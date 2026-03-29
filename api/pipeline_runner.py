import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Callable

from api.models import TaskStatus, StepStatusEnum
from step0_ocr import extract_text_from_image
from step1_nlp import process_nlp
from step2_vision import generate_all_images
from step3_audio import generate_all_audio
from step4_subtitle import generate_subtitles
from step5_video import compose_video

logger = logging.getLogger(__name__)

# 전역 상태 저장소
task_status_dict: dict[str, TaskStatus] = {}

# 최대 2개 동시 실행 (GPU 충돌 방지)
_executor = ThreadPoolExecutor(max_workers=2)


async def run_in_thread(func: Callable, *args, **kwargs):
  """블로킹 함수를 스레드풀에서 실행"""
  loop = asyncio.get_event_loop()
  return await loop.run_in_executor(_executor, lambda: func(*args, **kwargs))


def _create_task_status(task_id: str) -> TaskStatus:
  """새 작업 상태 객체 생성"""
  return TaskStatus(
    task_id=task_id,
    current_step=0,
    status=StepStatusEnum.pending,
    status_message='작업 대기 중',
    error_log={},
    created_at=datetime.now(),
    updated_at=datetime.now(),
  )


async def run_step0(task_id: str, image_path: str) -> str:
  """Step 0: OCR"""
  task = task_status_dict[task_id]
  task.current_step = 0
  task.status = StepStatusEnum.running
  task.status_message = 'OCR 처리 중...'
  task.updated_at = datetime.now()

  try:
    result = await run_in_thread(extract_text_from_image, image_path, use_cache=True)
    task.ocr_text = result
    return result
  except Exception as e:
    logger.error(f'Step 0 오류: {e}')
    task.error_log['step0'] = str(e)
    task.status = StepStatusEnum.failed
    raise


async def run_step1(task_id: str, ocr_text: str) -> tuple[list[dict], list[str]]:
  """Step 1: NLP"""
  task = task_status_dict[task_id]
  task.current_step = 1
  task.status = StepStatusEnum.running
  task.status_message = 'NLP 처리 중 (번역, 씬 분할)...'
  task.updated_at = datetime.now()

  try:
    script_data, image_prompts = await run_in_thread(process_nlp, ocr_text)

    # NLP 결과 캐시 경로 저장
    from step1_nlp import CACHE_DIR
    hash_key = __import__('hashlib').md5(ocr_text.encode()).hexdigest()[:16]
    nlp_path = CACHE_DIR / f'{hash_key}_nlp.json'
    task.nlp_cache_path = str(nlp_path)

    return script_data, image_prompts
  except Exception as e:
    logger.error(f'Step 1 오류: {e}')
    task.error_log['step1'] = str(e)
    task.status = StepStatusEnum.failed
    raise


async def run_step2_with_progress(task_id: str, image_prompts: list[str]) -> list[str]:
  """Step 2: 이미지 생성 (진행 상황 실시간 업데이트)"""
  task = task_status_dict[task_id]
  task.current_step = 2
  task.status = StepStatusEnum.running
  task.updated_at = datetime.now()

  try:
    from step2_vision import CACHE_DIR, generate_image

    image_paths = []
    for i, prompt in enumerate(image_prompts):
      task.status_message = f'이미지 생성 중: {i+1}/{len(image_prompts)}씬'
      task.updated_at = datetime.now()
      logger.info(task.status_message)

      path = await run_in_thread(generate_image, prompt, i, use_cache=True)
      image_paths.append(path)

    task.image_paths = image_paths
    return image_paths
  except Exception as e:
    logger.error(f'Step 2 오류: {e}')
    task.error_log['step2'] = str(e)
    task.status = StepStatusEnum.failed
    raise


async def run_step3(task_id: str, script_data: list[dict]) -> list[str]:
  """Step 3: 오디오 생성"""
  task = task_status_dict[task_id]
  task.current_step = 3
  task.status = StepStatusEnum.running
  task.status_message = 'TTS 오디오 생성 중...'
  task.updated_at = datetime.now()

  try:
    # Windows asyncio 이슈: 별도 이벤트 루프 생성
    def _run_step3():
      loop = asyncio.new_event_loop()
      asyncio.set_event_loop(loop)
      try:
        return generate_all_audio(script_data, use_cache=True)
      finally:
        loop.close()

    audio_paths = await run_in_thread(_run_step3)
    task.audio_paths = audio_paths
    return audio_paths
  except Exception as e:
    logger.error(f'Step 3 오류: {e}')
    task.error_log['step3'] = str(e)
    task.status = StepStatusEnum.failed
    raise


