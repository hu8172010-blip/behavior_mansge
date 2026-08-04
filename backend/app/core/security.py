from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models import SysAccount, SysAccountPermission, SysPermission, SysTypePermission

ALGORITHM = "HS256"
bearer = HTTPBearer(auto_error=False)


def create_token(account_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours)
    return jwt.encode({"sub": str(account_id), "exp": expire}, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> int:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="登录状态已失效，请重新登录") from exc


async def get_current_account(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> SysAccount:
    if credentials is None:
        raise HTTPException(status_code=401, detail="未登录")
    account_id = decode_token(credentials.credentials)
    account = (await db.execute(select(SysAccount).where(SysAccount.account_id == account_id))).scalar_one_or_none()
    if account is None or account.status != 1:
        raise HTTPException(status_code=401, detail="账号不存在或已被禁用")
    return account


async def require_super_account(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> SysAccount:
    account = await get_current_account(credentials, db)
    if account.type_id != 1:
        raise HTTPException(status_code=403, detail="需要超级管理员权限")
    return account


def require_permission(perm_key: str):
    async def dependency(
        account: SysAccount = Depends(get_current_account),
        db: AsyncSession = Depends(get_db),
    ) -> SysAccount:
        keys = await load_permission_keys(db, account)
        if perm_key not in keys:
            raise HTTPException(status_code=403, detail="无操作权限")
        return account

    return dependency


async def load_permission_keys(db: AsyncSession, account: SysAccount) -> list[str]:
    if account.type_id == 1:
        rows = (await db.execute(select(SysPermission.perm_key))).scalars().all()
        return list(rows)
    custom_ids = (
        (await db.execute(select(SysAccountPermission.perm_id).where(SysAccountPermission.account_id == account.account_id)))
        .scalars()
        .all()
    )
    if custom_ids:
        rows = (await db.execute(select(SysPermission.perm_key).where(SysPermission.perm_id.in_(custom_ids)))).scalars().all()
        return list(rows)
    role_ids = (
        (await db.execute(select(SysTypePermission.perm_id).where(SysTypePermission.type_id == account.type_id))).scalars().all()
    )
    if not role_ids:
        return []
    rows = (await db.execute(select(SysPermission.perm_key).where(SysPermission.perm_id.in_(role_ids)))).scalars().all()
    return list(rows)
