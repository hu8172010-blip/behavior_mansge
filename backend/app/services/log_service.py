import json
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FaOperationLog, SysAccount

ROLE_KEY_MAP = {1: "SUPER_ADMIN", 2: "SECURITY_LEAD", 3: "GUARD", 4: "COUNSELOR", 5: "SUPERVISOR", 6: "EMPLOYEE", 7: "AUDITOR"}


async def write_log(
    db: AsyncSession,
    module_code: str,
    operation_type: str,
    operator: SysAccount | None,
    target_id: int | None = None,
    target_type: str | None = None,
    content: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> None:
    log = FaOperationLog(
        module_code=module_code,
        operation_type=operation_type,
        operator_id=operator.account_id if operator else None,
        operator_role=ROLE_KEY_MAP.get(operator.type_id) if operator else None,
        target_id=target_id,
        target_type=target_type,
        operation_content=json.dumps(content, ensure_ascii=False) if content else None,
        ip_address=ip_address,
        operated_at=datetime.now(),
    )
    db.add(log)
