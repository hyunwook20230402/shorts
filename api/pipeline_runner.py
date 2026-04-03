import asyncio
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Callable

from step0_ocr import extract_text_from_image
from step1_nlp import process_nlp
from step2_tts import generate_all_audio as elevenlabs_generate_all_v3
from step3_scheduler import build_sentence_schedules
from step4_image import generate_all_images
from step5_bgm import run_step5 as generate_bgm
from step6_video import compose_final_video

from api.models import StepStatusEnum, TaskStatus
from api.poem_registry import PoemRegistry

logger = logging.getLogger(__name__)

# 최대 2개 동시 실행 (GPU 충돌 방지)
_executor = ThreadPoolExecutor(max_workers=2)

# task 상태 영속화 파일
TASK_STATE_FILE = Path('upload_cache/task_states.json')


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


def _get_poem_dir(task: TaskStatus) -> Path:
  """task의 poem_id로부터 캐시 폴더 경로 도출"""
  if not task.poem_id:
    raise ValueError(f'poem_id 없음: {task.task_id} — 이미지를 다시 업로드하세요')
  poem_dir = PoemRegistry().get_poem_dir(task.poem_id)
  poem_dir.mkdir(parents=True, exist_ok=True)
  return poem_dir


async def run_step0(task_id: str, image_path: str, use_cache: bool = True) -> str:
  """Step 0: OCR"""
  task = task_status_dict[task_id]
  task.current_step = 0
  task.status = StepStatusEnum.running
  task.status_message = 'OCR 처리 중...'
  task.updated_at = datetime.now()
  task_status_dict[task_id] = task
  logger.info(f'[Step 0] 시작: task_id={task_id}, poem_id={task.poem_id}')

  try:
    poem_dir = _get_poem_dir(task)
    logger.info(f'[Step 0] OCR 함수 호출 중: {image_path}')
    # 동기 함수를 직접 호출 (스레드풀 사용 안 함 - 이벤트 루프 데드락 방지)
    result = extract_text_from_image(image_path, poem_dir, use_cache=use_cache)
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
    poem_dir = _get_poem_dir(task)

    # 동기 함수를 직접 호출
    script_data, image_prompts = process_nlp(ocr_text, poem_dir, task_id=task_id, use_cache=use_cache)

    # NLP 결과 캐시 경로
    nlp_path = poem_dir / 'step1_nlp.json'

    # 파일 존재 검증
    if not nlp_path.exists():
      raise RuntimeError(f'NLP 캐시 파일이 생성되지 않았습니다: {nlp_path}')

    # 메타데이터 갱신: NLP 결과에서 title, author 추출
    try:
      nlp_data = json.loads(nlp_path.read_text(encoding='utf-8'))
      PoemRegistry().update_poem_info(
        task.poem_id,
        title=nlp_data.get('title', ''),
        author=nlp_data.get('author', ''),
      )
      logger.info(f'[Step 1] 메타데이터 갱신 완료: {task.poem_id}')
    except Exception as metadata_err:
      logger.warning(f'[Step 1] 메타데이터 갱신 실패 (무시): {metadata_err}')

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


async def run_step2_audio(task_id: str, script_data: list[dict], use_cache: bool = True) -> tuple[list[list[str]], list[list[str]]]:
  """Step 2: 문장 단위 ElevenLabs TTS → (sentence_audio_paths, sentence_alignment_paths)"""
  task = task_status_dict[task_id]
  task.current_step = 2
  task.status = StepStatusEnum.running
  task.status_message = '문장 단위 음성 생성 중...'
  task.updated_at = datetime.now()
  task_status_dict[task_id] = task

  try:
    poem_dir = _get_poem_dir(task)
    # 문장 단위 TTS: [씬][문장] 2차원 리스트 반환
    sentence_audio_paths, sentence_alignment_paths = await elevenlabs_generate_all_v3(
      script_data, poem_dir=poem_dir, use_cache=use_cache
    )

    task = task_status_dict[task_id]
    task.sentence_audio_paths = sentence_audio_paths
    task.sentence_alignment_paths = sentence_alignment_paths
    # 하위호환: flat list도 유지
    task.audio_paths = [p for scene in sentence_audio_paths for p in scene]
    task.tts_alignment_paths = [p for scene in sentence_alignment_paths for p in scene]
    task.status = StepStatusEnum.completed
    total_sentences = sum(len(s) for s in sentence_audio_paths)
    task.status_message = f'음성 생성 완료 ({total_sentences}개 문장)'
    task.updated_at = datetime.now()
    task_status_dict[task_id] = task
    return sentence_audio_paths, sentence_alignment_paths
  except Exception as e:
    logger.error(f'Step 2 오류: {e}')
    task = task_status_dict[task_id]
    task.error_log['step2'] = str(e)
    task.status = StepStatusEnum.failed
    task.status_message = f'Step 2 오류: {str(e)}'
    task.updated_at = datetime.now()
    task_status_dict[task_id] = task
    raise


