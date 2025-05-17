import json, os
import traceback

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import desc
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from openai import OpenAIError

from models import  AssistantMessageCreate, AssistantThread, AssistantMessage, User, TrainingProgram, TrainingCycle, ExerciseDetail, ExerciseSet, BodyMeasurementRecord
from database import get_db
from assistant import client, AssistantHandler, ExerciseDesignerHandler, __INSTRUCTIONS__, __EXERCISE_DESIGNER_INSTRUCTIONS__
from utils import get_current_user

assistant_router = APIRouter()

assistant_id = os.getenv("ASSISTANT_ID")
assistant_exercise_designer_id = os.getenv("ASSISTANT_EXERCISE_DESIGNER_ID") # 임시


### 스레드 관리 API ###
#
#    ooooooooooooo oooo                                           .o8 
#    8'   888   `8 `888                                          "888 
#         888       888 .oo.   oooo d8b  .ooooo.   .oooo.    .oooo888 
#         888       888P"Y88b  `888""8P d88' `88b `P  )88b  d88' `888 
#         888       888   888   888     888ooo888  .oP"888  888   888 
#         888       888   888   888     888    .o d8(  888  888   888 
#        o888o     o888o o888o d888b    `Y8bod8P' `Y888""8o `Y8bod88P"
# run state : creating, created, run, interrupt, done

# 스레드 생성
async def create_assistant_thread(user_id: int, db: Session = Depends(get_db)):
    thread = client.beta.threads.create()
    
    assistant_thread = AssistantThread(
        user_id=user_id,
        thread_id=thread.id
    )
    
    db.add(assistant_thread)
    db.commit()
    db.refresh(assistant_thread)
    
    return assistant_thread
    

