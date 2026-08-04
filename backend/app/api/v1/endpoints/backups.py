from __future__ import annotations

import asyncio
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import get_current_account
from app.db.session import get_db
from app.models import SysAccount, SysDataBackup, SysDataRestoreLog
from app.schemas.common import ok, page_result

router = APIRouter()


class CreateBackupBody(BaseModel):
    """创建备份请求体。所有字段可选，未传或为空时使用默认值。"""
    backup_type: str = "MANUAL"
    strategy_desc: str = ""


def _db_credentials() -> tuple[str, str, str, str, str]:
    """从 DATABASE_URL 解析出 (host, port, user, password, dbname)。"""
    url = urlparse(settings.database_url)
    return (
        url.hostname or "127.0.0.1",
        str(url.port or 3306),
        unquote(url.username or "root"),
        unquote(url.password or ""),
        (url.path or "").lstrip("/"),
    )


def _backup_root() -> Path:
    root = Path(settings.backup_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _run(cmd: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, timeout=timeout)


def _restore_sync(cmd: list[str], src: Path, timeout: int = 300) -> subprocess.CompletedProcess:
    """在线程中执行 mysql 恢复（避免阻塞异步事件循环）。

    Windows 兼容性（实测结论）：
    1. mysql.exe 经 Python 管道读 stdin 时偶发不识别 EOF，永久挂起；
    2. cmd /c 的 '<' 重定向遇中文工作目录会乱码（%CD% 变 mojibake）；
    3. mysql 的 SOURCE 命令直接读中文绝对路径会失败（ANSI 代码页）。
    因此：把 dump 复制到纯 ASCII 临时目录，再用 SOURCE + 正斜杠 ASCII 路径执行。
    """
    import shutil
    import tempfile

    tmp_file = Path(tempfile.gettempdir()) / f"wbr_restore_{src.name}"
    shutil.copy2(src, tmp_file)
    try:
        exec_cmd = cmd + ["--execute", f"source {tmp_file.as_posix()}"]
        return subprocess.run(exec_cmd, capture_output=True, timeout=timeout)
    finally:
        tmp_file.unlink(missing_ok=True)


def _to_backup_dict(row: SysDataBackup) -> dict:
    return {
        "backup_id": row.backup_id,
        "backup_name": row.backup_name,
        "backup_type": row.backup_type,
        "strategy_desc": row.strategy_desc,
        "file_path": row.file_path,
        "file_size": row.file_size,
        "status": row.status,
        "operator_id": row.operator_id,
        "operator_name": row.operator_name,
        "create_time": row.create_time.strftime("%Y-%m-%d %H:%M:%S") if row.create_time else None,
    }


def _to_restore_dict(row: SysDataRestoreLog) -> dict:
    return {
        "restore_id": row.restore_id,
        "backup_id": row.backup_id,
        "backup_name": row.backup_name,
        "restore_status": row.restore_status,
        "result_msg": row.result_msg,
        "operator_id": row.operator_id,
        "operator_name": row.operator_name,
        "restore_time": row.restore_time.strftime("%Y-%m-%d %H:%M:%S") if row.restore_time else None,
    }


@router.get("")
async def list_backups(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    backup_type: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    _account: SysAccount = Depends(get_current_account),
):
    stmt = select(SysDataBackup)
    if backup_type:
        stmt = stmt.where(SysDataBackup.backup_type == backup_type)
    if status:
        stmt = stmt.where(SysDataBackup.status == status)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt = stmt.order_by(SysDataBackup.create_time.desc(), SysDataBackup.backup_id.desc()).offset((page - 1) * size).limit(size)
    rows = (await db.execute(stmt)).scalars().all()
    return ok(page_result([_to_backup_dict(r) for r in rows], total, page, size))


@router.post("")
async def create_backup(
    body: CreateBackupBody,
    db: AsyncSession = Depends(get_db),
    account: SysAccount = Depends(get_current_account),
):
    """创建备份。支持配置：
    - backup_type: MANUAL | AUTO（默认 MANUAL）
    - strategy_desc: 备份策略描述（建议填写，便于审计追溯）
    """
    backup_type = body.backup_type.upper() if body.backup_type else "MANUAL"
    if backup_type not in ("MANUAL", "AUTO"):
        backup_type = "MANUAL"
    user_strategy = (body.strategy_desc or "").strip()

    host, port, user, password, dbname = _db_credentials()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"backup_{stamp}.sql"
    file_path = _backup_root() / file_name
    target = str(file_path)
    mysqldump = Path(settings.mysql_bin_dir) / "mysqldump.exe"
    cmd = [
        str(mysqldump),
        f"--host={host}", f"--port={port}", f"--user={user}", f"--password={password}",
        "--single-transaction", "--default-character-set=utf8mb4",
        f"--result-file={target}", dbname,
    ]
    try:
        proc = await asyncio.to_thread(_run, cmd)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"执行备份命令失败: {exc}") from exc

    if proc.returncode != 0 or not file_path.exists():
        detail = (proc.stderr or b"").decode("utf-8", "ignore")[-300:] or "备份文件未生成"
        raise HTTPException(status_code=500, detail=f"备份失败: {detail}")

    default_desc = "手动备份（mysqldump --single-transaction）" if backup_type == "MANUAL" else "自动备份（mysqldump --single-transaction）"
    record = SysDataBackup(
        backup_name=f"{'手动' if backup_type == 'MANUAL' else '自动'}备份_{stamp}",
        backup_type=backup_type,
        strategy_desc=user_strategy or default_desc,
        file_path=str(Path(settings.backup_dir) / file_name),
        file_size=file_path.stat().st_size,
        status="SUCCESS",
        operator_id=account.account_id,
        operator_name=account.real_name,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return ok(_to_backup_dict(record), message="备份成功")


@router.delete("/{backup_id}")
async def delete_backup(
    backup_id: int,
    db: AsyncSession = Depends(get_db),
    account: SysAccount = Depends(get_current_account),
):
    if account.type_id != 1:
        raise HTTPException(status_code=403, detail="仅超级管理员可删除备份")
    row = (
        await db.execute(select(SysDataBackup).where(SysDataBackup.backup_id == backup_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="备份记录不存在")
    try:
        (_backup_root() / Path(row.file_path).name).unlink(missing_ok=True)
    except OSError:
        pass
    await db.delete(row)
    await db.commit()
    return ok(message="备份已删除")


@router.post("/{backup_id}/restore")
async def restore_backup(
    backup_id: int,
    db: AsyncSession = Depends(get_db),
    account: SysAccount = Depends(get_current_account),
):
    if account.type_id != 1:
        raise HTTPException(status_code=403, detail="仅超级管理员可执行数据恢复")
    row = (
        await db.execute(select(SysDataBackup).where(SysDataBackup.backup_id == backup_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="备份记录不存在")

    backup_id_, backup_name_ = row.backup_id, row.backup_name
    file_name = Path(row.file_path).name
    # 关键：先提交事务释放元数据锁。否则恢复脚本里的 DROP TABLE 会被本会话
    # SELECT sys_data_backup 持有的共享 MDL 阻塞，导致 mysql 子进程永久等待。
    await db.commit()

    host, port, user, password, dbname = _db_credentials()
    src = _backup_root() / file_name
    if not src.exists():
        log = SysDataRestoreLog(
            backup_id=backup_id_, backup_name=backup_name_,
            restore_status="FAILED", result_msg=f"备份文件不存在: {row.file_path}",
            operator_id=account.account_id, operator_name=account.real_name,
        )
        db.add(log)
        await db.commit()
        raise HTTPException(status_code=500, detail="备份文件不存在，无法恢复")

    mysql = Path(settings.mysql_bin_dir) / "mysql.exe"
    cmd = [
        str(mysql),
        f"--host={host}", f"--port={port}", f"--user={user}", f"--password={password}",
        "--connect-timeout=10",
        "--default-character-set=utf8mb4", dbname,
    ]
    try:
        proc = await asyncio.to_thread(_restore_sync, cmd, src)
    except Exception as exc:  # noqa: BLE001
        log = SysDataRestoreLog(
            backup_id=backup_id_, backup_name=backup_name_,
            restore_status="FAILED", result_msg=f"恢复命令执行异常: {exc}",
            operator_id=account.account_id, operator_name=account.real_name,
        )
        db.add(log)
        await db.commit()
        raise HTTPException(status_code=500, detail=f"恢复执行失败: {exc}") from exc

    if proc.returncode != 0:
        detail = (proc.stderr or b"").decode("utf-8", "ignore")[-300:] or "mysql 命令返回非零"
        log = SysDataRestoreLog(
            backup_id=backup_id_, backup_name=backup_name_,
            restore_status="FAILED", result_msg=detail,
            operator_id=account.account_id, operator_name=account.real_name,
        )
        db.add(log)
        await db.commit()
        raise HTTPException(status_code=500, detail=f"恢复失败: {detail}")

    log = SysDataRestoreLog(
        backup_id=backup_id_, backup_name=backup_name_,
        restore_status="SUCCESS", result_msg="恢复完成",
        operator_id=account.account_id, operator_name=account.real_name,
    )
    db.add(log)
    await db.commit()
    return ok(message="数据恢复成功")


@router.get("/restore-logs")
async def list_restore_logs(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _account: SysAccount = Depends(get_current_account),
):
    total = (await db.execute(select(func.count()).select_from(SysDataRestoreLog))).scalar_one()
    stmt = (
        select(SysDataRestoreLog)
        .order_by(SysDataRestoreLog.restore_time.desc(), SysDataRestoreLog.restore_id.desc())
        .offset((page - 1) * size).limit(size)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return ok(page_result([_to_restore_dict(r) for r in rows], total, page, size))