async def run_step3_schedule(
  task_id: str,
  script_data: list[dict],
  sentence_audio_paths: list[list[str]],
  sentence_alignment_paths: list[list[str]],
  use_cache: bool = True
) -> str:
  """Step 3: 문장 단위 스케줄 생성 → sentence_schedule_path"""
  task = task_status_dict[task_id]
  task.current_step = 3
  task.status = StepStatusEnum.running
  task.status_message = '문장 단위 스케줄 생성 중...'
  task.updated_at = datetime.now()
  task_status_dict[task_id] = task

  try:
    poem_dir = _get_poem_dir(task)
    sentence_schedule_path = build_sentence_schedules(
      script_data,
      sentence_audio_paths,
      sentence_alignment_paths,
      poem_dir,
      use_cache=use_cache
    )

    task = task_status_dict[task_id]
    task.sentence_schedule_path = sentence_schedule_path
    task.frame_schedule_path = sentence_schedule_path  # 하위호환
    task.status = StepStatusEnum.completed
    task.status_message = '문장 스케줄 생성 완료'
    task.updated_at = datetime.now()
    task_status_dict[task_id] = task
    return sentence_schedule_path
  except Exception as e:
    logger.error(f'Step 3 오류: {e}')
    task = task_status_dict[task_id]
    task.error_log['step3'] = str(e)
    task.status = StepStatusEnum.failed
    task.status_message = f'Step 3 오류: {str(e)}'
    task.updated_at = datetime.now()
    task_status_dict[task_id] = task
    raise


async def run_step4_clips(task_id: str, sentence_schedule_path: str, use_cache: bool = True) -> list[str]:
  """Step 4: 문장 단위 정지 이미지 생성 (Step 4-A) → still_image_paths"""
  task = task_status_dict[task_id]
  task.current_step = 4
  task.status = StepStatusEnum.running
  task.status_message = 'Step 4: ComfyUI 정지 이미지 생성 중...'
  task.updated_at = datetime.now()
  task_status_dict[task_id] = task

  try:
    poem_dir = _get_poem_dir(task)
    # generate_all_clips()는 이제 still_image_paths 리스트만 반환
    still_image_paths = generate_all_images(
      sentence_schedule_path,
      poem_dir,
      use_cache=use_cache
    )

    task = task_status_dict[task_id]
    task.still_image_paths = still_image_paths
    task.video_clip_paths = []
    task.status = StepStatusEnum.completed
    task.status_message = f'정지 이미지 생성 완료 ({len(still_image_paths)}개 문장)'
    task.updated_at = datetime.now()
    task_status_dict[task_id] = task
    return still_image_paths
  except Exception as e:
    logger.error(f'Step 4 오류: {e}')
    task = task_status_dict[task_id]
    task.error_log['step4'] = str(e)
    task.status = StepStatusEnum.failed
    task.status_message = f'Step 4 오류: {str(e)}'
    task.updated_at = datetime.now()
    task_status_dict[task_id] = task
    raise


