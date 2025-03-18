from passlib.context import CryptContext

## 비밀번호 해싱 설정 ##
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

## 비밀번호 해시화 ##
def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

## 일반 비밀번호와 해시화된 비밀번호 확인(검증) ##
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)