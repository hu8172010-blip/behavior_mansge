from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_token, get_current_account, load_permission_keys
from app.db.session import get_db
from app.models import SysAccount, SysUserType
from app.schemas.common import ok
from app.services.log_service import write_log

router = APIRouter()


class LoginBody(BaseModel):
    login_name: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=64)


class RegisterBody(BaseModel):
    real_name: str = Field(min_length=1, max_length=64)
    login_name: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=4, max_length=64)
    type_id: int


def account_payload(account: SysAccount, role_name: str | None, permissions: list[str], token: str | None = None) -> dict:
    data = {
        "account_id": account.account_id,
        "login_name": account.login_name,
        "real_name": account.real_name,
        "dept": account.dept,
        "type_id": account.type_id,
        "role_name": role_name,
        "permissions": permissions,
    }
    if token is not None:
        data["token"] = token
    return data


async def get_role_name(db: AsyncSession, type_id: int) -> str | None:
    row = (await db.execute(select(SysUserType.type_name).where(SysUserType.type_id == type_id))).scalar_one_or_none()
    return row


@router.post("/login")
async def login(body: LoginBody, db: AsyncSession = Depends(get_db)):
    account = (
        await db.execute(select(SysAccount).where(SysAccount.login_name == body.login_name))
    ).scalar_one_or_none()
    if account is None or account.password != body.password:
        raise HTTPException(status_code=400, detail="用户名或密码错误")
    if account.status != 1:
        raise HTTPException(status_code=403, detail="该账号已被禁用，请联系管理员")
    account.last_login_time = datetime.now()
    permissions = await load_permission_keys(db, account)
    role_name = await get_role_name(db, account.type_id)
    await write_log(db, "SYSTEM", "QUERY", account, account.account_id, "USER", {"action": "login"})
    await db.commit()
    return ok(account_payload(account, role_name, permissions, create_token(account.account_id)), "登录成功")


@router.get("/roles")
async def register_roles(db: AsyncSession = Depends(get_db)):
    roles = (
        (await db.execute(select(SysUserType).where(SysUserType.type_id != 1).order_by(SysUserType.type_id)))
        .scalars()
        .all()
    )
    return ok([{"id": role.type_id, "name": role.type_name} for role in roles])


@router.post("/register")
async def register(body: RegisterBody, db: AsyncSession = Depends(get_db)):
    exists = (
        await db.execute(select(SysAccount.account_id).where(SysAccount.login_name == body.login_name))
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=400, detail="该用户名已存在，请更换用户名")
    role = (await db.execute(select(SysUserType).where(SysUserType.type_id == body.type_id))).scalar_one_or_none()
    if role is None or body.type_id == 1:
        raise HTTPException(status_code=400, detail="用户类型不存在")
    account = SysAccount(
        login_name=body.login_name,
        password=body.password,
        real_name=body.real_name,
        type_id=body.type_id,
        status=1,
    )
    db.add(account)
    await db.flush()
    await db.commit()
    return ok({"account_id": account.account_id, "login_name": account.login_name}, "注册成功，请登录")


@router.get("/me")
async def me(account: SysAccount = Depends(get_current_account), db: AsyncSession = Depends(get_db)):
    permissions = await load_permission_keys(db, account)
    role_name = await get_role_name(db, account.type_id)
    return ok(account_payload(account, role_name, permissions))
