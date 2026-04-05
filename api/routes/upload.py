import hashlib
import logging
import uuid
from pathlib import Path
from typing import List

from fastapi import APIRouter, UploadFile, File
from api.models import UploadResponse
from api.pipeline_runner import task_status_dict, _create_task_status
from api.poem_registry import PoemRegistry

logger = logging.getLogger(__name__)
router = APIRouter()

UPLOAD_DIR = Path('upload_cache/uploads')
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.post('/upload', response_model=UploadResponse)
async def upload_images(files: List[UploadFile] = File(...)) -> UploadResponse:
  """이미지 N장 업로드 및 task_id, poem_id 발급 (순서 중요)"""
  if not files:
    from fastapi import HTTPException
    raise HTTPException(status_code=400, detail='이미지 파일을 하나 이상 업로드하세요.')

  try:
    task_id = str(uuid.uuid4())
    file_paths: list[str] = []
    all_contents: list[bytes] = []

    for idx, file in enumerate(files):
      contents = await file.read()
      all_contents.append(contents)
      file_path = UPLOAD_DIR / f'{task_id}_{idx:02d}_{file.filename}'
      with open(file_path, 'wb') as f:
        f.write(contents)
      file_paths.append(str(file_path))
      logger.info(f'파일 업로드 [{idx+1}/{len(files)}]: {file_path}')

    # 모든 이미지 해시를 합산하여 poem_id 결정 (순서 포함)
    combined_hash = hashlib.sha256(b''.join(all_contents)).hexdigest()
    first_filename = files[0].filename
    poem_id = PoemRegistry().find_or_create(combined_hash, first_filename)
    logger.info(f'poem_id 부여: {poem_id}')

    # poem_dir에 원본 이미지 저장
    poem_dir = PoemRegistry().get_poem_dir(poem_id)
    poem_dir.mkdir(parents=True, exist_ok=True)
    for idx, (file, contents) in enumerate(zip(files, all_contents)):
      original_dest = poem_dir / f'original_{idx:02d}{Path(file.filename).suffix}'
      if not original_dest.exists():
        original_dest.write_bytes(contents)
        logger.info(f'원본 이미지 저장: {original_dest}')

    # 작업 상태 생성
    task_status = _create_task_status(task_id)
    task_status.uploaded_image_path = file_paths[0]    # 하위호환
    task_status.uploaded_image_paths = file_paths
    task_status.poem_id = poem_id
    task_status_dict[task_id] = task_status

    return UploadResponse(
      task_id=task_id,
      image_path=file_paths[0],
      image_paths=file_paths,
      poem_id=poem_id,
      status='uploaded'
    )

  except Exception as e:
    logger.error(f'업로드 오류: {e}')
    raise
