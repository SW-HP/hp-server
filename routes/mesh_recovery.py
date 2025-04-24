from fastapi import APIRouter, UploadFile, HTTPException, File, Depends
from sqlalchemy.orm import Session
import requests
import os
from dotenv import load_dotenv

from models import User
from utils import get_current_user
from database import get_db
load_dotenv()

ml_host = os.getenv("ML_HOST")
ml_port = os.getenv("ML_PORT")

recovery_router = APIRouter()

@recovery_router.post("/process-image/")
async def process_image(file: UploadFile = File(...), _fov: int = 60, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        url = f"http://{ml_host}:{ml_port}/process-image/?_fov={_fov}"
        files = {'file': (file.filename, file.file, file.content_type)}
        headers = {'accept': 'application/json'}

        response = requests.post(url, headers=headers, files=files)

        # if response.status_code != 200:
        #     raise HTTPException(status_code=response.status_code, detail="이미지 처리 중 오류가 발생했습니다")

        return response.json()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"서버 오류가 발생했습니다: {str(e)}")