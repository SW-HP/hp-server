from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import desc

from models import User, AssistantThread, TrainingProgram, TrainingCycle, ExerciseDetail, ExerciseSet, BodyMeasurementRecord
import os, json
from openai import OpenAIError

assistant_exercise_designer_id = os.getenv("ASSISTANT_EXERCISE_DESIGNER_ID")

def estimate_body_fat_percentage(weight_kg: float, height_cm: float, age: int, gender: str = "male") -> float:
    """
    Seong et al. (2017) 최종 모델 1 기반 한국인 대상 BMI 기반 체지방률 추정 공식
    :param weight_kg: 체중 (kg)
    :param height_cm: 신장 (cm)
    :param age: 나이 (만 나이 기준)
    :param gender: 'male' 또는 'female'
    :return: 체지방률 (%)
    본 시스템의 실험에서는 r^2 = 0.656, mae 3.48, mse 16.43, rmse 4.05로 나타났습니다.
    """
    if None in (weight_kg, height_cm, age, gender):
        raise ValueError("모든 인자를 입력해야 합니다.")
    
    gender = gender.lower()
    if gender not in ("male", "female"):
        raise ValueError("gender는 'male' 또는 'female'만 허용됩니다.")
    
    sex = 1 if gender == 'male' else 0

    # BMI 계산
    height_m = height_cm / 100
    bmi = weight_kg / (height_m ** 2)

    # 성별 상수 계산
    constant = 54.811 * sex + 66.622 * (1 - sex)

    # 체지방률 계산 (최종 모델 1)
    body_fat_percentage = constant + 0.010 * age - 956.110 / bmi + 3864.956 / (bmi ** 2)

    return round(body_fat_percentage, 2)

def estimate_appendicular_skeletal_muscle_mass(weight_kg: float, waist_circum_cm: float, calf_circum_cm: float, height_cm: float, gender: str = "male") -> float:
    """
    Kawakami et al. (2021) 사지 골격근량(ASM) 추정 공식
    :param weight_kg: 체중 (kg)
    :param waist_circum_cm: 허리둘레 (cm)
    :param calf_circum_cm: 종아리둘레 (cm)
    :param height_cm: 신장 (cm)
    :param gender: 'male' 또는 'female'
    :return: 사지 골격근량 ASM (kg)
    본 시스템의 실험에서는 r^2 = -0.334?, mae 2.02, mse 5.63, rmse 2.374로 나타났습니다.
    """
    if None in (weight_kg, waist_circum_cm, calf_circum_cm, height_cm, gender):
        raise ValueError("모든 인자를 입력해야 합니다.")
    
    sex = 1 if gender.lower() == 'male' else 0

    asm = 2.955 * sex + 0.255 * weight_kg - 0.130 * waist_circum_cm + 0.308 * calf_circum_cm + 0.081 * height_cm - 11.897
    return round(asm, 2)

def estimate_smm_lee(weight_kg: float, height_cm: float, age: int, gender: str = "male", race: str = "asian") -> float:
    """
    Lee et al. (2000) 사지 골격근량(ASM) 추정 공식
    ASM = 0.244 * weight_kg + 7.8 * height_m + 6.6 * sex - 0.098 * age + race_adjustment - 3.3
    """
    if None in (weight_kg, height_cm, age, gender, race):
        raise ValueError("모든 인자를 입력해야 합니다.")
    
    sex = 1 if gender.lower() == 'male' else 0

    race_mapping = {"asian": 1.2, "african_american": 1.4, "white": 0, "hispanic": 0}
    race_adj = race_mapping.get(race.lower(), 0)

    height_m = height_cm / 100

    # ASM 계산
    asm = 0.244 * weight_kg + 7.8 * height_m + 6.6 * sex - 0.098 * age + race_adj - 3.3
    return round(asm, 2)

