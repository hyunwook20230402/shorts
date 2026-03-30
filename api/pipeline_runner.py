import asyncio
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Callable

from api.models import TaskStatus, StepStatusEnum
from step0_ocr import extract_text_from_image
from step1_nlp import process_nlp
from step3_audio import generate_all_audio
from step4_subtitle import generate_subtitles
from step5_video import compose_video

logger = logging.getLogger(__name__)

# 최대 2개 동시 실행 (GPU 충돌 방지)
_executor = ThreadPoolExecutor(max_workers=2)

# task 상태 영속화 파일
TASK_STATE_FILE = Path('cache/task_states.json')


class PersistentTaskDict:
  """파일 기반 task 상태 저장소 — 다중 프로세스 환경에서도 상태 공유"""
  _lock = threading.Lock()

  def _load(self) -> dict:
    if TASK_STATE_FILE.exists():
      try:
        return json.loads(TASK_STATE_FILE.read_text(encoding='utf-8'))
      except (json.JSONDecodeError, OSError):
        return {}
    return {}

  def _save(self, data: dict):
    TASK_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    TASK_STATE_FILE.write_text(
      json.dumps(data, ensure_ascii=False, indent=2, default=str),
      encoding='utf-8'
    )

  def __contains__(self, key: str) -> bool:
    with self._lock:
      return key in self._load()

  def __getitem__(self, key: str) -> TaskStatus:
    with self._lock:
      data = self._load()
      if key not in data:
        raise KeyError(key)
      return TaskStatus(**data[key])

  def __setitem__(self, key: str, value: TaskStatus):
    with self._lock:
      data = self._load()
      data[key] = value.model_dump(mode='json')
      self._save(data)

  def __delitem__(self, key: str):
    with self._lock:
      data = self._load()
      del data[key]
      self._save(data)

  def values(self):
    with self._lock:
      data = self._load()
      return [TaskStatus(**v) for v in data.values()]


# 전역 상태 저장소
task_status_dict = PersistentTaskDict()


async def run_in_thread(func: Callable, *args, **kwargs):
  """블로킹 함수를 스레드풀에서 실행"""
  loop = asyncio.get_running_loop()
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


async def run_step0(task_id: str, image_path: str, use_cache: bool = True) -> str:
  """Step 0: OCR"""
  task = task_status_dict[task_id]
  task.current_step = 0
  task.status = StepStatusEnum.running
  task.status_message = 'OCR 처리 중...'
  task.updated_at = datetime.now()
  task_status_dict[task_id] = task
  logger.info(f'[Step 0] 시작: task_id={task_id}')

  try:
    logger.info(f'[Step 0] OCR 함수 호출 중: {image_path}')
    # 동기 함수를 직접 호출 (스레드풀 사용 안 함 - 이벤트 루프 데드락 방지)
    result = extract_text_from_image(image_path, use_cache=use_cache)
    logger.info(f'[Step 0] OCR 완료: {len(result)}자')

    task = task_status_dict[task_id]
    task.ocr_text = result
    task.status = StepStatusEnum.completed
    task.status_message = 'OCR 처리 완료'
    task.updated_at = datetime.now()
    task_status_dict[task_id] = task
    logger.info(f'[Step 0] 상태 업데이트 완료: status={task.status}')
    return result
  except Exception as e:
    logger.error(f'[Step 0] 오류: {e}', exc_info=True)
    task = task_status_dict[task_id]
    task.error_log['step0'] = str(e)
    task.status = StepStatusEnum.failed
    task.status_message = f'Step 0 오류: {str(e)}'
    task.updated_at = datetime.now()
    task_status_dict[task_id] = task
    raise


