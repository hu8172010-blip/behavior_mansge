import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_account
from app.db.session import get_db
from app.models import FaOperationLog, SysAccount
from app.schemas.common import ok, page_result

router = APIRouter()


def fmt(dt: datetime | None) -> str | None:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


def build_query(module_code, operation_type, keyword, start_time, end_time):
    operator = SysAccount.__table__.alias("operator")
    stmt = select(FaOperationLog, operator.c.real_name.label("operator_name")).outerjoin(
        operator, operator.c.account_id == FaOperationLog.operator_id
    )
    count_stmt = select(func.count()).select_from(FaOperationLog)
    if module_code:
        stmt = stmt.where(FaOperationLog.module_code == module_code)
        count_stmt = count_stmt.where(FaOperationLog.module_code == module_code)
    if operation_type:
        stmt = stmt.where(FaOperationLog.operation_type == operation_type)
        count_stmt = count_stmt.where(FaOperationLog.operation_type == operation_type)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(or_(operator.c.real_name.like(like), FaOperationLog.operation_content.like(like)))
        count_stmt = count_stmt.where(FaOperationLog.operation_content.like(like))
    if start_time:
        stmt = stmt.where(FaOperationLog.operated_at >= start_time)
        count_stmt = count_stmt.where(FaOperationLog.operated_at >= start_time)
    if end_time:
        stmt = stmt.where(FaOperationLog.operated_at <= end_time)
        count_stmt = count_stmt.where(FaOperationLog.operated_at <= end_time)
    return stmt, count_stmt


@router.get("")
async def list_logs(
    module_code: str | None = Query(default=None),
    operation_type: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    start_time: str | None = Query(default=None),
    end_time: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: SysAccount = Depends(get_current_account),
):
    stmt, count_stmt = build_query(module_code, operation_type, keyword, start_time, end_time)
    total = (await db.execute(count_stmt)).scalar_one()
    rows = (
        await db.execute(stmt.order_by(FaOperationLog.operated_at.desc()).offset((page - 1) * size).limit(size))
    ).all()
    items = [
        {
            "log_id": row[0].log_id,
            "module_code": row[0].module_code,
            "operation_type": row[0].operation_type,
            "operator_id": row[0].operator_id,
            "operator_name": row[1],
            "operator_role": row[0].operator_role,
            "target_id": row[0].target_id,
            "target_type": row[0].target_type,
            "operation_content": row[0].operation_content,
            "operated_at": fmt(row[0].operated_at),
        }
        for row in rows
    ]
    return ok(page_result(items, total, page, size))


@router.get("/export")
async def export_logs(
    module_code: str | None = Query(default=None),
    operation_type: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    start_time: str | None = Query(default=None),
    end_time: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: SysAccount = Depends(get_current_account),
):
    stmt, _ = build_query(module_code, operation_type, keyword, start_time, end_time)
    rows = (await db.execute(stmt.order_by(FaOperationLog.operated_at.desc()).limit(5000))).all()
    buffer = io.StringIO()
    buffer.write("﻿")
    writer = csv.writer(buffer)
    writer.writerow(["日志ID", "模块", "操作类型", "操作人", "角色", "对象类型", "对象ID", "操作详情", "操作时间"])
    for row in rows:
        log: FaOperationLog = row[0]
        writer.writerow([
            log.log_id,
            log.module_code,
            log.operation_type,
            row[1] or "",
            log.operator_role or "",
            log.target_type or "",
            log.target_id or "",
            (log.operation_content or "").replace("\n", " "),
            fmt(log.operated_at),
        ])
    buffer.seek(0)
    filename = f"operation_logs_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
