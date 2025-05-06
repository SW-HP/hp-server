import json, os
import traceback

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import desc
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from openai import OpenAIError

from models import  AssistantMessageCreate, AssistantThread, AssistantMessage, User, TrainingProgram, TrainingCycle, ExerciseDetail, ExerciseSet
from database import get_db
from assistant import client, AssistantHandler, ExerciseDesignerHandler, __INSTRUCTIONS__, __EXERCISE_DESIGNER_INSTRUCTIONS__
from utils import get_current_user

assistant_router = APIRouter()

assistant_id = os.getenv("ASSISTANT_ID")
assistant_exercise_designer_id = os.getenv("ASSISTANT_EXERCISE_DESIGNER_ID")


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
    client.beta.threads.delete(thread.thread_id)
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

# Test용
@assistant_router.post("/temp_message_run")
async def temp_message_run(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        # 함수 시간 측정 시작
        start_time = datetime.now()
        elapsed_times = {}

        # 임시 쓰레드 생성
        thread = client.beta.threads.create()
        thread_id = db.query(AssistantThread).filter(AssistantThread.user_id == user.user_id).first().thread_id

        # 메시지 실행
        response = client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=f"운동 목적 : 운동 프로그램을 만들어줘.",
            metadata={"ID": thread_id, "운동목적": "운동 프로그램을 만들어줘."}
        )

        # 메시지 실행 결과를 스트림으로 처리
        with client.beta.threads.runs.stream(
            thread_id=thread.id,
            assistant_id=assistant_exercise_designer_id,
            instructions=__EXERCISE_DESIGNER_INSTRUCTIONS__,
            event_handler=ExerciseDesignerHandler(db, thread.id),
        ) as stream:
            stream.until_done()

        elapsed_times["step_2"] = (datetime.now() - start_time).total_seconds() * 1000

        # 스트림에서 최종 메시지 가져오기
        program = json.loads(stream.get_final_messages()[0].content[0].text.value)
        elapsed_times["step_3"] = (datetime.now() - start_time).total_seconds() * 1000

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

        elapsed_times["step_4"] = (datetime.now() - start_time).total_seconds() * 1000

        # 해당 Assistant는 메인 Assistant의 Function으로 작동하므로 FunctionCall 형태로 반환
        elapsed_times["total"] = (datetime.now() - start_time).total_seconds() * 1000
        return {
            "status": "Message executed",
            "content": json.dumps(json.loads(stream.get_final_messages()[0].content[0].text.value), indent=2, ensure_ascii=False),
            "elapsed_times": elapsed_times
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