from typing import Generic, TypeVar

ServiceResult = TypeVar("ServiceResult")


class BaseService(Generic[ServiceResult]):
    pass
