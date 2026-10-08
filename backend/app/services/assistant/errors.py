from uuid import uuid4
from fastapi import HTTPException


class AssistantError(HTTPException):
    def __init__(self, code, message, status=422, retryable=False, retry_after=None):
        detail = dict(code=code, message=message, retryable=retryable, request_id=uuid4().hex)
        if retry_after is not None:
            detail["retry_after_seconds"] = retry_after
        super().__init__(status_code=status, detail=detail, headers={"Retry-After": str(retry_after)} if retry_after is not None else None)
