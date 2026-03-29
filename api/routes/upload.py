import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile, File
from api.models import TaskStatus, StepStatusEnum, UploadResponse
from api.pipeline_runner import task_status_dict, _create_task_status
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter()

UPLOAD_DIR = Path('cache/uploads')
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.post('/upload', response_model=UploadResponse)
async def upload_image(file: UploadFile = File(...)) -> UploadResponse:
  """이미지 업로드 및 task_id 발급"""
  try:
    # task_id 생성
    task_id = str(uuid.uuid4())

    # 파일 저장
    file_path = UPLOAD_DIR / f'{task_id}_{file.filename}'
    contents = await file.read()
    with open(file_path, 'wb') as f:
      f.write(contents)

    logger.info(f'파일 업로드: {file_path}')

    # 작업 상태 생성
    task_status = _create_task_status(task_id)
    task_status.uploaded_image_path = str(file_path)
    task_status_dict[task_id] = task_status

    return UploadResponse(
      task_id=task_id,
      image_path=str(file_path),
      status='uploaded'
    )

  except Exception as e:
    logger.error(f'업로드 오류: {e}')
    raise
