from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.connection import notifier
from app.core.security import get_current_account, require_super_account
from app.db.session import get_db
from app.models import SysAccount, SysAccountPermission, SysPermission, SysTypePermission, SysUserType
from app.schemas.common import ok, page_result
from app.services.log_service import write_log

router = APIRouter()


def fmt(dt) -> str | None:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


@router.get("/accounts")
async def list_accounts(
    keyword: str | None = Query(default=None),
    type_id: int | None = Query(default=None),
    status: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: SysAccount = Depends(get_current_account),
):
    stmt = select(SysAccount, SysUserType.type_name).join(SysUserType, SysUserType.type_id == SysAccount.type_id)
    count_stmt = select(func.count()).select_from(SysAccount)
    if keyword:
        like = f"%{keyword}%"
        cond = or_(SysAccount.login_name.like(like), SysAccount.real_name.like(like), SysAccount.dept.like(like))
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)
    if type_id is not None:
        stmt = stmt.where(SysAccount.type_id == type_id)
        count_stmt = count_stmt.where(SysAccount.type_id == type_id)
    if status is not None:
        stmt = stmt.where(SysAccount.status == status)
        count_stmt = count_stmt.where(SysAccount.status == status)
    total = (await db.execute(count_stmt)).scalar_one()
    rows = (await db.execute(stmt.order_by(SysAccount.account_id).offset((page - 1) * size).limit(size))).all()
    custom_account_ids = set(
        (await db.execute(select(SysAccountPermission.account_id).distinct())).scalars().all()
    )
    items = [
        {
            "account_id": row[0].account_id,
            "login_name": row[0].login_name,
            "real_name": row[0].real_name,
            "dept": row[0].dept,
            "phone": row[0].phone,
            "type_id": row[0].type_id,
            "type_name": row[1],
            "status": row[0].status,
            "use_custom": 1 if row[0].account_id in custom_account_ids else 0,
            "last_login_time": fmt(row[0].last_login_time),
        }
        for row in rows
    ]
    return ok(page_result(items, total, page, size))


class AccountBody(BaseModel):
    login_name: str
    password: str
    real_name: str
    dept: str | None = None
    phone: str | None = None
    type_id: int


@router.post("/accounts")
async def create_account(body: AccountBody, db: AsyncSession = Depends(get_db), account: SysAccount = Depends(get_current_account)):
    exists = (
        await db.execute(select(SysAccount.account_id).where(SysAccount.login_name == body.login_name))
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=400, detail="登录名已存在")
    role = (
        await db.execute(select(SysUserType).where(SysUserType.type_id == body.type_id))
    ).scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=400, detail="角色不存在")
    new_account = SysAccount(
        login_name=body.login_name,
        password=body.password,
        real_name=body.real_name,
        dept=body.dept,
        phone=body.phone,
        type_id=body.type_id,
        status=1,
    )
    db.add(new_account)
    await db.flush()
    await write_log(db, "SYSTEM", "UPDATE", account, new_account.account_id, "USER", {"action": "create_account", "login_name": body.login_name, "type_id": body.type_id})
    await db.commit()
    return ok({"account_id": new_account.account_id}, "账号已创建")


class StatusBody(BaseModel):
    status: int


