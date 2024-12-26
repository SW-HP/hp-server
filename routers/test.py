from fastapi import APIRouter
import torch

router = APIRouter()

@router.get("/test")
def gpu_check():
    gpu_available = torch.cuda.is_available()
    gpu_count = torch.cuda.device_count()
    gpu_name = None
    cuda_version = torch.version.cuda
    cudnn_version = torch.backends.cudnn.version()

    if gpu_available:
        current_gpu = torch.cuda.current_device()
        gpu_name = torch.cuda.get_device_name(current_gpu)

    return {
        "gpu_available": gpu_available,
        "gpu_count": gpu_count,
        "gpu_name": gpu_name,
        "torch_version": torch.__version__,
        "cuda_version": cuda_version,
        "cudnn_version": cudnn_version
    }