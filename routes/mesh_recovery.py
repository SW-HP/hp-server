from fastapi import APIRouter, HTTPException, UploadFile, status, File, Depends, Header
from fastapi.responses import JSONResponse

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload
import requests
import os

from datetime import datetime, timedelta

from dotenv import load_dotenv
from models import User, BodyMeasurementRecord, AssistantThread, TrainingProgram
from schemas import BodyMeasurementRecordSchema
from utils import get_current_user
from database import get_db
load_dotenv()

ml_host = os.getenv("ML_HOST")
ml_port = os.getenv("ML_PORT")

recovery_router = APIRouter()

@recovery_router.post("/process-image/")
async def process_image(file: UploadFile = File(...), _fov: int = 60, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        user_id = user.user_id
        url = f"http://{ml_host}:{ml_port}/process-image/?_fov={_fov}"
        files = {'file': (file.filename, file.file, file.content_type)}
        headers = {'accept': 'application/json'}

        response = requests.post(url, headers=headers, files=files)

        # if response.status_code != 200:
        #     raise HTTPException(status_code=response.status_code, detail="이미지 처리 중 오류가 발생했습니다")

        # return response.json()
        record = response.json()

        new_record = BodyMeasurementRecord(
            user_id=user_id,
            recoded_at=datetime.utcnow(),
            left_arm_length=record['arm left length'],
            right_arm_length=record['arm right length'],
            inside_leg_height=record['inside leg height'],
            shoulder_to_crotch_height=record['shoulder to crotch height'],
            shoulder_breadth=record['shoulder breadth'],
            head_circumference=record['head circumference'],
            chest_circumference=record['chest circumference'],
            waist_circumference=record['waist circumference'],
            hip_circumference=record['hip circumference'],
            wrist_right_circumference=record['wrist right circumference'],
            bicep_right_circumference=record['bicep right circumference'],
            forearm_right_circumference=record['forearm right circumference'],
            thigh_left_circumference=record['thigh left circumference'],
            calf_left_circumference=record['calf left circumference'],
            ankle_left_circumference=record['ankle left circumference']
        )
        db.add(new_record)
        db.commit()
        db.refresh(new_record)

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={
                "message": "신체 측정 기록이 등록되었습니다.",
                "record": {
                    "user_id": user_id,
                    "recoded_at": new_record.recoded_at.isoformat(),
                    "left_arm_length": new_record.left_arm_length,
                    "right_arm_length": new_record.right_arm_length,
                    "inside_leg_height": new_record.inside_leg_height,
                    "shoulder_to_crotch_height": new_record.shoulder_to_crotch_height,
                    "shoulder_breadth": new_record.shoulder_breadth,
                    "head_circumference": new_record.head_circumference,
                    "chest_circumference": new_record.chest_circumference,
                    "waist_circumference": new_record.waist_circumference,
                    "hip_circumference": new_record.hip_circumference,
                    "wrist_right_circumference": new_record.wrist_right_circumference,
                    "bicep_right_circumference": new_record.bicep_right_circumference,
                    "forearm_right_circumference": new_record.forearm_right_circumference,
                    "thigh_left_circumference": new_record.thigh_left_circumference,
                    "calf_left_circumference": new_record.calf_left_circumference,
                    "ankle_left_circumference": new_record.ankle_left_circumference
                }
            }
        )
    # 데이터베이스 관련 오류 처리
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류가 발생했습니다: {str(e)}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"예상치 못한 오류가 발생했습니다: {str(e)}")
    
# get
@recovery_router.get('/body_measurement_record', response_model=BodyMeasurementRecordSchema)
def get_body_measurement_record(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        # 사용자 존재 여부 확인
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다.")
        
        # 최근 신체 측정 기록 조회
        record = db.query(BodyMeasurementRecord).filter(BodyMeasurementRecord.user_id == user.user_id).first()
        if not record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="신체 측정 기록을 찾을 수 없습니다.")
        
        return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "message": "가장 최근의 신체 측정 기록입니다.",
            
            "record": {
                "user_id": record.user_id,
                "recoded_at": record.recoded_at.isoformat(),
                "left_arm_length": record.left_arm_length,
                "right_arm_length": record.right_arm_length,
                "inside_leg_height": record.inside_leg_height,
                "shoulder_to_crotch_height": record.shoulder_to_crotch_height,
                "shoulder_breadth": record.shoulder_breadth,
                "head_circumference": record.head_circumference,
                "chest_circumference": record.chest_circumference,
                "waist_circumference": record.waist_circumference,
                "hip_circumference": record.hip_circumference,
                "wrist_right_circumference": record.wrist_right_circumference,
                "bicep_right_circumference": record.bicep_right_circumference,
                "forearm_right_circumference": record.forearm_right_circumference,
                "thigh_left_circumference": record.thigh_left_circumference,
                "calf_left_circumference": record.calf_left_circumference,
                "ankle_left_circumference": record.ankle_left_circumference
            }
        }
    )
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류가 발생했습니다: {str(e)}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"예상치 못한 오류가 발생했습니다: {str(e)}")