async def run_step5_bgm(task_id: str, use_cache: bool = True) -> str:
  """Step 5: BGM 생성 → bgm_path (step5_bgm.wav)"""
  task = task_status_dict[task_id]
  task.current_step = 5
  task.status = StepStatusEnum.running
  task.status_message = 'BGM 생성 중...'
  task.updated_at = datetime.now()
  task_status_dict[task_id] = task

  try:
    poem_dir = _get_poem_dir(task)
    bgm_path = generate_bgm(str(poem_dir), use_cache=use_cache)

    task = task_status_dict[task_id]
    task.bgm_path = bgm_path
    task.status = StepStatusEnum.completed
    task.status_message = 'BGM 생성 완료'
    task.updated_at = datetime.now()
    task_status_dict[task_id] = task
    return bgm_path
  except Exception as e:
    logger.error(f'Step 5 오류: {e}')
    task = task_status_dict[task_id]
    task.error_log['step5'] = str(e)
    task.status = StepStatusEnum.failed
    task.status_message = f'Step 5 오류: {str(e)}'
    task.updated_at = datetime.now()
    task_status_dict[task_id] = task
    raise


async def run_step6_merge(
  task_id: str,
  still_image_paths: list[str],
  audio_paths: list[str],
  sentence_schedule_path: str
) -> str:
  """Step 6: 문장 단위 이미지 병합 + 자막 + BGM → final video_path"""
  task = task_status_dict[task_id]
  task.current_step = 6
  task.status = StepStatusEnum.running
  task.status_message = '최종 영상 병합 중...'
  task.updated_at = datetime.now()
  task_status_dict[task_id] = task

  try:
    poem_dir = _get_poem_dir(task)
    video_path = compose_final_video(
      still_image_paths,
      audio_paths,
      sentence_schedule_path,
      poem_dir,
      use_cache=True
    )

    task = task_status_dict[task_id]
    task.video_path = video_path
    task.status = StepStatusEnum.completed
    task.status_message = '최종 영상 완성!'
    task.updated_at = datetime.now()
    task_status_dict[task_id] = task
    return video_path
  except Exception as e:
    logger.error(f'Step 6 오류: {e}')
    task = task_status_dict[task_id]
    task.error_log['step6'] = str(e)
    task.status = StepStatusEnum.failed
    task.status_message = f'Step 6 오류: {str(e)}'
    task.updated_at = datetime.now()
    task_status_dict[task_id] = task
    raise


async def run_pipeline_async(task_id: str, start_step: int = 0, end_step: int = 6):
  """Step 0~5 순차 실행 (v2 파이프라인)"""
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

    # Step 2: 문장 단위 ElevenLabs 음성 + 타임스탬프
    if start_step <= 2 <= end_step:
      sentence_audio_paths, sentence_alignment_paths = await run_step2_audio(task_id, script_data)
    else:
      sentence_audio_paths = task_status_dict[task_id].sentence_audio_paths
      sentence_alignment_paths = task_status_dict[task_id].sentence_alignment_paths

    # Step 3: 문장 단위 스케줄 생성
    if start_step <= 3 <= end_step:
      sentence_schedule_path = await run_step3_schedule(task_id, script_data, sentence_audio_paths, sentence_alignment_paths)
    else:
      sentence_schedule_path = task_status_dict[task_id].sentence_schedule_path

    # Step 4: 문장 단위 정지 이미지 생성
    if start_step <= 4 <= end_step:
      still_image_paths = await run_step4_clips(task_id, sentence_schedule_path)
    else:
      still_image_paths = task_status_dict[task_id].still_image_paths

    # Step 5: BGM 생성
    if start_step <= 5 <= end_step:
      await run_step5_bgm(task_id)

    # Step 6: 문장 단위 이미지 병합 + 자막 + BGM
    if start_step <= 6 <= end_step:
      audio_flat = task_status_dict[task_id].audio_paths  # flat list
      await run_step6_merge(task_id, still_image_paths, audio_flat, sentence_schedule_path)

    # 완료
    task = task_status_dict[task_id]
    task.current_step = 6
    task.status = StepStatusEnum.completed
    task.status_message = '파이프라인 완료!'
    task.updated_at = datetime.now()
    task_status_dict[task_id] = task
    logger.info(f'Task {task_id} 완료')

  except Exception as e:
    logger.error(f'파이프라인 오류: {e}')
    task = task_status_dict[task_id]
    task.status = StepStatusEnum.failed
    task.status_message = f'파이프라인 오류: {str(e)}'
    task.updated_at = datetime.now()
    task_status_dict[task_id] = task
    raise
