from fastapi import APIRouter
import torch
import platform

router = APIRouter()

@router.get("/test")
def system_check():
    os_name = platform.system()
    os_version = platform.version()
    python_version = platform.python_version()

    return {
        "os_name": os_name,
        "os_version": os_version,
        "python_version": python_version
    }