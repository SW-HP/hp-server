# 일단은 기본적인 부분 제외하고 예외처리 없이 수행한 뒤 필요한 부분을 추가하는 식으로 할것.
#
# openai assistant api 부분 미완성되어있음
# - 음성인식의 결과가 이상한 경우 어떻게 처리할것인지?
# - 내부적으로 쓰레드 삭제를 어떻게 할것인지?
# - 사용자 메모리를 어떻게 구현할것인지?
# - 메모리 구성을 하겠다면, 어떻게 파인튜닝할것인지?


import nest_asyncio
nest_asyncio.apply()

import sqlite3
from routes.auth import auth_router
from database import Base, engine
from schemas import schemas
from models import models
from database import database
from routes import auth
from utils import token, password_utils


from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from base64 import b64encode

# FastAPI 애플리케이션 생성
app = FastAPI(
    title="HP team",
    description="This is the API documentation for the HealthPartner in SWcapstone",
    version="1.0.0",
    contact={
        "name": "API git",
        "url": "https://github.com/SW-HP/hp-server",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
)

# CORS (Cross Origin Resource Sharing, 교차 출처 리소스 공유) 설정
# 

app.add_middleware(
    CORSMiddleware,
    # allow_origins=variables.ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# HTTPS 리다이렉트
# app.add_middleware(HTTPSRedirectMiddleware)
# 음.. 인증서랑 어떻게 해야할지 몰겠네요 좀 걸릴것같습니다.
# 일단은 api완성부터하겠습니다.

# 레이트 리미팅 설정
# limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
# app.state.limiter = limiter
# app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# # DB 연결
# Base.metadata.create_all(bind=engine)

app.include_router(auth_router,prefix="/auth",tags=["authentications"])
# app.include_router(user.router, prefix="/users", tags=["Users"])
# app.include_router(assistant.router, prefix="/assistant", tags=["Assistant"])
# app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
# app.include_router(reminders.router, prefix="/reminder", tags=["Reminder"])

# @app.exception_handler(HTTPException)
# async def custom_http_exception_handler(request, exc):
#     return JSONResponse(
#         status_code=exc.status_code,
#         content={"detail": exc.detail}
#     )

# if __name__ == "__main__":
#     uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
# bash > uvicorn main:app --host [host] --port [port] --reload