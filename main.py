# 일단은 기본적인 부분 제외하고 예외처리 없이 수행한 뒤 필요한 부분을 추가하는 식으로 할것.
#
# 보호자 및 시니어 회원가입 및 로그인
# 보호자의 시니어 위치 확인 api 추가
# openai assistant api 부분 미완성되어있음
# - 음성인식의 결과가 이상한 경우 어떻게 처리할것인지?
# - 내부적으로 쓰레드 삭제를 어떻게 할것인지?
# - 주제별로 쓰레드를 나누기? 매일 삭제? 흠..
# - 사용자 메모리를 어떻게 구현할것인지?
# - 메모리 구성을 하겠다면, 어떻게 파인튜닝할것인지?
# - 파인튜닝 데이터 누가 만들것인지?

# 라우터를 통한 엔드포인트별 구별이 필요
# SERVER/
# ├── main.py
# ├── routers/            # 라우터
# │   ├── auth.py           # 유저 인증 관리
# │   ├── register.py       # 유저 가입 관리
# │   ├── assistant.py      # openai assistnat api
# │   ├── event.py          # 일정관리
# ├── schemas/            # HTTP 통신 스키마(데이터 교환을 정의하는 규칙이나 구조)
# │   ├── schemas.py
# ├── utils/              # 유틸리티 함수들
# │   ├── crud.py
# ├── database/           # 데이터베이스 설정 및 세션 관리
# │   ├── session.py
# └── .env                # 환경 변수 파일

import nest_asyncio
nest_asyncio.apply()

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
    title="Health Partner API",
    description="This is the API documentation for the Health Partner",
    version="1.0.0",
    contact={
        "name": "Health Partner",
        "url": "https://github.com/SW-HP/",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
)

# middleware
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# routers
from routers import test
app.include_router(test.router, prefix="/test", tags=["test"])

# bash > uvicorn main:app --host [host] --port [port] --reload