def calculate_smi(asm_kg: float, height_cm: float) -> float:
    """
    SMI (kg/m^2) 계산
    """
    height_m = height_cm / 100
    smi = asm_kg / (height_m ** 2)
    return round(smi, 2)

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
            .filter(AssistantThread.thread_id == thread_id)
            .first()
        )

        if not user:
            return {"status": "failed", "message": "사용자를 찾을 수 없습니다."}

        # 최신 프로그램 조회
        program = (
            db.query(TrainingProgram)
            .filter(TrainingProgram.user_id == user.user_id)
            .order_by(desc(TrainingProgram.created_at))
            .options(
                joinedload(TrainingProgram.cycles),
                joinedload(TrainingProgram.exercise_sets).joinedload(ExerciseSet.details)
            )
            .first()
        )

        if not program:
            return {"status": "failed", "message": "운동 프로그램이 존재하지 않습니다."}

        # 등록 로직과 동일한 구조로 포맷 구성
        cycles_data = []
        for cycle in program.cycles:
            sets_data = []
            # cycle_id에 해당하는 세트만 추출
            related_sets = [s for s in program.exercise_sets if s.cycle_id == cycle.id]
            for ex_set in related_sets:
                details_data = [
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

                sets_data.append({
                    "focus_area": ex_set.focus_area,
                    "exercises": details_data
                })

            cycles_data.append({
                "day_index": cycle.day_index,
                "exercise_type": cycle.exercise_type,
                "sets": sets_data
            })

        program_data = {
            "program_id": program.id,
            "training_cycle_length": program.training_cycle_length,
            "constraints": program.constraints,
            "notes": program.notes,
            "cycles": cycles_data
        }

        return {"status": "success", "data": program_data}

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
                # 몸무게 추가되어야함.
                "weight": user.user_body_profile.weight,
                "body_fat_percentage": estimate_body_fat_percentage(
                    user.user_body_profile.weight,
                    user.user_body_profile.height,
                    user.user_body_profile.user_age,
                    user.user_body_profile.gender
                ),
            }
        }

    except SQLAlchemyError as e:
        return {"status": "failed", "message": f"데이터베이스 오류가 발생했습니다: {str(e)}"}
    except Exception as e:
        return {"status": "failed", "message": f"예상치 못한 오류가 발생했습니다: {str(e)}"}

def generate_user_train_program(db: Session, thread_id: str, user_request: str="운동 프로그램을 추천해줘"):
    try:
        from assistant import client
        thread = client.beta.threads.create()

        user = db.query(User).join(AssistantThread).filter(AssistantThread.thread_id == thread_id).first()
        record = (
            db.query(BodyMeasurementRecord)
            .filter(BodyMeasurementRecord.user_id == user.user_id)
            .order_by(desc(BodyMeasurementRecord.recoded_at))
            .first()
        )

        response = client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=user_request,
            metadata={"ID": str(thread.id), "운동목적": str(user.goals)}
        )

        from assistant import ExerciseDesignerHandler, __EXERCISE_DESIGNER_INSTRUCTIONS__
        with client.beta.threads.runs.stream(
            thread_id=thread.id,
            assistant_id=assistant_exercise_designer_id,
            instructions=__EXERCISE_DESIGNER_INSTRUCTIONS__,
            event_handler=ExerciseDesignerHandler(db, thread.id),
        ) as stream:
            stream.until_done()
        stream.close()
        final_messages = stream.get_final_messages()

        if not final_messages:
            raise RuntimeError("스트림에서 수신된 메시지가 없습니다.")

        program = json.loads(final_messages[0].content[0].text.value)

        # print("Program generated:", program)  # 디버깅 추가

        new_program = TrainingProgram(
            user_id=user.user_id,
            training_cycle_length=program["training_cycle_length"],
            constraints=json.dumps(program["constraints"], ensure_ascii=False),
            notes=program["notes"]
        )
        db.add(new_program)
        db.commit()
        db.refresh(new_program)

        # print("Program saved with ID:", new_program.id)  # 저장 확인 디버깅 추가

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

        # #디버깅 추가 저장된 DB 순회하여 확인
        # for cycle in new_program.cycles:
        #     print(f"Cycle ID: {cycle.id}, Day Index: {cycle.day_index}, Exercise Type: {cycle.exercise_type}")
        #     for ex_set in cycle.exercise_sets:
        #         print(f"  Set ID: {ex_set.id}, Focus Area: {ex_set.focus_area}")
        #         for detail in ex_set.details:
        #             print(f"    Detail ID: {detail.id}, Name: {detail.name}, Sets: {detail.sets}, Reps: {detail.reps}")

        client.beta.threads.delete(thread.id)
        
        return {"status": "Message executed", "content": program}

    except OpenAIError as e:
        return {"status": "failed", "message": f"OpenAI API 오류가 발생했습니다: {str(e)}"}

    except SQLAlchemyError as e:
        db.rollback()
        return {"status": "failed", "message": f"데이터베이스 오류가 발생했습니다: {str(e)}"}
    except Exception as e:
        db.rollback()
        return {"status": "failed", "message": f"예상치 못한 오류가 발생했습니다: {str(e)}"}