async def run_step1(task_id: str, ocr_text: str, use_cache: bool = True) -> tuple[list[dict], list[str]]:
  """Step 1: NLP"""
  task = task_status_dict[task_id]
  task.current_step = 1
  task.status = StepStatusEnum.running
  task.status_message = 'NLP 처리 중 (번역, 씬 분할)...'
  task.updated_at = datetime.now()
  task_status_dict[task_id] = task

  try:
    # 동기 함수를 직접 호출
    script_data, image_prompts = process_nlp(ocr_text, task_id, use_cache)

    # NLP 결과 캐시 경로 저장 (step1_nlp의 get_cache_path 함수 사용)
    from step1_nlp import get_cache_path
    nlp_path = get_cache_path(ocr_text)

    task = task_status_dict[task_id]
    task.nlp_cache_path = str(nlp_path).replace('\\', '/')
    task.status = StepStatusEnum.completed
    task.status_message = 'NLP 처리 완료'
    task.updated_at = datetime.now()
    task_status_dict[task_id] = task
    return script_data, image_prompts
  except Exception as e:
    logger.error(f'Step 1 오류: {e}')
    task = task_status_dict[task_id]
    task.error_log['step1'] = str(e)
    task.status = StepStatusEnum.failed
    task.status_message = f'Step 1 오류: {str(e)}'
    task.updated_at = datetime.now()
    task_status_dict[task_id] = task
    raise


async def run_step2_with_progress(task_id: str, image_prompts: list[str], use_cache: bool = True) -> list[str]:
  """Step 2: 이미지 생성 (진행 상황 실시간 업데이트)"""
  task = task_status_dict[task_id]
  task.current_step = 2
  task.status = StepStatusEnum.running
  task.updated_at = datetime.now()
  task_status_dict[task_id] = task

  try:
    from step2_vision import generate_image

    image_paths = []
    for i, prompt in enumerate(image_prompts):
      task = task_status_dict[task_id]
      task.status_message = f'이미지 생성 중: {i+1}/{len(image_prompts)}씬'
      task.updated_at = datetime.now()
      task_status_dict[task_id] = task
      logger.info(task.status_message)

      path = generate_image(prompt, i, use_cache=use_cache)
      image_paths.append(path)

    task = task_status_dict[task_id]
    task.image_paths = image_paths
    task.status = StepStatusEnum.completed
    task.status_message = f'이미지 생성 완료 ({len(image_paths)}개)'
    task.updated_at = datetime.now()
    task_status_dict[task_id] = task
    return image_paths
  except Exception as e:
    logger.error(f'Step 2 오류: {e}')
    task = task_status_dict[task_id]
    task.error_log['step2'] = str(e)
    task.status = StepStatusEnum.failed
    task.status_message = f'Step 2 오류: {str(e)}'
    task.updated_at = datetime.now()
    task_status_dict[task_id] = task
    raise


async def run_step3(task_id: str, script_data: list[dict], use_cache: bool = True) -> list[str]:
  """Step 3: 오디오 생성"""
  task = task_status_dict[task_id]
  task.current_step = 3
  task.status = StepStatusEnum.running
  task.status_message = 'TTS 오디오 생성 중...'
  task.updated_at = datetime.now()
  task_status_dict[task_id] = task

  try:
    # Windows asyncio 이슈: 별도 이벤트 루프 생성
    def _run_step3():
      loop = asyncio.new_event_loop()
      asyncio.set_event_loop(loop)
      try:
        return generate_all_audio(script_data, use_cache=use_cache)
      finally:
        loop.close()

    audio_paths = _run_step3()

    task = task_status_dict[task_id]
    task.audio_paths = audio_paths
    task.status = StepStatusEnum.completed
    task.status_message = '오디오 생성 완료'
    task.updated_at = datetime.now()
    task_status_dict[task_id] = task
    return audio_paths
  except Exception as e:
    logger.error(f'Step 3 오류: {e}')
    task = task_status_dict[task_id]
    task.error_log['step3'] = str(e)
    task.status = StepStatusEnum.failed
    task.status_message = f'Step 3 오류: {str(e)}'
    task.updated_at = datetime.now()
    task_status_dict[task_id] = task
    raise


