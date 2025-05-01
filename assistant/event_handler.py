import json, os

from typing import Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import desc
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from openai import AssistantEventHandler, OpenAI
from openai.types.beta.threads import Message

from functions import get_user_train_program, save_user_train_program
from models import AssistantThread, AssistantMessage
from assistant import __INSTRUCTIONS__, __EXERCISE_DESIGNER_INSTRUCTIONS__

openai_api_key = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=openai_api_key)

def override(method: Any) -> Any:
    return method

#       .oooooo.                                               .o.       ooooo
#      d8P'  `Y8b                                             .888.      `888'
#     888      888 oo.ooooo.   .ooooo.  ooo. .oo.            .8"888.      888 
#     888      888  888' `88b d88' `88b `888P"Y88b          .8' `888.     888 
#     888      888  888   888 888ooo888  888   888         .88ooo8888.    888 
#     `88b    d88'  888   888 888    .o  888   888        .8'     `888.   888 
#      `Y8bood8P'   888bod8P' `Y8bod8P' o888o o888o      o88o     o8888o o888o
#                   888                                                       
#                  o888o                                               


class AssistantHandler(AssistantEventHandler):
    def __init__(self, db: Session, thread_id: str):
        super().__init__()
        self.db = db
        self.thread_id = thread_id

    def update_message_status(self, status: str):
        try:
            message = self.db.query(AssistantMessage).filter(AssistantMessage.thread_id == self.thread_id).order_by(desc(AssistantMessage.created_at)).first()
            if message:
                self.db.query(AssistantThread).filter(AssistantThread.thread_id == self.thread_id).update({"run_state": status})
                self.db.commit()
            else:
                raise HTTPException(status_code=404, detail="메세지가 존재하지 않습니다.")
        except SQLAlchemyError:
            self.db.rollback()
    def on_event(self, event: Any) -> None:
        self.update_message_status(event.event)
        if event.event == 'thread.run.requires_action':
            run_id = event.data.id
            self.handle_requires_action(event.data, run_id)
        elif event.event == 'thread.run.cancelled':
            raise HTTPException(status_code=400, detail="쓰레드가 취소되었습니다.")
        elif event.event == 'thread.run.created':
            new_message = AssistantMessage(
                thread_id=self.thread_id,
                sender_type="assistant",
                content="",
                created_at=datetime.utcnow()
            )
            self.db.add(new_message)
            self.db.commit()
            self.db.refresh(new_message)
        else:
            pass
        
    @override
    def on_tool_call_created(self, tool_call):
        self.function_name = tool_call.function.name
        self.tool_id = tool_call.id

    @override
    def handle_requires_action(self, data, run_id):
        tool_outputs = []

        for tool in data.required_action.submit_tool_outputs.tool_calls:
            print(f"tool.function.name: {tool.function.name}")
            print(f"tool.function.arguments: {tool.function.arguments}")
            tool_arguments = json.loads(tool.function.arguments) if tool.function.arguments else {}

            if tool.function.name == "get_user_train_program":
                result = get_user_train_program(db=self.db, thread_id=self.current_run.thread_id, **tool_arguments)


            if isinstance(result, dict):
                result = json.dumps(result, ensure_ascii=False)
            elif not isinstance(result, str):
                result = str(result)
            tool_outputs.append({"tool_call_id" : tool.id, "output": result})
        self.submit_tool_outputs(tool_outputs, run_id)

    @override
    def submit_tool_outputs(self, tool_outputs, run_id):
        with client.beta.threads.runs.submit_tool_outputs_stream(
            thread_id=self.current_run.thread_id,
            run_id=self.current_run.id,
            tool_outputs=tool_outputs,
            event_handler=AssistantHandler(self.db, self.thread_id),
        ) as stream:
            try:
                for text in stream.text_deltas:
                    self.db.commit()
            except Exception as e:
                self.db.rollback()
    @override
    def on_text_delta(self, delta, snapshot):
        try:
            message = self.db.query(AssistantMessage).filter(AssistantMessage.thread_id == self.thread_id).order_by(desc(AssistantMessage.created_at)).first()
            if message:
                new_content = message.content + delta.value
                message.content = new_content
                self.db.commit()
            # else:
                # raise HTTPException(status_code=404, detail="메세지가 존재하지 않습니다.")
        except SQLAlchemyError as e:
            self.db.rollback()
            # raise HTTPException(status_code=500, detail=f"메세지 델타 처리 실패: {str(e)}")

    @override
    def on_message_done(self, content: Message) -> None:
        try:
            message = self.db.query(AssistantMessage).filter(AssistantMessage.thread_id == self.thread_id).order_by(desc(AssistantMessage.created_at)).first()
            if message:
                message.content = content.content[0].text.value
                self.db.commit()
        except SQLAlchemyError as e:
            self.db.rollback()
            # raise HTTPException(status_code=500, detail=f"메세지 종료 처리 실패: {str(e)}")


class ExerciseDesignerHandler(AssistantEventHandler):
    def __init__(self, db: Session, thread_id: str):
        super().__init__()
        self.db = db
        self.thread_id = thread_id
        
    @override
    def on_tool_call_created(self, tool_call):
        self.function_name = tool_call.function.name
        self.tool_id = tool_call.id

    @override
    def handle_requires_action(self, data, run_id):
        tool_outputs = []

        for tool in data.required_action.submit_tool_outputs.tool_calls:
            tool_arguments = json.loads(tool.function.arguments) if tool.function.arguments else {}

            if tool.function.name == "save_user_train_program":
                result = save_user_train_program(db=self.db, thread_id=self.current_run.thread_id, **tool_arguments)
            elif tool.function.name == "get_user_train_program":
                result = get_user_train_program(db=self.db, thread_id=self.current_run.thread_id, **tool_arguments)


            if isinstance(result, dict):
                result = json.dumps(result, ensure_ascii=False)
            elif not isinstance(result, str):
                result = str(result)
            tool_outputs.append({"tool_call_id" : tool.id, "output": result})
        self.submit_tool_outputs(tool_outputs, run_id)

    @override
    def submit_tool_outputs(self, tool_outputs, run_id):
        with client.beta.threads.runs.submit_tool_outputs_stream(
            thread_id=self.current_run.thread_id,
            run_id=self.current_run.id,
            tool_outputs=tool_outputs,
            event_handler=ExerciseDesignerHandler(self.db, self.thread_id),
        ) as stream:
            try:
                for text in stream.text_deltas:
                    print(f'\tdelta: {text}')
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"메세지 델타 처리 실패: {str(e)}")

    @override
    def on_message_done(self, content: Message) -> None:
        try:
            print(f"\t→")
            print(f'\t→content: {content}')
            print(f'\t→content: {content.content[0].text.value}')
            print(f"\t→")

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"메세지 종료 처리 실패: {str(e)}")