# 특정 사용자의 스레드 조회
@assistant_router.get("/threads")
async def get_threads_by_user(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    threads = db.query(AssistantThread).filter(AssistantThread.user_id == user.user_id).all()
    if not threads:
        threads = await create_assistant_thread(user.user_id, db)

    return threads
# 스레드 삭제
@assistant_router.delete("/threads")
async def delete_assistant_thread(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    thread = db.query(AssistantThread).filter(AssistantThread.user_id == user.user_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="쓰레드를 찾을 수 없습니다.")

    # OpenAI Thread 삭제 시도
    try:
        client.beta.threads.delete(thread.thread_id)
    except OpenAIError as e:
        # 404 오류인 경우 무시하고 DB만 삭제
        if "No thread found with id" in str(e):
            pass
        else:
            # 그 외 오류는 그대로 리턴
            raise HTTPException(status_code=500, detail="쓰레드 삭제 중 오류가 발생했습니다." + str(e) + str(thread.thread_id))

    # DB 기록 삭제
    db.delete(thread)
    db.commit()
    return {"message": "쓰레드를 삭제했습니다."}
#    ooo        ooooo                                                           
#    `88.       .888'                                                           
#     888b     d'888   .ooooo.   .oooo.o  .oooo.o  .oooo.    .oooooooo  .ooooo. 
#     8 Y88. .P  888  d88' `88b d88(  "8 d88(  "8 `P  )88b  888' `88b  d88' `88b
#     8  `888'   888  888ooo888 `"Y88b.  `"Y88b.   .oP"888  888   888  888ooo888
#     8    Y     888  888    .o o.  )88b o.  )88b d8(  888  `88bod8P'  888    .o
#    o8o        o888o `Y8bod8P' 8""888P' 8""888P' `Y888""8o `8oooooo.  `Y8bod8P'
#                                                           d"     YD           
#                                                           "Y88888P'           

@assistant_router.post("/message")
async def add_and_run_message(message: AssistantMessageCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    thread = db.query(AssistantThread).filter(AssistantThread.user_id == user.user_id).first()
    if not thread:
        thread = await create_assistant_thread(user.user_id, db)
    try:
        if thread.run_state != "None" or thread.run_state in ["thread.run.completed", "thread.run.cancelled"]:
            response = client.beta.threads.messages.create(
                thread_id=thread.thread_id,
                role="user",
                content=message.content
            )
        elif thread.run_state in ["thread.run.failed"]:
            delete_assistant_thread(user, db)
            response = client.beta.threads.messages.create(
                thread_id=thread.thread_id,
                role="user",
                content=message.content
            )
        else:
            return {"status": "Message created but not executed", "content": "죄송합니다. 잠시 후 다시 시도해주세요."}

    except OpenAIError as e:
        return {"status": "Message created but not executed", "content": "죄송합니다. 잠시 뒤 다시 말씀해주세요."}
    except Exception as e:
        return {"status": "Message not created", "content": "죄송합니다. 제가 이해하지 못했어요. 다시 말씀해주시겠어요?"}

    new_message = AssistantMessage(
        thread_id=thread.thread_id,
        sender_type="user",
        content=message.content,
        created_at=datetime.utcnow()
    )
    db.add(new_message)
    db.commit()
    db.refresh(new_message)

    with client.beta.threads.runs.stream(
        thread_id=thread.thread_id,
        assistant_id=assistant_id,
        instructions=__INSTRUCTIONS__,
        event_handler=AssistantHandler(db, thread.thread_id),
    ) as stream:
        stream.until_done()
    latest_message = db.query(AssistantMessage).filter(AssistantMessage.thread_id == thread.thread_id).order_by(desc(AssistantMessage.created_at)).first()

    return {"status": "Message created and executed", "content": latest_message.content}

@assistant_router.get("/messages")
async def get_messages_by_thread(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    thread = db.query(AssistantThread).filter(AssistantThread.user_id == user.user_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="쓰레드를 찾을 수 없습니다.")

    messages = db.query(AssistantMessage).filter(AssistantMessage.thread_id == thread.thread_id).all()
    if not messages:
        return []
    
    return messages

@assistant_router.get("/messages/latest")
async def get_latest_message(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    thread = db.query(AssistantThread).filter(AssistantThread.user_id == user.user_id).first()
    if not thread:
        thread = await create_assistant_thread(user.user_id, db)

    latest_message = db.query(AssistantMessage).filter(AssistantMessage.thread_id == thread.thread_id).order_by(desc(AssistantMessage.created_at)).first()
    if not latest_message:
        raise HTTPException(status_code=404, detail="최신 메세지를 찾을 수 없습니다.")
    
    return latest_message

# # Test용
@assistant_router.post("/temp_message_run")
async def temp_message_run(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        # 임시 쓰레드 생성
        thread = client.beta.threads.create()
        thread_id = db.query(AssistantThread).filter(AssistantThread.user_id == user.user_id).first().thread_id
        
        record = db.query(BodyMeasurementRecord).filter(BodyMeasurementRecord.user_id == user.user_id).order_by(desc(BodyMeasurementRecord.recoded_at)).first()
        # 메시지 실행
        response = client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=f"주 4회, 회당 60분 정도의 운동 프로그램을 설계해줘",
            metadata={
                "ID": str(thread_id),
                "운동목적": str(user.goals),
                "부상이력": str(user.user_body_profile.injuries),
                "사용가능기구": str(user.user_body_profile.equipment),
                "체지방률": str(user.user_body_profile.body_fat_percentage),
                "골격근량": str(user.user_body_profile.body_muscle_mass),
                "체중": str(user.user_body_profile.weight),
                "신장": str(user.user_body_profile.height),
                "나이": str(user.user_body_profile.user_age),
                "길이": str(
                    f"left_arm_length: {record.left_arm_length}, "
                    f"right_arm_length: {record.right_arm_length}, "
                    f"inside_leg_height: {record.inside_leg_height}, "
                    f"shoulder_to_crotch_height: {record.shoulder_to_crotch_height}"
                ),
                "둘레": str(
                    f"shoulder_breadth: {record.shoulder_breadth}, "
                    f"head_circumference: {record.head_circumference}, "
                    f"chest_circumference: {record.chest_circumference}, "
                    f"waist_circumference: {record.waist_circumference}, "
                    f"hip_circumference: {record.hip_circumference}, "
                    f"wrist_right_circumference: {record.wrist_right_circumference}, "
                    f"bicep_right_circumference: {record.bicep_right_circumference}, "
                    f"forearm_right_circumference: {record.forearm_right_circumference}, "
                    f"thigh_left_circumference: {record.thigh_left_circumference}, "
                    f"calf_left_circumference: {record.calf_left_circumference}, "
                    f"ankle_left_circumference: {record.ankle_left_circumference}"
                )
            }
        )

        # 메시지 실행 결과를 스트림으로 처리
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
            # 적절한 에러 처리 또는 사용자 안내
            raise RuntimeError("스트림에서 수신된 메시지가 없습니다.")
        
        program = json.loads(stream.get_final_messages()[0].content[0].text.value)

        new_program = TrainingProgram(
            user_id=user.user_id,
            training_cycle_length=program["training_cycle_length"],
            constraints=json.dumps(program["constraints"], ensure_ascii=False),
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
        client.beta.threads.delete(thread_id)
        return {
            "status": "Message executed",
            "content": json.dumps(json.loads(stream.get_final_messages()[0].content[0].text.value), indent=2, ensure_ascii=False)
        }

    except SQLAlchemyError as e:
        db.rollback()
        return {"status": "failed", "message": f"데이터베이스 오류가 발생했습니다: {str(e)}"}
    except OpenAIError as e:
        return {"status": "failed", "message": f"OpenAI API 오류가 발생했습니다: {str(e)}"}
    except Exception as e:
        return {
            "status": "failed", 
            "message": f"예상치 못한 오류가 발생했습니다.",
            "error": str(e),
            "traceback": traceback.format_exc()
            }
# get user train program to json
@assistant_router.get("/user_train_program")
async def get_complete_user_train_program(
    user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    try:
        # Fetch the user's training program
        # 가장 마지막에 저장된 것 조회
        program = db.query(TrainingProgram).filter(TrainingProgram.user_id == user.user_id).order_by(desc(TrainingProgram.created_at)).first()
        if not program:
            raise HTTPException(status_code=404, detail="사용자의 훈련 프로그램을 찾을 수 없습니다.")

        # Build the response structure
        program_data = {
            "training_cycle_length": program.training_cycle_length,
            "constraints": json.loads(program.constraints),
            "notes": program.notes,
            "cycles": []
        }

        for cycle in program.cycles:
            cycle_data = {
                "day_index": cycle.day_index,
                "exercise_type": cycle.exercise_type,
                "sets": []
            }
            for ex_set in cycle.exercise_sets:
                set_data = {
                    "focus_area": ex_set.focus_area,
                    "exercises": []
                }
                for detail in ex_set.details:
                    detail_data = {
                        "name": detail.name,
                        "sets": detail.sets,
                        "reps": detail.reps,
                        "unit": detail.unit,
                        "weight_type": detail.weight_type,
                        "weight_value": detail.weight_value,
                        "rest": detail.rest
                    }
                    set_data["exercises"].append(detail_data)
                cycle_data["sets"].append(set_data)
            program_data["cycles"].append(cycle_data)

        return program_data

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류가 발생했습니다: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"예상치 못한 오류가 발생했습니다: {str(e)}")