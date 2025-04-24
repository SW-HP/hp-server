from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from models import User, AssistantThread

def get_user_train_program(db: Session, thread_id):
    try:
        user = db.query(User).join(AssistantThread).filter(AssistantThread.thread_id == thread_id).first()
        if not user:
            return {"status": "failed", "message": "사용자를 찾을 수 없습니다."}
        
    except SQLAlchemyError as e:
        db.rollback()
        return {"status": "failed", "message": f"데이터베이스 오류가 발생했습니다: {str(e)}"}
    except Exception as e:
        db.rollback()
        return {"status": "failed", "message": f"예상치 못한 오류가 발생했습니다: {str(e)}"}