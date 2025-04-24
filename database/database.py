from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.exc import SQLAlchemyError, IntegrityError, DataError, InvalidRequestError, NoResultFound, MultipleResultsFound, OperationalError
from fastapi import HTTPException
from requests import Session
from dotenv import load_dotenv 
import os

load_dotenv(override=True)
user = os.getenv("DB_USER")
passwd = os.getenv("DB_PASSWORD")
host = os.getenv("DB_HOST")
port = os.getenv("DB_PORT")
db = os.getenv("DB_NAME")


DB_URL = f'mysql+mysqlconnector://{user}:{passwd}@{host}:{port}/{db}?charset=utf8'

## db 연결 방법 정의 ##
engine = create_engine(DB_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False,autoflush=False, bind=engine)
Base = declarative_base()

## db 연결하는 함수 ##
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


try:
    # 연결 시도
    print(DB_URL)
    with engine.connect() as connection:
        print("데이터베이스에 연결되었습니다.")
        
        # 쿼리 실행 예시
        query = "SELECT * FROM table_name LIMIT 5"
        
        # 결과 출력
        print("쿼리 실행 완료")
        
except Exception as e:
    print("데이터베이스 연결 실패:", e)