async def run_step4(task_id: str, audio_paths: list[str], script_data: list[dict]) -> str:
  """Step 4: 자막 생성"""
  task = task_status_dict[task_id]
  task.current_step = 4
  task.status = StepStatusEnum.running
  task.status_message = '자막 생성 중...'
  task.updated_at = datetime.now()

  try:
    from step4_subtitle import CACHE_DIR
    import hashlib

    # 캐시 파일명 생성
    cache_key = hashlib.md5(''.join(audio_paths).encode()).hexdigest()[:8]
    output_path = CACHE_DIR / f'{cache_key}_subtitles.srt'

    subtitle_path = await run_in_thread(
      generate_subtitles,
      audio_paths,
      script_data,
      str(output_path)
    )
    task.subtitle_path = subtitle_path
    return subtitle_path
  except Exception as e:
    logger.error(f'Step 4 오류: {e}')
    task.error_log['step4'] = str(e)
    task.status = StepStatusEnum.failed
    raise


async def run_step5(task_id: str, image_paths: list[str], audio_paths: list[str],
                    subtitle_path: str) -> str:
  """Step 5: 영상 합성"""
  task = task_status_dict[task_id]
  task.current_step = 5
  task.status = StepStatusEnum.running
  task.status_message = '영상 합성 중 (인코딩)...'
  task.updated_at = datetime.now()

  try:
    from step5_video import CACHE_DIR
    import hashlib

    # 캐시 파일명 생성
    cache_key = hashlib.md5(
      (f'{"".join(image_paths)}|{"".join(audio_paths)}|{subtitle_path}').encode()
    ).hexdigest()[:8]
    output_path = CACHE_DIR / f'{cache_key}_shorts.mp4'

    # audio-visual-qa 리포트 로드 (있으면)
    qa_report_path = Path('cache/step4/audio_visual_qa_report.json')
    scene_durations = None
    if qa_report_path.exists():
      import json
      with open(qa_report_path, 'r', encoding='utf-8') as f:
        report = json.load(f)
        scene_durations = report.get('scene_durations')

    video_path = await run_in_thread(
      compose_video,
      image_paths,
      audio_paths,
      subtitle_path,
      scene_durations,
      str(output_path)
    )
    task.video_path = video_path
    return video_path
  except Exception as e:
    logger.error(f'Step 5 오류: {e}')
    task.error_log['step5'] = str(e)
    task.status = StepStatusEnum.failed
    raise


async def run_pipeline_async(task_id: str, start_step: int = 0, end_step: int = 5):
  """Step 0~5 순차 실행"""
  task = task_status_dict[task_id]
  image_path = task.uploaded_image_path

  try:
    # Step 0: OCR
    if start_step <= 0 <= end_step:
      ocr_text = await run_step0(task_id, image_path)
    else:
      ocr_text = task.ocr_text

    # Step 1: NLP
    if start_step <= 1 <= end_step:
      script_data, image_prompts = await run_step1(task_id, ocr_text)
    else:
      import json
      with open(task.nlp_cache_path, 'r', encoding='utf-8') as f:
        nlp_data = json.load(f)
        script_data = nlp_data.get('scenes', [])
        image_prompts = [s.get('image_prompt', '') for s in script_data]

    # Step 2: 이미지
    if start_step <= 2 <= end_step:
      image_paths = await run_step2_with_progress(task_id, image_prompts)
    else:
      image_paths = task.image_paths

    # Step 3: 오디오
    if start_step <= 3 <= end_step:
      audio_paths = await run_step3(task_id, script_data)
    else:
      audio_paths = task.audio_paths

    # Step 4: 자막
    if start_step <= 4 <= end_step:
      subtitle_path = await run_step4(task_id, audio_paths, script_data)
    else:
      subtitle_path = task.subtitle_path

    # Step 5: 영상
    if start_step <= 5 <= end_step:
      video_path = await run_step5(task_id, image_paths, audio_paths, subtitle_path)
    else:
      video_path = task.video_path

    # 완료
    task.current_step = 5
    task.status = StepStatusEnum.completed
    task.status_message = '파이프라인 완료!'
    task.updated_at = datetime.now()
    logger.info(f'Task {task_id} 완료')

  except Exception as e:
    logger.error(f'파이프라인 오류: {e}')
    task.status = StepStatusEnum.failed
    task.status_message = f'오류 발생: {str(e)}'
    task.updated_at = datetime.now()
