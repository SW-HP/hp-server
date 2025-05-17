from fastapi import APIRouter, HTTPException, UploadFile, status, File, Depends, Header
from fastapi.responses import JSONResponse

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload
import requests
import os

from datetime import datetime, timedelta

from dotenv import load_dotenv
from models import User, BodyMeasurementRecord, AssistantThread, TrainingProgram, UserBodyProfile
from schemas import BodyMeasurementRecordSchema
from utils import get_current_user
from database import get_db
load_dotenv()

ml_host = os.getenv("ML_HOST")
ml_port = os.getenv("ML_PORT")

recovery_router = APIRouter()

def calculate_mean_std(records, field, actual_height):
    values = []
    for record in records:
        record_value = getattr(record, field, None)
        record_height = getattr(record, 'height', None)
        if record_value is not None and record_height:
            factor = actual_height / record_height if record_height else 1.0
            values.append(record_value * factor)
    if not values:
        return None, None
    mean_val = sum(values) / len(values)
    variance = sum((v - mean_val) ** 2 for v in values) / len(values)
    std_dev = variance ** 0.5
    return mean_val, std_dev

import csv
import os
from fastapi.responses import FileResponse
from functions import estimate_body_fat_percentage, estimate_appendicular_skeletal_muscle_mass, estimate_smm_lee, calculate_smi

# 1번~12번 유저 체지방률, 사지근골격량 추출 및 파일로 저장
@recovery_router.get('/BFandASMestimation')
def body_fat_and_asm_estimation(db: Session = Depends(get_db)):
    try:
        user_stats = []
        for user_id in range(1, 13):
            user = db.query(User).filter(User.user_id == user_id).first()
            if not user or not user.user_body_profile or not user.user_body_profile.height:
                continue

            records = db.query(BodyMeasurementRecord).filter(BodyMeasurementRecord.user_id == user_id).order_by(BodyMeasurementRecord.recoded_at.desc()).limit(5).all()
            if not records:
                continue

            row = {"user_id": user_id}
            for record in records:
                body_fat_percentage = estimate_body_fat_percentage(user.user_body_profile.weight, user.user_body_profile.height, user.user_body_profile.user_age, 'male')
                asm = estimate_appendicular_skeletal_muscle_mass(user.user_body_profile.weight, record.waist_circumference, record.calf_left_circumference, user.user_body_profile.height, 'male')
                smm_heymsfield = estimate_smm_lee(user.user_body_profile.weight, user.user_body_profile.height, user.user_body_profile.user_age)
                smi = calculate_smi(asm, 175)

                row["body_fat_percentage"] = round(body_fat_percentage, 2) if body_fat_percentage is not None else "데이터 없음"
                row["asm"] = round(asm, 2) if asm is not None else "데이터 없음"
                row["smm_heymsfield"] = round(smm_heymsfield, 2) if smm_heymsfield is not None else "데이터 없음"
                row["smi"] = round(smi, 2) if smi is not None else "데이터 없음"

            user_stats.append(row)

        # CSV 저장
        stats_file = "/tmp/body_fat_and_asm_estimation.csv"
        with open(stats_file, mode='w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ["user_id", "body_fat_percentage", "asm", "smm_heymsfield", "smm_janssen", "smi"]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(user_stats)

        return FileResponse(stats_file, filename="body_fat_and_asm_estimation.csv")

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류가 발생했습니다: {str(e)}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"예상치 못한 오류가 발생했습니다: {str(e)}")

