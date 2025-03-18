from fastapi import APIRouter, Depends, HTTPException, status, Header
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from database import get_db, exception_handler
from schemas import UserCreate, UserUpdate, UserResponse, TokenResponse, UserRegister, Login
from datetime import timedelta, datetime
from utils import auth_handler, get_password_hash, verify_password, get_current_user
from pydantic import BaseModel, field_validator
from sqlalchemy.exc import SQLAlchemyError
from models import User, RefreshToken
import uuid, re, os

auth_router = APIRouter()

############################################################################################
######################################## 사용자 생성 ########################################
############################################################################################
@exception_handler
@auth_router.post('/user_register', response_model=UserRegister) # 출력 하는 모델
def user_register(user: UserCreate, db: Session = Depends(get_db)): # 입력 받는 모델
    try:
        # 이메일 입력 검증
        if user.email:
            existing_user = db.query(User).filter(User.email == user.email).first()
            if existing_user:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="이미 등록된 이메일입니다")
        
        # 전화번호 입력 검증
        if user.phone_number:
            existing_user = db.query(User).filter(User.phone_number == user.phone_number).first()
            if existing_user:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="전화번호가 이미 등록되어 있습니다")
        
        if not user.email and not user.phone_number:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="이메일 혹은 전화번호를 입력해주세요")

        hashed_password = get_password_hash(user.user_password)

        # 새 사용자 생성
        new_user = User(
            user_uuid=str(uuid.uuid4()),
            user_name=user.user_name,
            user_password=hashed_password,
            phone_number=user.phone_number,
            email=user.email,
            created_at=datetime.utcnow(),
        )

        db.add(new_user)
        db.commit()

        # 토큰 생성
        access_token = auth_handler.create_access_token(new_user.user_id)
        refresh_token = auth_handler.create_refresh_token(new_user.user_id)
        

        # 리프레시 토큰 저장 및 초기화 작업
        auth_handler.save_token(db, new_user.user_id, refresh_token)

        # 새 사용자 정보 갱신
        db.refresh(new_user)

        # 응답 반환
        return UserRegister(
            user_name=new_user.user_name,
            phone_number=new_user.phone_number,
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer"
            )

    # 데이터베이스 관련 오류 처리
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류가 발생했습니다: {str(e)}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"예상치 못한 오류가 발생했습니다: {str(e)}")
    

############################################################################################
####################################### 사용자 로그인 #######################################
############################################################################################

@exception_handler
@auth_router.post("/login", response_model=TokenResponse)
def login(data: Login, db: Session = Depends(get_db)):
    user = None
    identifier = data.identifier

    if identifier["type"] == "email":            # 이메일로 로그인 시
        user = db.query(User).filter(User.email == identifier["value"]).first()
    elif identifier["type"] == "phone_number":   # 전화번호로 로그인 시
        user = db.query(User).filter(User.phone_number == identifier["value"]).first()

    if not user:
        raise HTTPException(status_code=404, detail="유저를 찾을 수 없습니다")
    

    if not verify_password(data.password,  user.user_password):
        raise HTTPException(status_code=401, detail="비밀번호가 일치하지 않습니다")

    # 기존 리프레시 토큰 무효화
    existing_refresh_token = db.query(RefreshToken).filter(RefreshToken.user_id == user.user_id).first()
    if existing_refresh_token:
        return TokenResponse(access_token=auth_handler.create_access_token(user.user_id),
                            refresh_token=existing_refresh_token.token)

    # 새로운 액세스 토큰 및 리프레시 토큰 발급
    access_token = auth_handler.create_access_token(user.user_id)
    refresh_token = auth_handler.create_refresh_token(user.user_id)

    # 리프레시 토큰 저장
    auth_handler.save_token(db, user.user_id, refresh_token)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)

############################################################################################
######################################## 토큰 재발급 ########################################
############################################################################################

@exception_handler
@auth_router.post("/refresh")
def refresh(access_token: str = Header(None), refresh_token: str = Header(None), db: Session = Depends(get_db)):
    if not access_token or not refresh_token:
        raise HTTPException(status_code=400, detail="토큰이 누락되었습니다")

    try:
        access_payload = auth_handler.decode_token(access_token, refresh=True)
        user_id = access_payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="토근이 유효하지 않습니다")
    except Exception as e:
        raise HTTPException(status_code=401, detail="토근이 유효하지 않습니다")

    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="유저를 찾을 수 없습니다")

    valid_refresh_token = auth_handler.get_refreshtoken(db, refresh_token)
    
    if valid_refresh_token.user_id != user.user_id:
        raise HTTPException(status_code=401, detail="토근이 유효하지 않습니다")

    new_access_token =auth_handler.create_access_token(user.user_id)
    new_refresh_token = auth_handler.create_refresh_token(user.user_id)

    auth_handler.delete_token(db, refresh_token)
    
    auth_handler.save_token(db, user.user_id, new_refresh_token)
    return {"access_token": new_access_token, "refresh_token": new_refresh_token}

############################################################################################
###################################### 사용자 로그아웃 ######################################
############################################################################################

@exception_handler
@auth_router.post("/logout")
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    refresh_token = db.query(RefreshToken).filter(RefreshToken.user_id == user.user_id).first()
    
    if not refresh_token:
        raise HTTPException(status_code=404, detail="리프레시 토큰을 찾을 수 없습니다")
    
    auth_handler.delete_token(db, refresh_token.token)

    return JSONResponse(content={"message": "로그아웃 되었습니다"})