async def run_step4(task_id: str, audio_paths: list[str], script_data: list[dict]) -> str:
  """Step 4: 자막 생성"""
  task = task_status_dict[task_id]
  task.current_step = 4
  task.status = StepStatusEnum.running
  task.status_message = '자막 생성 중...'
  task.updated_at = datetime.now()
  task_status_dict[task_id] = task

  try:
    from step4_subtitle import CACHE_DIR
    import hashlib

    # 캐시 파일명 생성
    cache_key = hashlib.md5(''.join(audio_paths).encode()).hexdigest()[:8]
    output_path = CACHE_DIR / f'{cache_key}_subtitles.srt'

    subtitle_path = generate_subtitles(
      audio_paths,
      script_data,
      str(output_path)
    )

    task = task_status_dict[task_id]
    task.subtitle_path = subtitle_path
    task.status = StepStatusEnum.completed
    task.status_message = '자막 생성 완료'
    task.updated_at = datetime.now()
    task_status_dict[task_id] = task
    return subtitle_path
  except Exception as e:
    logger.error(f'Step 4 오류: {e}')
    task = task_status_dict[task_id]
    task.error_log['step4'] = str(e)
    task.status = StepStatusEnum.failed
    task.status_message = f'Step 4 오류: {str(e)}'
    task.updated_at = datetime.now()
    task_status_dict[task_id] = task
    raise


async def run_step5(task_id: str, image_paths: list[str], audio_paths: list[str],
                    subtitle_path: str) -> str:
  """Step 5: 영상 합성"""
  task = task_status_dict[task_id]
  task.current_step = 5
  task.status = StepStatusEnum.running
  task.status_message = '영상 합성 중 (인코딩)...'
  task.updated_at = datetime.now()
  task_status_dict[task_id] = task

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
      with open(qa_report_path, 'r', encoding='utf-8') as f:
        report = json.load(f)
        scene_durations = report.get('scene_durations')

    video_path = compose_video(
      image_paths,
      audio_paths,
      subtitle_path,
      scene_durations,
      str(output_path)
    )

    task = task_status_dict[task_id]
    task.video_path = video_path
    task.status = StepStatusEnum.completed
    task.status_message = '영상 합성 완료'
    task.updated_at = datetime.now()
    task_status_dict[task_id] = task
    return video_path
  except Exception as e:
    logger.error(f'Step 5 오류: {e}')
    task = task_status_dict[task_id]
    task.error_log['step5'] = str(e)
    task.status = StepStatusEnum.failed
    task.status_message = f'Step 5 오류: {str(e)}'
    task.updated_at = datetime.now()
    task_status_dict[task_id] = task
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
      ocr_text = task_status_dict[task_id].ocr_text

    # Step 1: NLP
    if start_step <= 1 <= end_step:
      script_data, image_prompts = await run_step1(task_id, ocr_text)
    else:
      with open(task_status_dict[task_id].nlp_cache_path, 'r', encoding='utf-8') as f:
        nlp_data = json.load(f)
        script_data = nlp_data.get('modern_script_data', [])
        image_prompts = nlp_data.get('image_prompts', [])

    # Step 2: 이미지
    if start_step <= 2 <= end_step:
      image_paths = await run_step2_with_progress(task_id, image_prompts)
    else:
      image_paths = task_status_dict[task_id].image_paths

    # Step 3: 오디오
    if start_step <= 3 <= end_step:
      audio_paths = await run_step3(task_id, script_data)
    else:
      audio_paths = task_status_dict[task_id].audio_paths

    # Step 4: 자막
    if start_step <= 4 <= end_step:
      subtitle_path = await run_step4(task_id, audio_paths, script_data)
    else:
      subtitle_path = task_status_dict[task_id].subtitle_path

    # Step 5: 영상
    if start_step <= 5 <= end_step:
      await run_step5(task_id, image_paths, audio_paths, subtitle_path)

    # 완료
    task = task_status_dict[task_id]
    task.current_step = 5
    task.status = StepStatusEnum.completed
    task.status_message = '파이프라인 완료!'
    task.updated_at = datetime.now()
    task_status_dict[task_id] = task
    logger.info(f'Task {task_id} 완료')

  except Exception as e:
    logger.error(f'파이프라인 오류: {e}')
    task = task_status_dict[task_id]
    task.status = StepStatusEnum.failed
    task.status_message = f'오류 발생: {str(e)}'
    task.updated_at = datetime.now()
    task_status_dict[task_id] = task
