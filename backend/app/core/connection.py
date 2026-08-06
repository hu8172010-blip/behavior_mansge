from __future__ import annotations

from fastapi import WebSocket


class PermissionNotifier:
    """维护在线用户 WebSocket 连接，并按 account_id / type_id 映射，
    用于权限变更后向受影响用户推送通知。"""

    def __init__(self) -> None:
        # account_id -> set of WebSocket
        self._account_sockets: dict[int, set[WebSocket]] = {}
        # type_id -> set of WebSocket
        self._role_sockets: dict[int, set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, account_id: int, type_id: int) -> None:
        await websocket.accept()
        self._account_sockets.setdefault(account_id, set()).add(websocket)
        self._role_sockets.setdefault(type_id, set()).add(websocket)

    def disconnect(self, websocket: WebSocket, account_id: int, type_id: int) -> None:
        self._account_sockets.get(account_id, set()).discard(websocket)
        if not self._account_sockets.get(account_id):
            self._account_sockets.pop(account_id, None)
        self._role_sockets.get(type_id, set()).discard(websocket)
        if not self._role_sockets.get(type_id):
            self._role_sockets.pop(type_id, None)

    async def send_to_account(self, account_id: int, message: dict) -> None:
        sockets = self._account_sockets.get(account_id, set()).copy()
        for ws in sockets:
            try:
                await ws.send_json(message)
            except Exception:
                self._account_sockets.get(account_id, set()).discard(ws)

    async def broadcast_to_role(self, type_id: int, message: dict) -> None:
        sockets = self._role_sockets.get(type_id, set()).copy()
        for ws in sockets:
            try:
                await ws.send_json(message)
            except Exception:
                self._role_sockets.get(type_id, set()).discard(ws)

    async def broadcast_all(self, message: dict) -> None:
        """向所有在线 WebSocket 连接广播消息（用于设备状态恢复等全局事件通知）。"""
        seen: set[int] = set()
        for sockets in self._account_sockets.values():
            for ws in sockets.copy():
                if id(ws) in seen:
                    continue
                seen.add(id(ws))
                try:
                    await ws.send_json(message)
                except Exception:
                    pass


# 全局单例
notifier = PermissionNotifier()