@recovery_router.get('/body_measurement_record/batch_statistics')
def batch_body_measurement_statistics(db: Session = Depends(get_db)):
    try:
        user_stats = []
        overall_sums = {}
        overall_counts = {}
        user_overall_means = []

        fields = [
            "height", "left_arm_length", "right_arm_length", "inside_leg_height",
            "shoulder_to_crotch_height", "shoulder_breadth", "head_circumference",
            "chest_circumference", "waist_circumference", "hip_circumference",
            "wrist_right_circumference", "bicep_right_circumference", "forearm_right_circumference",
            "thigh_left_circumference", "calf_left_circumference", "ankle_left_circumference"
        ]

        for user_id in range(1, 13):
            user = db.query(User).filter(User.user_id == user_id).first()
            if not user or not user.user_body_profile or not user.user_body_profile.height:
                continue

            actual_height = user.user_body_profile.height
            records = db.query(BodyMeasurementRecord).filter(BodyMeasurementRecord.user_id == user_id).order_by(BodyMeasurementRecord.recoded_at.desc()).limit(5).all()
            if not records:
                continue

            row = {"user_id": user_id}
            user_means = []

            for field in fields:
                mean, std = calculate_mean_std(records, field, actual_height)
                if mean is not None:
                    row[f"{field}_mean"] = round(mean, 2)
                    if field != "height":
                        row[f"{field}_std"] = round(std, 2)
                        user_means.append(mean)
                        overall_sums[field] = overall_sums.get(field, 0) + mean
                        overall_counts[field] = overall_counts.get(field, 0) + 1
                    else:
                        row[f"{field}_mean"] = round(mean, 2)
                else:
                    row[f"{field}_mean"] = "데이터 없음"
                    if field != "height":
                        row[f"{field}_std"] = "데이터 없음"

            if user_means:
                user_overall_mean = sum(user_means) / len(user_means)
                row["overall_mean"] = round(user_overall_mean, 2)
                user_overall_means.append(user_overall_mean)

            user_stats.append(row)

        # 사용자별 통계 CSV 저장
        user_stats_file = "/tmp/body_measurement_user_stats.csv"
        with open(user_stats_file, mode='w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ["user_id"] + [f"{f}_mean" for f in fields] + [f"{f}_std" for f in fields if f != "height"] + ["overall_mean"]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(user_stats)

        # 부위별 전체 평균 계산
        overall_aggregates = []
        for field in fields:
            if field == "height":
                continue
            if field in overall_sums:
                overall_mean = overall_sums[field] / overall_counts[field]
                overall_aggregates.append({"field": field, "overall_mean": round(overall_mean, 2)})

        # 부위별 전체 평균 CSV 저장
        overall_file = "/tmp/body_measurement_overall_aggregates.csv"
        with open(overall_file, mode='w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=["field", "overall_mean"])
            writer.writeheader()
            writer.writerows(overall_aggregates)

        # 최종 평가 리포트 생성
        average_user_mean = sum(user_overall_means) / len(user_overall_means) if user_overall_means else 0
        report_file = "/tmp/body_measurement_report.txt"
        with open(report_file, "w", encoding="utf-8") as report:
            report.write("측정 평가 리포트\n")
            report.write(f"총 사용자 수: {len(user_stats)}명\n")
            report.write(f"평균 부위 수: {len(fields) - 1}개\n")
            report.write(f"전체 사용자 평균 측정치: {round(average_user_mean, 2)}\n")
            if average_user_mean >= 80:
                grade = "우수"
            elif average_user_mean >= 60:
                grade = "양호"
            elif average_user_mean >= 40:
                grade = "보통"
            else:
                grade = "불량"
            report.write(f"시스템 정확도 평가: {grade}\n")

        # 반환 (파일 다운로드 링크 예시 하나만 반환)
        # return FileResponse(user_stats_file, filename="body_measurement_user_stats.csv")
        # return FileResponse(overall_file, filename="body_measurement_overall_aggregates.csv")
        return FileResponse(report_file, filename="body_measurement_report.txt")


    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류가 발생했습니다: {str(e)}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"예상치 못한 오류가 발생했습니다: {str(e)}")
    

# 개인 신체 정보 기입 set (user.user_body_profile)
# 나이, 성별(GenderEnum), 키, 몸무게, 체지방률, 근육량, 부상 이력, 장비 이력 선택 입력
@recovery_router.put('/user_body_profile')
def update_user_body_profile(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    user_age: int = None,
    gender: str = None,
    height: float = None,
    weight: float = None,
    body_fat_percentage: float = None,
    body_muscle_mass: float = None,
    injuries: str = None,
    equipment: str = None
):
    try:
        # 사용자 존재 여부 확인
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다.")

        # 사용자 프로필 가져오기
        user_body_profile = user.user_body_profile
        if not user_body_profile:
            # 프로필이 없으면 새로 생성
            user_body_profile = UserBodyProfile(user_id=user.user_id)
            db.add(user_body_profile)

        # 선택적으로 필드 업데이트
        if user_age is not None:
            user_body_profile.user_age = user_age
        if gender is not None:
            if gender not in ["male", "female"]:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="성별은 'male' 또는 'female'만 허용됩니다.")
            user_body_profile.gender = gender
        if height is not None:
            user_body_profile.height = height
        if weight is not None:
            user_body_profile.weight = weight
        if body_fat_percentage is not None:
            user_body_profile.body_fat_percentage = body_fat_percentage
        if body_muscle_mass is not None:
            user_body_profile.body_muscle_mass = body_muscle_mass
        if injuries is not None:
            user_body_profile.injuries = injuries
        if equipment is not None:
            user_body_profile.equipment = equipment

        # 변경 사항 저장
        db.commit()
        db.refresh(user_body_profile)

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": "사용자 신체 정보가 업데이트되었습니다.",
                "user_body_profile": {
                    "user_id": user_body_profile.user_id,
                    "user_age": user_body_profile.user_age,
                    "gender": user_body_profile.gender.value if user_body_profile.gender else None,  # Enum을 문자열로 변환
                    "height": user_body_profile.height,
                    "weight": user_body_profile.weight,
                    "body_fat_percentage": user_body_profile.body_fat_percentage,
                    "body_muscle_mass": user_body_profile.body_muscle_mass,
                    "injuries": user_body_profile.injuries,
                    "equipment": user_body_profile.equipment
                }
            }
        )
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류가 발생했습니다: {str(e)}")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"예상치 못한 오류가 발생했습니다: {str(e)}")


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
            height=record['height'],
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
                    "height": new_record.height,
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
# 개인 신체기록 전체 삭제
@recovery_router.delete('/body_measurement_record', status_code=status.HTTP_204_NO_CONTENT)
def delete_body_measurement_record(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        # 사용자 존재 여부 확인
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다.")
        
        # 신체 측정 기록 삭제
        records = db.query(BodyMeasurementRecord).filter(BodyMeasurementRecord.user_id == user.user_id).all()
        if not records:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="신체 측정 기록을 찾을 수 없습니다.")
        
        for record in records:
            db.delete(record)
        db.commit()
        
        return JSONResponse(
            status_code=status.HTTP_204_NO_CONTENT,
            content={
                "message": "신체 측정 기록이 삭제되었습니다."
            }
        )
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
        # record = db.query(BodyMeasurementRecord).filter(BodyMeasurementRecord.user_id == user.user_id).first()
        # 가장 마지막 측정 기록 조회
        record = db.query(BodyMeasurementRecord).filter(BodyMeasurementRecord.user_id == user.user_id).order_by(BodyMeasurementRecord.recoded_at.desc()).first()
        if not record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="신체 측정 기록을 찾을 수 없습니다.")
        
        return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "message": "가장 최근의 신체 측정 기록입니다.",
            
            "record": {
                "user_id": record.user_id,
                "recoded_at": record.recoded_at.isoformat(),
                "height": record.height,
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