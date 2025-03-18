from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.exc import SQLAlchemyError, IntegrityError, DataError, InvalidRequestError, NoResultFound, MultipleResultsFound, OperationalError
from fastapi import HTTPException
from requests import Session
from dotenv import load_dotenv 
import os



## DB 연결 ##
load_dotenv(override=True)
user = os.getenv("DB_USER")     # "first"
passwd = os.getenv("DB_PASSWORD") # "Qwer1234!"
host = os.getenv("DB_HOST")     # "127.0.0.1"
port = os.getenv("DB_PORT")     # "3306"
db = os.getenv("DB_NAME")       # "hptest"


DB_URL = f'mysql+pymysql://{user}:{passwd}@{host}:{port}/{db}?charset=utf8'
print(DB_URL)
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
    with engine.connect() as connection:
        print("데이터베이스에 연결되었습니다.")
        
        # 쿼리 실행 예시
        query = "SELECT * FROM table_name LIMIT 5"
        result = pd.read_sql(query, connection)
        
        # 결과 출력
        print(result)
        
except Exception as e:
    print("데이터베이스 연결 실패:", e)





## 예외 처리 함수 ##

def exception_handler(func):
    def wrapper(*args, **kwargs):
        for arg in args:
            if isinstance(arg, Session):
                db = arg
                break
        try:
            return func(*args, **kwargs)
        except SQLAlchemyError as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f" 데이터베이스 오류입니다. : {e}")
        except IntegrityError as e:
            db.rollback()
            raise HTTPException(status_code=400, detail=f" 데이터베이스 무결성 오류입니다.: {e}")
        except DataError as e:
            db.rollback()
            raise HTTPException(status_code=400, detail=f" 잘못된 데이터 입력입니다. : {e}")  
        except InvalidRequestError as e:
            db.rollback()
            raise HTTPException(status_code=400, detail=f" 잘못된 요청입니다. : {e}")
        except NoResultFound as e:
            db.rollback()
            raise HTTPException(status_code=404, detail=f" 결과를 찾을 수 없습니다. : {e}")
        except MultipleResultsFound as e:
            db.rollback()
            raise HTTPException(status_code=400, detail=f" 여러 결과가 반환되었습니다. : {e}")
        except OperationalError as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f" 데이터베이스 연결 오류입니다. : {e}")
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f" 알 수 없는 오류가 발생하였습니다. : {e}")
    return wrapper
        