from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import SQLAlchemyError
from models import User, AssistantThread, TrainingProgram, TrainingCycle, ExerciseDetail, ExerciseSet, BodyMeasurementRecord
import math

# 아래 두 추정 함수는 신체 측정값을 기반으로 체지방률과 골격근량을 추정하는 함수입니다.
# 각각의 함수는 신체 치수를 입력받아 계산된 값을 반환합니다.

def estimate_body_fat_percentage(height, neck_circumference, waist_circumference):
    height_in = height / 2.54
    neck_in = neck_circumference / 2.54
    waist_in = waist_circumference / 2.54

    bf_percentage = 86.010 * math.log10(waist_in - neck_in) - 70.041 * math.log10(height_in) + 36.76
    return bf_percentage

def estimate_skeletal_muscle_mass(height, thigh_circumference, calf_circumference, forearm_circumference):
    smm = 0.244 * thigh_circumference + 0.098 * calf_circumference + 0.200 * forearm_circumference + 0.115 * height - 10.5
    return smm

def get_user_train_program(db: Session, thread_id: str, id: str=None):
    """
    주어진 thread_id에 해당하는 사용자의 운동 프로그램을 가져옵니다.
    JSON 형태로 반환됩니다.

    :param db: 데이터베이스 세션
    :param thread_id: AssistantThread의 thread_id
    :return: 운동 프로그램 데이터
    """
    try:
        if id is not None:
            thread_id = id
        user = (
            db.query(User)
            .join(AssistantThread)
            .options(
                joinedload(User.training_programs)
                .joinedload(TrainingProgram.cycles),
                joinedload(User.training_programs)
                .joinedload(TrainingProgram.exercise_sets)
                .joinedload(TrainingProgram.exercise_sets.of_type(TrainingProgram))
                .joinedload("exercise_sets.details")
            )
            .filter(AssistantThread.thread_id == thread_id)
            .first()
        )

        if not user:
            return {"status": "failed", "message": "사용자를 찾을 수 없습니다."}

        training_data = []
        for program in user.training_programs:
            cycles = [
                {"day_index": cycle.day_index, "exercise_type": cycle.exercise_type}
                for cycle in program.cycles
            ]

            exercise_sets = []
            for ex_set in program.exercise_sets:
                details = [
                    {
                        "name": detail.name,
                        "sets": detail.sets,
                        "reps": detail.reps,
                        "unit": detail.unit,
                        "weight_type": detail.weight_type,
                        "weight_value": detail.weight_value,
                        "rest": detail.rest
                    }
                    for detail in ex_set.details
                ]

                exercise_sets.append({
                    "set_key": ex_set.set_key,
                    "focus_area": ex_set.focus_area,
                    "details": details
                })

            training_data.append({
                "program_id": program.id,
                "training_cycle_length": program.training_cycle_length,
                "constraints": program.constraints,
                "notes": program.notes,
                "cycles": cycles,
                "exercise_sets": exercise_sets
            })

        return {"status": "success", "data": training_data}

    except SQLAlchemyError as e:
        db.rollback()
        return {"status": "failed", "message": f"데이터베이스 오류가 발생했습니다: {str(e)}"}
    except Exception as e:
        db.rollback()
        return {"status": "failed", "message": f"예상치 못한 오류가 발생했습니다: {str(e)}"}
    
# JSON 형태를 DB에 저장하는 함수
def save_user_train_program(db: Session, thread_id: str, training_data: dict):
    """
    주어진 사용자의 운동 프로그램을 DB에 저장합니다.

    :param db: 데이터베이스 세션
    :param user: User 객체
    :param training_data: 운동 프로그램 데이터 (JSON 형태)
    :return: 저장된 운동 프로그램 데이터
    """
    try:
        # 기존 프로그램 삭제
    # 기존 프로그램 삭제
        user = db.query(User).join(AssistantThread).filter(AssistantThread.thread_id == thread_id).first()
        db.query(TrainingProgram).filter(TrainingProgram.user_id == user.user_id).delete()
        db.commit()

        # training_data는 dict이므로 반복문 필요 없음
        program = training_data

        new_program = TrainingProgram(
            user_id=user.user_id,
            training_cycle_length=program["training_cycle_length"],
            constraints=program["constraints"],  # 이게 JSONField 혹은 문자열이어야 함
            notes=program["notes"]
        )
        db.add(new_program)
        db.commit()
        db.refresh(new_program)

        for cycle in program["cycles"]:
            new_cycle = TrainingCycle(
                program_id=new_program.id,
                day_index=cycle["day_index"],
                exercise_type=cycle["exercise_type"]
            )
            db.add(new_cycle)
            db.commit()
            db.refresh(new_cycle)

            for ex_set in cycle["sets"]:
                new_ex_set = ExerciseSet(
                    program_id=new_program.id,
                    cycle_id=new_cycle.id,
                    focus_area=ex_set["focus_area"]
                )
                db.add(new_ex_set)
                db.commit()
                db.refresh(new_ex_set)

                for detail in ex_set["exercises"]:
                    new_detail = ExerciseDetail(
                        set_id=new_ex_set.id,
                        name=detail["name"],
                        sets=detail["sets"],
                        reps=detail["reps"],
                        unit=detail["unit"],
                        weight_type=detail.get("weight_type"),
                        weight_value=detail.get("weight_value"),
                        rest=detail["rest"]
                    )
                    db.add(new_detail)
                    db.commit()
                    db.refresh(new_detail)

        return {"status": "success", "message": "운동 프로그램이 성공적으로 저장되었습니다."}

    except SQLAlchemyError as e:
        db.rollback()
        return {"status": "failed", "message": f"데이터베이스 오류가 발생했습니다: {str(e)}"}
    except Exception as e:
        db.rollback()
        return {"status": "failed", "message": f"예상치 못한 오류가 발생했습니다: {str(e)}"}


def get_body_measurement_records(db: Session, thread_id: str):
    try:
        user = db.query(User).join(AssistantThread).filter(AssistantThread.thread_id == thread_id).first()
        if not user:
            return {"status": "failed", "message": "사용자를 찾을 수 없습니다."}
        record = db.query(BodyMeasurementRecord).filter(BodyMeasurementRecord.user_id == user.user_id).first()
        if not record:
            return {"status": "failed", "message": "신체 측정 기록을 찾을 수 없습니다."}
        return {
            "status": "success",
            "data": {
                "user_id": user.user_id,
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
                "ankle_left_circumference": record.ankle_left_circumference,
                
            }
        }

    except SQLAlchemyError as e:
        return {"status": "failed", "message": f"데이터베이스 오류가 발생했습니다: {str(e)}"}
    except Exception as e:
        return {"status": "failed", "message": f"예상치 못한 오류가 발생했습니다: {str(e)}"}

def call_program_recommendation_api(db: Session, thread_id: str, body_measurement_data: dict):
    try:
        pass
    except SQLAlchemyError as e:
        db.rollback()
        return {"status": "failed", "message": f"데이터베이스 오류가 발생했습니다: {str(e)}"}
    except Exception as e:
        db.rollback()
        return {"status": "failed", "message": f"예상치 못한 오류가 발생했습니다: {str(e)}"}