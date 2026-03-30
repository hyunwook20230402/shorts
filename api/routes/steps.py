import asyncio
import logging

from fastapi import APIRouter, HTTPException, BackgroundTasks

from api.models import StepRequest, PipelineRunRequest
from api.pipeline_runner import (
  task_status_dict,
  run_pipeline_async,
  run_step0,
  run_step1,
  run_step2_with_progress,
  run_step3,
  run_step4,
  run_step5,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_event_loop() -> asyncio.AbstractEventLoop:
  """현재 이벤트 루프 가져오기 (없으면 생성)"""
  try:
    return asyncio.get_running_loop()
  except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop


def _run_pipeline_sync(task_id: str, start_step: int = 0, end_step: int = 5):
  """파이프라인을 동기적으로 실행 (백그라운드 태스크용)"""
  loop = _get_event_loop()
  loop.run_until_complete(run_pipeline_async(task_id, start_step, end_step))


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
async def run_step0_endpoint(request: StepRequest, background_tasks: BackgroundTasks) -> dict:
  """Step 0 실행"""
  if request.task_id not in task_status_dict:
    raise HTTPException(status_code=404, detail=f'작업 {request.task_id}를 찾을 수 없습니다')

  task = task_status_dict[request.task_id]
  image_path = task.uploaded_image_path

  if not image_path:
    raise HTTPException(status_code=400, detail='이미지가 업로드되지 않았습니다')

  # 하위 스텝 캐시 무효화
  if request.invalidate_downstream:
    task.ocr_text = None
    task.nlp_cache_path = None
    task.image_paths = []
    task.audio_paths = []
    task.subtitle_path = None
    task.video_path = None

  def _run():
    loop = _get_event_loop()
    try:
      loop.run_until_complete(run_step0(request.task_id, image_path, request.use_cache))
    except Exception as e:
      logger.error(f'Step 0 오류: {e}')

  background_tasks.add_task(_run)
  return {'task_id': request.task_id, 'status': 'running'}


@router.post('/steps/step1')
async def run_step1_endpoint(request: StepRequest, background_tasks: BackgroundTasks) -> dict:
  """Step 1 실행"""
  if request.task_id not in task_status_dict:
    raise HTTPException(status_code=404, detail=f'작업 {request.task_id}를 찾을 수 없습니다')

  task = task_status_dict[request.task_id]

  if not task.ocr_text:
    raise HTTPException(status_code=400, detail='OCR 텍스트가 없습니다. Step 0을 먼저 실행하세요')

  # 하위 스텝 캐시 무효화
  if request.invalidate_downstream:
    task.nlp_cache_path = None
    task.image_paths = []
    task.audio_paths = []
    task.subtitle_path = None
    task.video_path = None

  def _run():
    loop = _get_event_loop()
    try:
      loop.run_until_complete(run_step1(request.task_id, task.ocr_text, request.use_cache))
    except Exception as e:
      logger.error(f'Step 1 오류: {e}')

  background_tasks.add_task(_run)
  return {'task_id': request.task_id, 'status': 'running'}


@router.post('/steps/step2')
async def run_step2_endpoint(request: StepRequest, background_tasks: BackgroundTasks) -> dict:
  """Step 2 실행 (오래 걸림)"""
  if request.task_id not in task_status_dict:
    raise HTTPException(status_code=404, detail=f'작업 {request.task_id}를 찾을 수 없습니다')

  task = task_status_dict[request.task_id]

  if not task.nlp_cache_path:
    raise HTTPException(status_code=400, detail='NLP 데이터가 없습니다. Step 1을 먼저 실행하세요')

  # 하위 스텝 캐시 무효화
  if request.invalidate_downstream:
    task.image_paths = []
    task.audio_paths = []
    task.subtitle_path = None
    task.video_path = None

  def _run():
    loop = _get_event_loop()
    try:
      import json
      with open(task.nlp_cache_path, 'r', encoding='utf-8') as f:
        nlp_data = json.load(f)
        image_prompts = nlp_data.get('image_prompts', [])
      loop.run_until_complete(run_step2_with_progress(request.task_id, image_prompts, request.use_cache))
    except Exception as e:
      logger.error(f'Step 2 오류: {e}')

  background_tasks.add_task(_run)
  return {'task_id': request.task_id, 'status': 'running'}


@router.post('/steps/step3')
async def run_step3_endpoint(request: StepRequest, background_tasks: BackgroundTasks) -> dict:
  """Step 3 실행"""
  if request.task_id not in task_status_dict:
    raise HTTPException(status_code=404, detail=f'작업 {request.task_id}를 찾을 수 없습니다')

  task = task_status_dict[request.task_id]

  if not task.nlp_cache_path:
    raise HTTPException(status_code=400, detail='NLP 데이터가 없습니다. Step 1을 먼저 실행하세요')

  # 하위 스텝 캐시 무효화
  if request.invalidate_downstream:
    task.audio_paths = []
    task.subtitle_path = None
    task.video_path = None

  def _run():
    loop = _get_event_loop()
    try:
      import json
      with open(task.nlp_cache_path, 'r', encoding='utf-8') as f:
        script_data = json.load(f).get('modern_script_data', [])
      loop.run_until_complete(run_step3(request.task_id, script_data, request.use_cache))
    except Exception as e:
      logger.error(f'Step 3 오류: {e}')

  background_tasks.add_task(_run)
  return {'task_id': request.task_id, 'status': 'running'}


@router.post('/steps/step4')
async def run_step4_endpoint(request: StepRequest, background_tasks: BackgroundTasks) -> dict:
  """Step 4 실행"""
  if request.task_id not in task_status_dict:
    raise HTTPException(status_code=404, detail=f'작업 {request.task_id}를 찾을 수 없습니다')

  task = task_status_dict[request.task_id]

  if not task.audio_paths:
    raise HTTPException(status_code=400, detail='오디오가 없습니다. Step 3을 먼저 실행하세요')

  if not task.nlp_cache_path:
    raise HTTPException(status_code=400, detail='NLP 데이터가 없습니다. Step 1을 먼저 실행하세요')

  # 하위 스텝 캐시 무효화
  if request.invalidate_downstream:
    task.subtitle_path = None
    task.video_path = None

  def _run():
    loop = _get_event_loop()
    try:
      import json
      with open(task.nlp_cache_path, 'r', encoding='utf-8') as f:
        script_data = json.load(f).get('modern_script_data', [])
      loop.run_until_complete(run_step4(request.task_id, task.audio_paths, script_data))
    except Exception as e:
      logger.error(f'Step 4 오류: {e}')

  background_tasks.add_task(_run)
  return {'task_id': request.task_id, 'status': 'running'}


@router.post('/steps/step5')
async def run_step5_endpoint(request: StepRequest, background_tasks: BackgroundTasks) -> dict:
  """Step 5 실행"""
  if request.task_id not in task_status_dict:
    raise HTTPException(status_code=404, detail=f'작업 {request.task_id}를 찾을 수 없습니다')

  task = task_status_dict[request.task_id]

  if not task.subtitle_path:
    raise HTTPException(status_code=400, detail='자막이 없습니다. Step 4를 먼저 실행하세요')

  def _run():
    loop = _get_event_loop()
    try:
      loop.run_until_complete(run_step5(request.task_id, task.image_paths, task.audio_paths, task.subtitle_path))
    except Exception as e:
      logger.error(f'Step 5 오류: {e}')

  background_tasks.add_task(_run)
  return {'task_id': request.task_id, 'status': 'running'}
