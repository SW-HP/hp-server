import os

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import desc
from sqlalchemy.orm import Session
from openai import OpenAIError

from models import  AssistantMessageCreate, AssistantThread, AssistantMessage, User
from database import get_db
from assistant import client, AssistantHandler, ExerciseDesignerHandler, __INSTRUCTIONS__, __EXERCISE_DESIGNER_INSTRUCTIONS__
from utils import get_current_user

assistant_router = APIRouter()

assistant_id = os.getenv("assistant_id")
assistant_exercise_designer_id = os.getenv("assistant_exercise_designer_id")


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

@assistant_router.post("/temp_message_run")
async def temp_message_run(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
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
            event_handler=ExerciseDesignerHandler(db, thread.thread_id),
        ) as stream:
            for text_delta in stream.text_deltas:
                print(f"Delta: {text_delta}")

        # 최종 메시지 결과 반환
        print(dir(stream))
        try:
            print(f'stream.content[0]: {stream.content[0]}')
        except Exception as e:
            print(f'stream.latest_message.content[0]: {stream.latest_message.content[0]}') 
        print(f'stream.content[0].text.value: {stream.content[0].text.value}')

        return {"status": "Message executed", "content": stream.content[0].text.value}

    except OpenAIError as e:
        raise HTTPException(status_code=500, detail=f"OpenAI API 오류: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"예상치 못한 오류가 발생했습니다: {str(e)}")