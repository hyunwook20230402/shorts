import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor

import requests
from fastapi import APIRouter, BackgroundTasks, HTTPException

from api.models import PipelineRunRequest, StepRequest, StepStatusEnum
from api.pipeline_runner import (
  run_pipeline_async,
  run_step0,
  run_step1,
  run_step2_audio,
  run_step3_schedule,
  run_step4_clips,
  run_step5_merge,
  task_status_dict,
)

# 태스크 실행용 executor
_executor = ThreadPoolExecutor(max_workers=2)

logger = logging.getLogger(__name__)
router = APIRouter()


def _run_pipeline_sync(task_id: str, start_step: int = 0, end_step: int = 5):
  """파이프라인을 동기적으로 실행 (백그라운드 태스크용)"""
  try:
    asyncio.run(run_pipeline_async(task_id, start_step, end_step))
  except Exception as e:
    logger.error(f'파이프라인 오류: {e}', exc_info=True)


@router.post('/pipeline/run')
async def run_pipeline(request: PipelineRunRequest, background_tasks: BackgroundTasks) -> dict:
  """전체 파이프라인 실행 (백그라운드)"""
  if request.task_id not in task_status_dict:
    raise HTTPException(status_code=404, detail=f'작업 {request.task_id}를 찾을 수 없습니다')

  task = task_status_dict[request.task_id]

  # 이미 실행 중인 경우
  if task.status.value == 'running':
    return {'task_id': request.task_id, 'status': 'already_running'}

  # 백그라운드 작업 등록
  background_tasks.add_task(
    _run_pipeline_sync,
    request.task_id,
    request.start_step,
    request.end_step
  )

  logger.info(f'파이프라인 시작: {request.task_id}')
  return {'task_id': request.task_id, 'status': 'running'}


@router.post('/steps/step0')
async def run_step0_endpoint(request: StepRequest) -> dict:
  """Step 0: OCR 실행"""
  if request.task_id not in task_status_dict:
    raise HTTPException(status_code=404, detail=f'작업 {request.task_id}를 찾을 수 없습니다')

  task = task_status_dict[request.task_id]
  image_path = task.uploaded_image_path

  if not image_path:
    raise HTTPException(status_code=400, detail='이미지가 업로드되지 않았습니다')

  # 하위 스텝 캐시 무효화 (v2: Step 2부터 시작)
  if request.invalidate_downstream:
    task.ocr_text = None
    task.nlp_cache_path = None
    task.audio_paths = []
    task.tts_alignment_paths = []
    task.frame_schedule_path = None
    task.still_image_paths = []
    task.video_clip_paths = []
    task.video_path = None

  def _run_sync():
    try:
      asyncio.set_event_loop(None)
    except Exception:
      pass
    try:
      logger.info(f'[EXECUTOR] Step 0 시작: task_id={request.task_id}')
      asyncio.run(run_step0(request.task_id, image_path, request.use_cache))
      logger.info(f'[EXECUTOR] Step 0 완료: status={task_status_dict[request.task_id].status}')
    except Exception as e:
      logger.error(f'[EXECUTOR] Step 0 오류: {e}', exc_info=True)

  _executor.submit(_run_sync)
  return {'task_id': request.task_id, 'status': 'running'}


@router.post('/steps/step1')
async def run_step1_endpoint(request: StepRequest) -> dict:
  """Step 1: NLP 실행"""
  if request.task_id not in task_status_dict:
    raise HTTPException(status_code=404, detail=f'작업 {request.task_id}를 찾을 수 없습니다')

  task = task_status_dict[request.task_id]

  if not task.ocr_text:
    raise HTTPException(status_code=400, detail='OCR 텍스트가 없습니다. Step 0을 먼저 실행하세요')

  # 하위 스텝 캐시 무효화
  if request.invalidate_downstream:
    task.nlp_cache_path = None
    task.audio_paths = []
    task.tts_alignment_paths = []
    task.frame_schedule_path = None
    task.still_image_paths = []
    task.video_clip_paths = []
    task.video_path = None

  def _run_sync():
    try:
      asyncio.run(run_step1(request.task_id, task.ocr_text, request.use_cache))
    except Exception as e:
      logger.error(f'Step 1 오류: {e}')
      task.status = StepStatusEnum.failed
      task.status_message = str(e)

  _executor.submit(_run_sync)
  return {'task_id': request.task_id, 'status': 'running'}


