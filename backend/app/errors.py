"""One error type for the whole backend. The API layer turns it into JSON."""

from typing import Any, Optional


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        field: Optional[str] = None,
        extra: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.field = field
        self.extra = extra or {}

    def body(self) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code, "message": self.message, "field": self.field}
        error.update(self.extra)
        return {"error": error}


def not_found(what: str) -> ApiError:
    return ApiError(404, "not_found", f"{what} not found.")
