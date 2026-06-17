from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4


@dataclass(frozen=True)
class ErrorResponse:
    code: str
    message: str
    request_id: str
    details: dict = field(default_factory=dict)


class DomainError(Exception):
    """Project-wide domain error using the required response shape."""

    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.request_id = f"req_{uuid4().hex[:8]}"
        self.details = details or {}

    def to_response(self) -> dict:
        response = ErrorResponse(
            code=self.code,
            message=self.message,
            request_id=self.request_id,
            details=self.details,
        )
        return {
            "code": response.code,
            "message": response.message,
            "request_id": response.request_id,
            "details": response.details,
        }