@router.post('/steps/step2')
async def run_step2_endpoint(request: StepRequest) -> dict:
  """Step 2: ElevenLabs TTS 실행"""
  if request.task_id not in task_status_dict:
    raise HTTPException(status_code=404, detail=f'작업 {request.task_id}를 찾을 수 없습니다')

  task = task_status_dict[request.task_id]

  if not task.nlp_cache_path:
    raise HTTPException(status_code=400, detail='NLP 데이터가 없습니다. Step 1을 먼저 실행하세요')

  # TTS 엔진 확인: ElevenLabs 키 있으면 ElevenLabs, 없으면 edge-tts fallback
  elevenlabs_api_key = os.getenv('ELEVENLABS_API_KEY', '')
  if not elevenlabs_api_key:
    logger.info('ELEVENLABS_API_KEY 미설정 — edge-tts 기본 음성으로 진행')

  # 하위 스텝 캐시 무효화
  if request.invalidate_downstream:
    task.tts_alignment_paths = []
    task.frame_schedule_path = None
    task.still_image_paths = []
    task.video_clip_paths = []
    task.video_path = None

  def _run_sync():
    try:
      import json
      with open(task.nlp_cache_path, 'r', encoding='utf-8') as f:
        nlp_data = json.load(f)
        script_data = nlp_data.get('modern_script_data', [])
      asyncio.run(run_step2_audio(request.task_id, script_data, request.use_cache))
    except Exception as e:
      logger.error(f'Step 2 오류: {e}')
      task.status = StepStatusEnum.failed
      task.status_message = str(e)

  _executor.submit(_run_sync)
  return {'task_id': request.task_id, 'status': 'running'}


@router.post('/steps/step3')
async def run_step3_endpoint(request: StepRequest) -> dict:
  """Step 3: 동적 프레임 스케줄링 실행"""
  if request.task_id not in task_status_dict:
    raise HTTPException(status_code=404, detail=f'작업 {request.task_id}를 찾을 수 없습니다')

  task = task_status_dict[request.task_id]

  if not task.sentence_audio_paths or not task.sentence_alignment_paths:
    raise HTTPException(
      status_code=400,
      detail='ElevenLabs 오디오/타임스탬프가 없습니다. Step 2를 먼저 실행하세요'
    )

  # 하위 스텝 캐시 무효화
  if request.invalidate_downstream:
    task.sentence_schedule_path = None
    task.frame_schedule_path = None
    task.still_image_paths = []
    task.video_clip_paths = []
    task.video_path = None

  def _run_sync():
    try:
      import json
      with open(task.nlp_cache_path, 'r', encoding='utf-8') as f:
        nlp_data = json.load(f)
        script_data = nlp_data.get('modern_script_data', [])
      asyncio.run(run_step3_schedule(
        request.task_id,
        script_data,
        task.sentence_audio_paths,
        task.sentence_alignment_paths,
        request.use_cache
      ))
    except Exception as e:
      logger.error(f'Step 3 오류: {e}')
      task.status = StepStatusEnum.failed
      task.status_message = str(e)

  _executor.submit(_run_sync)
  return {'task_id': request.task_id, 'status': 'running'}


@router.post('/steps/step4')
async def run_step4_endpoint(request: StepRequest) -> dict:
  """Step 4: AnimateDiff 비디오 클립 실행"""
  if request.task_id not in task_status_dict:
    raise HTTPException(status_code=404, detail=f'작업 {request.task_id}를 찾을 수 없습니다')

  task = task_status_dict[request.task_id]

  if not task.frame_schedule_path:
    raise HTTPException(
      status_code=400,
      detail='프레임 스케줄이 없습니다. Step 3을 먼저 실행하세요'
    )

  # ComfyUI 헬스체크
  comfyui_host = os.getenv('COMFYUI_HOST', 'http://127.0.0.1:8188')
  try:
    requests.get(f'{comfyui_host}/system_stats', timeout=3)
  except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
    error_msg = f'ComfyUI 서버가 실행되지 않았습니다. {comfyui_host}에 연결할 수 없습니다. ' \
                f'ComfyUI 디렉토리에서 python main.py를 실행한 후 다시 시도하세요.'
    task.status = StepStatusEnum.failed
    task.status_message = error_msg
    task.error_log['step4'] = error_msg
    raise HTTPException(status_code=503, detail=error_msg)

  # 하위 스텝 캐시 무효화
  if request.invalidate_downstream:
    task.still_image_paths = []
    task.video_clip_paths = []
    task.video_path = None

  def _run_sync():
    try:
      asyncio.run(run_step4_clips(request.task_id, task.frame_schedule_path, request.use_cache))
    except Exception as e:
      logger.error(f'Step 4 오류: {e}')
      task.status = StepStatusEnum.failed
      task.status_message = str(e)

  _executor.submit(_run_sync)
  return {'task_id': request.task_id, 'status': 'running'}


@router.post('/steps/step5')
async def run_step5_endpoint(request: StepRequest) -> dict:
  """Step 5: Burn-in + 최종 병합 실행"""
  if request.task_id not in task_status_dict:
    raise HTTPException(status_code=404, detail=f'작업 {request.task_id}를 찾을 수 없습니다')

  task = task_status_dict[request.task_id]

  if not task.still_image_paths or not task.sentence_schedule_path:
    raise HTTPException(
      status_code=400,
      detail='정지 이미지 또는 스케줄이 없습니다. Step 3~4를 먼저 실행하세요'
    )

  def _run_sync():
    try:
      asyncio.run(run_step5_merge(
        request.task_id,
        task.still_image_paths,
        task.audio_paths,
        task.sentence_schedule_path
      ))
    except Exception as e:
      logger.error(f'Step 5 오류: {e}')
      task.status = StepStatusEnum.failed
      task.status_message = str(e)

  _executor.submit(_run_sync)
  return {'task_id': request.task_id, 'status': 'running'}
