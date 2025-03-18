
from fastapi import HTTPException, Request, Response
from fastapi.middleware import Middleware
import re

# SQL 인젝션 해킹 방지용 함수
def is_valid_injection(input: str) -> bool:
    sql_injection = re.compile(
        r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|GRANT|REVOKE|UNION|--|#|/\*|\*/|;)\b|'|\"|=|--|\|\||\bOR\b|\bAND\b)",
        # 더 추가할 정규식 없는지?
        re.IGNORECASE
    )
    return not sql_injection.search(input)

async def sql_injection_middleware(request: Request, call_next):
    for key, value in request.query_params.items():
        if not is_valid_injection(value):
            raise HTTPException(status_code=400, detail="SQL Injection detected in query parameter")
    
    for key, value in request.path_params.items():
        if not is_valid_injection(value):
            raise HTTPException(status_code=400, detail="SQL Injection detected in path parameter")
    
    response = await call_next(request)
    return response