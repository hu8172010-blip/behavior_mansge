from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.connection import notifier
from app.core.security import decode_token
from app.db.session import AsyncSessionLocal
from app.models import SysAccount

router = APIRouter()


@router.websocket("/permissions")
async def permission_ws(websocket: WebSocket, token: str = Query(...)):
    try:
        account_id = decode_token(token)
    except Exception:
        await websocket.close(code=1008)
        return

    async with AsyncSessionLocal() as db:
        account = (
            await db.execute(select(SysAccount).where(SysAccount.account_id == account_id))
        ).scalar_one_or_none()

    if account is None:
        await websocket.close(code=1008)
        return

    await notifier.connect(websocket, account.account_id, account.type_id)
    try:
        while True:
            # 仅维持连接，不处理客户端消息
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        notifier.disconnect(websocket, account.account_id, account.type_id)
