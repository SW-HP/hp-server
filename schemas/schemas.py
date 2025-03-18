from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import Optional, List
from datetime import datetime
import re

## 사용자 회원가입 ##
class UserCreate(BaseModel):
    user_name: str
    email: EmailStr = Field(..., description="이메일")
    user_password: str = Field(..., min_length=8, description="최소 8자, 하나의 문자, 숫자, 특수문자 포함")
    phone_number: str = Field(..., description="휴대폰 번호")
    user_birth: datetime = Field(..., description="생년월일")
    
    class Config:
        from_attributes = True

    @field_validator("user_password")
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("비밀번호는 최소 8자 이상이어야 합니다.")
        if not any(char.isdigit() for char in v):
            raise ValueError("비밀번호는 최소 하나의 숫자를 포함해야 합니다.")
        if not any(char.isupper() for char in v):
            raise ValueError("비밀번호는 최소 하나의 대문자를 포함해야 합니다.")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError('비밀번호에는 특수문자가 포함되어야 합니다.')
        return v
    
    @field_validator('email')
    def validate_email(cls, v):
        if not v:
            raise ValueError("이메일을 입력해주세요.")
        return v

    @field_validator('phone_number')
    def validate_phone_number(cls, v):
        phone_regex = r"^010-\d{4}-\d{4}$"
        if not re.fullmatch(phone_regex, v):
            raise ValueError("휴대폰 번호는 010-xxxx-xxxx 형식이어야 합니다.")
        return v
    
    @field_validator('user_birth')
    def validate_birth(cls, v):
        if v >= datetime.now():
            raise ValueError('생년월일은 현재 날짜 이전이어야 합니다.')
        return v


## 사용자 정보 조회 ##
class UserResponse(BaseModel):
    user_name: str
    user_password: str
    phone_number: Optional[str] = None
    email: Optional[str] = None

    class Config:
        from_attributes = True

## 사용자 정보 수정 ##
class UserUpdate(BaseModel):
    user_name: Optional[str] = None
    user_password: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[str] = None

## 토큰 조회 ##
class TokenResponse(BaseModel): 
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

## 사용자 회원가입 반환 ##
class UserRegister(BaseModel):
    user_name: str
    phone_number: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: str = "bearer"

## 유저 체형 정보 ##
class UserBioBase(BaseModel):
    user_age: int
    gender: str
    body_height: float
    body_weight: float

## 유저 로그인 정보 ##
class Login(BaseModel):
    identifier: str  
    password: str
    
    @field_validator("identifier")
    def validate_identifier(cls, v):
        email_regex = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        if re.fullmatch(email_regex, v):
            return {"type": "email", "value": v}
        
        phone_regex = r"^010-?\d{4}-?\d{4}$"
        if re.fullmatch(phone_regex, v):
            normalized_phone = v.replace("-", "") 
            return {"type": "phone_number", "value": normalized_phone}  

        # 형식이 잘못된 경우 예외 발생
        raise ValueError("identifier는 유효한 이메일 또는 전화번호여야 합니다.")

class UserBioCreate(UserBioBase):
    pass

class UserBioUpdate(UserBioBase):
    pass

class UserBioOut(UserBioBase):
    user_id: int
    body_fat_percentage: float
    body_muscle_mass: float
    body_bone_density: float