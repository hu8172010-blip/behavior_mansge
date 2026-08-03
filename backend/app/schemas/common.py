from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "ok"
    data: T | None = None


class PageResult(BaseModel, Generic[T]):
    list: list[T]
    total: int
    page: int
    size: int


def ok(data: Any = None, message: str = "ok") -> dict[str, Any]:
    return {"code": 0, "message": message, "data": data}


def page_result(items: list[Any], total: int, page: int, size: int) -> dict[str, Any]:
    return {"list": items, "total": total, "page": page, "size": size}
