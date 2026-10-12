"""Small additive error contract for public authentication endpoints."""
from fastapi import HTTPException


def auth_problem(status: int, code: str, message: str, *, field: str = "", headers=None):
    raise HTTPException(status, {
        "code": code, "message": message,
        "field_errors": [{"field": field, "message": message}] if field else [],
    }, headers=headers)
