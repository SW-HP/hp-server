
from fastapi import HTTPException, Request, Response
from fastapi.middleware import Middleware
from fastapi.routing import APIRoute
import re

# SQL 인젝션 해킹 방지용 함수
def is_valid_injection(input: str) -> bool:
    sql_injection = re.compile(
        r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|GRANT|REVOKE|UNION|--|#|/\*|\*/|;)\b|'|\"|=|--|\|\||\bOR\b|\bAND\b)",
        re.IGNORECASE
    )
    return not sql_injection.search(input)

def sql_injection_protection(func):
    async def wrapper(request: Request, *args, **kwargs):
        for key, value in request.query_params.items():
            if not is_valid_injection(value):
                raise HTTPException(status_code=400, detail="입력값이 잘못되었습니다.")
        
        for key, value in request.path_params.items():
            if not is_valid_injection(value):
                raise HTTPException(status_code=400, detail="입력값이 잘못되었습니다.")
        
        return await func(request, *args, **kwargs)
    return wrapper

class SQLInjectionProtectedRoute(APIRoute):
    def get_route_handler(self):
        original_route_handler = super().get_route_handler()
        return sql_injection_protection(original_route_handler)
