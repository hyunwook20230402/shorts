import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

logger = logging.getLogger(__name__)
router = APIRouter()

CACHE_DIR = Path('cache')


def _safe_path(filename: str, subdir: str) -> Path:
  """경로 traversal 방지"""
  if '..' in filename or filename.startswith('/'):
    raise HTTPException(status_code=400, detail='유효하지 않은 파일명')
  return CACHE_DIR / subdir / filename


@router.get('/cache/images/{filename}')
async def get_image(filename: str) -> FileResponse:
  """이미지 파일 서빙"""
  file_path = _safe_path(filename, 'step2')
  if not file_path.exists():
    raise HTTPException(status_code=404, detail='파일을 찾을 수 없습니다')
  return FileResponse(file_path, media_type='image/png')


@router.get('/cache/audio/{filename}')
async def get_audio(filename: str) -> FileResponse:
  """오디오 파일 서빙"""
  file_path = _safe_path(filename, 'step3')
  if not file_path.exists():
    raise HTTPException(status_code=404, detail='파일을 찾을 수 없습니다')
  return FileResponse(file_path, media_type='audio/mpeg')


@router.get('/cache/video/{filename}')
async def get_video(filename: str) -> FileResponse:
  """영상 파일 서빙 (스트리밍)"""
  file_path = _safe_path(filename, 'step5')
  if not file_path.exists():
    raise HTTPException(status_code=404, detail='파일을 찾을 수 없습니다')
  return FileResponse(file_path, media_type='video/mp4')


@router.get('/cache/subtitle/{filename}')
async def get_subtitle(filename: str) -> FileResponse:
  """자막 파일 서빙"""
  file_path = _safe_path(filename, 'step4')
  if not file_path.exists():
    raise HTTPException(status_code=404, detail='파일을 찾을 수 없습니다')
  return FileResponse(file_path, media_type='text/plain; charset=utf-8')
