from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session
from jose import JWTError, jwt, ExpiredSignatureError
from database import get_db
from models import User, RefreshToken
from . import password_utils
from dotenv import load_dotenv
from datetime import datetime, timedelta
import os

## 토큰 생성 함수 ##
class AuthHandler:
    load_dotenv()
    def __init__(self, secret_key = os.getenv('your_Secret_Key'), 
                 algorithm = os.getenv('algorithm'),
                 access_token_expire_minutes = int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES')),
                 refresh_token_expire_days = int(os.getenv('REFRESH_TOKEN_EXPIRE_DAYS'))):
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.access_token_expire_minutes = access_token_expire_minutes
        self.refresh_token_expire_days = refresh_token_expire_days

    ## 토큰 인코딩 ##
    def encode_token(self, user_id: int, expires_delta: timedelta) -> str:
        encode_payload = {
            'sub': str(user_id),
            'iat': datetime.utcnow(),
            'exp': datetime.utcnow() + expires_delta
        }
        return jwt.encode(encode_payload, self.secret_key, algorithm=self.algorithm)
    
    ## 토큰 디코딩 ##
    def decode_token(self, token: str, refresh: bool = False,db: Session = Depends(get_db)) -> dict:
        try:
            decode_payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return decode_payload
        except ExpiredSignatureError:
            if refresh:
                decode_payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm], options={'verify_exp': False})
                self.update_last_used_at(db, token)
                return decode_payload
            else:
                raise HTTPException(status_code=401, detail="토큰이 만료되었습니다")
        except JWTError:
            raise HTTPException(status_code=401, detail="토큰이 유효하지 않습니다")
   
    ## 엑세스 토큰 생성 ##
    def create_access_token(self, user_id: int) -> str:
        return self.encode_token(user_id, timedelta(minutes=self.access_token_expire_minutes))
    
    ## 리프레쉬 토큰 생성 ##
    def create_refresh_token(self, user_id: int) -> str:
        return self.encode_token(user_id, timedelta(days=self.refresh_token_expire_days))
    
    ## 리프레시 토큰 마지막 사용 시간 업데이트 ##
    def update_last_used_at(self, db: Session, token: str):

        refresh_token = db.query(RefreshToken).filter(RefreshToken.token == token).first()
    
        if refresh_token:
            refresh_token.last_used_at = datetime.utcnow()
            db.commit()
            return refresh_token
        else:
            raise HTTPException(status_code=404, detail="리프레시 토큰을 찾을 수 없습니다")
    
    ## 토큰 DB저장 ##
    def save_token(self, db: Session, user_id: int, token: str, expires_at: datetime = None):
        if expires_at is None:
            expires_at = datetime.utcnow() + timedelta(days=self.refresh_token_expire_days)

        refresh_token = RefreshToken(user_id=user_id, token=token, expires_at=expires_at,
                                         last_used_at=None)
        db.add(refresh_token)
        db.commit()
        db.refresh(refresh_token)
        return refresh_token
        
    ## DB에서 사용가능한 리프레시 토큰 조회 ##
    def get_refreshtoken(self, db: Session, token: str) -> RefreshToken:
        refresh_token = db.query(RefreshToken).filter(RefreshToken.token == token).first()
        if not refresh_token:
            raise HTTPException(status_code=401, detail="토근이 유효하지 않습니다")
        
        if refresh_token.expires_at < datetime.utcnow():
            raise HTTPException(status_code=401, detail="토근이 유효하지 않습니다")
        
        return refresh_token

    ## 토큰 DB 삭제 ##
    def delete_token(self, db: Session, token: str):
        refresh_token = db.query(RefreshToken).filter(RefreshToken.token == token).first()
        if refresh_token:
            db.delete(refresh_token)
            db.commit()

auth_handler = AuthHandler()
authorization = APIKeyHeader(name="Authorization")

## 사용자 조회 ##
def get_current_user(bearer_token: str = Depends(authorization), db: Session = Depends(get_db)) -> User:

    if not bearer_token:
        raise HTTPException(status_code=401, detail="인증 정보가 없습니다")
    if not bearer_token.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer 토큰이 필요합니다")
    
    token = bearer_token.split(" ")[1]

    try:
        payload = auth_handler.decode_token(token)
        if not payload:
            raise HTTPException(status_code=401, detail="토큰이 유효하지 않습니다")
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
        user = user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
        
        return user
    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="토근이 유효하지 않습니다")

    except HTTPException as e:
        raise e
    
    except Exception as e:
        raise HTTPException(status_code=403, detail=f"예상치 못한 오류가 발생했습니다: {str(e)}")

## 사용자 마지막 로그인 시간 업데이트 ##
def update_last_login(db: Session, user_id: int):
    user = db.query(User).filter(User.user_id == user_id).first()
    if user:
        user.last_login = datetime.utcnow()
        db.commit()
        return user
    else:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")