@router.put("/accounts/{account_id}/status")
async def toggle_account_status(account_id: int, body: StatusBody, db: AsyncSession = Depends(get_db), account: SysAccount = Depends(get_current_account)):
    if body.status not in (0, 1):
        raise HTTPException(status_code=400, detail="status 仅支持 0 或 1")
    if account_id == 1:
        raise HTTPException(status_code=400, detail="超级管理员账号禁止停用")
    if account_id == account.account_id:
        raise HTTPException(status_code=400, detail="不能停用自己的账号")
    target = (
        await db.execute(select(SysAccount).where(SysAccount.account_id == account_id))
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    target.status = body.status
    await write_log(db, "SYSTEM", "UPDATE", account, account_id, "USER", {"action": "toggle_status", "status": body.status})
    await db.commit()
    return ok(message="账号已启用" if body.status == 1 else "账号已停用")


@router.get("/roles")
async def list_roles(db: AsyncSession = Depends(get_db), _: SysAccount = Depends(get_current_account)):
    roles = (await db.execute(select(SysUserType).order_by(SysUserType.type_id))).scalars().all()
    perm_rows = (await db.execute(select(SysTypePermission.type_id, SysTypePermission.perm_id))).all()
    perm_map: dict[int, list[int]] = {}
    for type_id, perm_id in perm_rows:
        perm_map.setdefault(type_id, []).append(perm_id)
    account_cnt = (
        select(SysAccount.type_id, func.count().label("cnt")).group_by(SysAccount.type_id)
    )
    cnt_map = {row[0]: row[1] for row in (await db.execute(account_cnt)).all()}
    return ok(
        [
            {
                "type_id": role.type_id,
                "type_name": role.type_name,
                "type_desc": role.type_desc,
                "is_super": role.type_id == 1,
                "account_count": cnt_map.get(role.type_id, 0),
                "perm_ids": sorted(perm_map.get(role.type_id, [])),
            }
            for role in roles
        ]
    )


@router.get("/permissions")
async def list_permissions(db: AsyncSession = Depends(get_db), _: SysAccount = Depends(get_current_account)):
    perms = (await db.execute(select(SysPermission).order_by(SysPermission.sort, SysPermission.perm_id))).scalars().all()
    return ok(
        [
            {
                "perm_id": p.perm_id,
                "perm_name": p.perm_name,
                "perm_key": p.perm_key,
                "perm_type": p.perm_type,
                "parent_id": p.parent_id,
                "sort": p.sort,
            }
            for p in perms
        ]
    )


class RolePermBody(BaseModel):
    perm_ids: list[int]


@router.put("/roles/{type_id}/permissions")
async def save_role_permissions(type_id: int, body: RolePermBody, db: AsyncSession = Depends(get_db), account: SysAccount = Depends(get_current_account)):
    if type_id == 1:
        raise HTTPException(status_code=400, detail="超级管理员默认拥有全部权限，无需配置")
    role = (
        await db.execute(select(SysUserType).where(SysUserType.type_id == type_id))
    ).scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    valid_ids = set(
        (await db.execute(select(SysPermission.perm_id).where(SysPermission.perm_id.in_(body.perm_ids or [0])))).scalars().all()
    )
    await db.execute(delete(SysTypePermission).where(SysTypePermission.type_id == type_id))
    for perm_id in sorted(valid_ids):
        db.add(SysTypePermission(type_id=type_id, perm_id=perm_id))
    await write_log(db, "SYSTEM", "UPDATE", account, type_id, "USER", {"action": "config_role_permissions", "perm_ids": sorted(valid_ids)})
    await db.commit()
    await notifier.broadcast_to_role(type_id, {"type": "ROLE_PERM_CHANGED", "type_id": type_id})
    return ok(message=f"角色「{role.type_name}」权限已保存，共 {len(valid_ids)} 项")


class AccountPermBody(BaseModel):
    use_custom: int
    perm_ids: list[int] = []


@router.get("/accounts/{account_id}/permissions")
async def get_account_permissions(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    _: SysAccount = Depends(require_super_account),
):
    target = (
        await db.execute(select(SysAccount).where(SysAccount.account_id == account_id))
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    if target.type_id == 1:
        raise HTTPException(status_code=400, detail="不能为超级管理员配置权限")
    role_perm_ids = (
        (await db.execute(select(SysTypePermission.perm_id).where(SysTypePermission.type_id == target.type_id)))
        .scalars()
        .all()
    )
    custom_perm_ids = (
        (await db.execute(select(SysAccountPermission.perm_id).where(SysAccountPermission.account_id == account_id)))
        .scalars()
        .all()
    )
    use_custom = 1 if custom_perm_ids else 0
    effective = sorted(custom_perm_ids) if use_custom else sorted(role_perm_ids)
    return ok(
        {
            "use_custom": use_custom,
            "custom_perm_ids": sorted(custom_perm_ids),
            "role_perm_ids": sorted(role_perm_ids),
            "effective_perm_ids": effective,
        }
    )


@router.put("/accounts/{account_id}/permissions")
async def save_account_permissions(
    account_id: int,
    body: AccountPermBody,
    db: AsyncSession = Depends(get_db),
    account: SysAccount = Depends(require_super_account),
):
    target = (
        await db.execute(select(SysAccount).where(SysAccount.account_id == account_id))
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    if target.type_id == 1:
        raise HTTPException(status_code=400, detail="不能为超级管理员配置权限")
    if body.use_custom not in (0, 1):
        raise HTTPException(status_code=400, detail="use_custom 仅支持 0 或 1")
    await db.execute(delete(SysAccountPermission).where(SysAccountPermission.account_id == account_id))
    if body.use_custom == 1:
        if not body.perm_ids:
            raise HTTPException(status_code=400, detail="自定义权限模式下至少需要选择一项权限")
        valid_ids = set(
            (
                await db.execute(
                    select(SysPermission.perm_id).where(SysPermission.perm_id.in_(body.perm_ids or [0]))
                )
            )
            .scalars()
            .all()
        )
        if not valid_ids:
            raise HTTPException(status_code=400, detail="未找到有效权限")
        for perm_id in sorted(valid_ids):
            db.add(SysAccountPermission(account_id=account_id, perm_id=perm_id))
        action = "config_account_permissions"
        log_content = {"action": action, "use_custom": 1, "perm_ids": sorted(valid_ids)}
        message = f"账号「{target.login_name}」自定义权限已保存，共 {len(valid_ids)} 项"
    else:
        action = "clear_account_permissions"
        log_content = {"action": action, "use_custom": 0, "perm_ids": []}
        message = f"账号「{target.login_name}」已恢复角色默认权限"
    await write_log(db, "SYSTEM", "UPDATE", account, account_id, "USER", log_content)
    await db.commit()
    await notifier.send_to_account(account_id, {"type": "ACCOUNT_PERM_CHANGED", "account_id": account_id})
    return ok(message=message)


@router.delete("/accounts/{account_id}")
async def delete_account(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    account: SysAccount = Depends(require_super_account),
):
    if account_id == 1:
        raise HTTPException(status_code=400, detail="不能删除超级管理员账号")
    if account_id == account.account_id:
        raise HTTPException(status_code=400, detail="不能删除当前登录账号")
    target = (
        await db.execute(select(SysAccount).where(SysAccount.account_id == account_id))
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    await db.execute(delete(SysAccount).where(SysAccount.account_id == account_id))
    await write_log(
        db,
        "SYSTEM",
        "DELETE",
        account,
        account_id,
        "USER",
        {"action": "delete_account", "login_name": target.login_name, "real_name": target.real_name},
    )
    await db.commit()
    return ok(message=f"账号 {target.login_name} 已删除")


@router.delete("/roles/{type_id}")
async def delete_role(
    type_id: int,
    db: AsyncSession = Depends(get_db),
    account: SysAccount = Depends(require_super_account),
):
    if type_id == 1:
        raise HTTPException(status_code=400, detail="不能删除超级管理员角色")
    role = (
        await db.execute(select(SysUserType).where(SysUserType.type_id == type_id))
    ).scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    in_use = (
        await db.execute(select(SysAccount.account_id).where(SysAccount.type_id == type_id).limit(1))
    ).scalar_one_or_none()
    if in_use is not None:
        raise HTTPException(status_code=400, detail="该角色下存在账号，无法删除")
    await db.execute(delete(SysUserType).where(SysUserType.type_id == type_id))
    await write_log(
        db,
        "SYSTEM",
        "DELETE",
        account,
        type_id,
        "USER",
        {"action": "delete_role", "type_name": role.type_name},
    )
    await db.commit()
    return ok(message=f"角色「{role.type_name}」已删除")


class CreateRoleBody(BaseModel):
    type_name: str = Field(min_length=1, max_length=64)
    type_desc: str | None = None


@router.post("/roles")
async def create_role(
    body: CreateRoleBody,
    db: AsyncSession = Depends(get_db),
    account: SysAccount = Depends(require_super_account),
):
    exists = (
        await db.execute(select(SysUserType).where(SysUserType.type_name == body.type_name))
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=400, detail="角色名称已存在")
    role = SysUserType(type_name=body.type_name, type_desc=body.type_desc)
    db.add(role)
    await db.flush()
    await write_log(
        db,
        "SYSTEM",
        "CREATE",
        account,
        role.type_id,
        "USER",
        {"action": "create_role", "type_name": role.type_name, "type_desc": body.type_desc},
    )
    await db.commit()
    return ok({"type_id": role.type_id}, "角色已创建")
