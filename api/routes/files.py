import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

logger = logging.getLogger(__name__)
router = APIRouter()

CACHE_DIR = Path('upload_cache')


def _resolve_file(poem_id: str, filename: str) -> Path:
  """poem_id 기반 캐시 파일 경로 해석 + 경로 traversal 방지"""
  if '..' in poem_id or '..' in filename:
    raise HTTPException(status_code=400, detail='유효하지 않은 경로')
  file_path = CACHE_DIR / poem_id / filename
  if not file_path.exists():
    raise HTTPException(status_code=404, detail=f'파일을 찾을 수 없습니다: {poem_id}/{filename}')
  return file_path


@router.get('/cache/{poem_id}/video/{filename}')
async def get_video(poem_id: str, filename: str) -> FileResponse:
  """영상 파일 서빙 (v2: poem_id 기반)"""
  file_path = _resolve_file(poem_id, filename)
  return FileResponse(file_path, media_type='video/mp4')


@router.get('/cache/{poem_id}/audio/{filename}')
async def get_audio(poem_id: str, filename: str) -> FileResponse:
  """오디오 파일 서빙 (v2: poem_id 기반)"""
  file_path = _resolve_file(poem_id, filename)
  return FileResponse(file_path, media_type='audio/mpeg')


@router.get('/cache/{poem_id}/image/{filename}')
async def get_image(poem_id: str, filename: str) -> FileResponse:
  """이미지 파일 서빙 (v2: poem_id 기반)"""
  file_path = _resolve_file(poem_id, filename)
  return FileResponse(file_path, media_type='image/png')


# 하위호환: v1 flat 경로 (step5/ 등에서 직접 서빙)
@router.get('/cache/video/{filename}')
async def get_video_legacy(filename: str) -> FileResponse:
  """영상 파일 서빙 (v1 하위호환 — 전체 poem 폴더 검색)"""
  for poem_dir in CACHE_DIR.iterdir():
    if poem_dir.is_dir() and poem_dir.name.startswith('poem_'):
      file_path = poem_dir / filename
      if file_path.exists():
        return FileResponse(file_path, media_type='video/mp4')
  raise HTTPException(status_code=404, detail=f'파일을 찾을 수 없습니다: {filename}')


@router.get('/cache/audio/{filename}')
async def get_audio_legacy(filename: str) -> FileResponse:
  """오디오 파일 서빙 (v1 하위호환)"""
  for poem_dir in CACHE_DIR.iterdir():
    if poem_dir.is_dir() and poem_dir.name.startswith('poem_'):
      file_path = poem_dir / filename
      if file_path.exists():
        return FileResponse(file_path, media_type='audio/mpeg')
  raise HTTPException(status_code=404, detail=f'파일을 찾을 수 없습니다: {filename}')


@router.get('/cache/images/{filename}')
async def get_image_legacy(filename: str) -> FileResponse:
  """이미지 파일 서빙 (v1 하위호환)"""
  for poem_dir in CACHE_DIR.iterdir():
    if poem_dir.is_dir() and poem_dir.name.startswith('poem_'):
      file_path = poem_dir / filename
      if file_path.exists():
        return FileResponse(file_path, media_type='image/png')
  raise HTTPException(status_code=404, detail=f'파일을 찾을 수 없습니다: {filename}')
