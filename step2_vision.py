"""
Step 2: Vision — ComfyUI API로 웹툰 이미지 생성

입력: image_prompts (list[str]) - Step 1 NLP에서 생성한 씬별 영문 프롬프트
출력: generated_image_paths (list[str]) - 생성된 PNG 이미지 경로 목록
"""

import io
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(
  level=logging.INFO,
  format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)

# 캐시 디렉토리
CACHE_DIR = Path('cache/step2')
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ComfyUI 설정
COMFYUI_HOST = os.environ.get('COMFYUI_HOST', 'localhost')
COMFYUI_PORT = os.environ.get('COMFYUI_PORT', '8188')
COMFYUI_MODEL = os.environ.get('COMFYUI_MODEL', 'model.safetensors')

COMFYUI_BASE_URL = f'http://{COMFYUI_HOST}:{COMFYUI_PORT}'

# 고정 네거티브 프롬프트
NEGATIVE_PROMPT = (
  'worst quality, low quality, blurry, deformed, ugly, '
  'duplicate, watermark, text, bad anatomy, extra limbs, '
  'missing limbs, disfigured, out of frame'
)


def get_image_cache_path(prompt: str, idx: int) -> Path:
  """이미지 캐시 경로 생성"""
  prompt_hash = str(hash(prompt))[-8:].replace('-', '_')
  return CACHE_DIR / f'{prompt_hash}_{idx:02d}_image.png'


def load_image_from_cache(cache_path: Path) -> str | None:
  """캐시에서 이미지 경로 로드"""
  if cache_path.exists():
    logger.info('캐시에서 이미지 로드: %s', cache_path)
    return str(cache_path.resolve())
  return None


def save_image_to_cache(cache_path: Path, image_data: bytes) -> None:
  """이미지 데이터를 캐시에 저장"""
  try:
    cache_path.write_bytes(image_data)
    logger.info('이미지 캐시 저장: %s', cache_path)
  except Exception as e:
    logger.warning('이미지 캐시 저장 실패: %s', str(e))


def build_comfyui_workflow(prompt: str) -> dict:
  """ComfyUI workflow JSON 조립 (KSampler 기반)"""
  workflow = {
    '4': {
      'class_type': 'CheckpointLoaderSimple',
      'inputs': {
        'ckpt_name': COMFYUI_MODEL,
      },
    },
    '5': {
      'class_type': 'EmptyLatentImage',
      'inputs': {
        'width': 512,
        'height': 910,
        'batch_size': 1,
      },
    },
    '6': {
      'class_type': 'CLIPTextEncode',
      'inputs': {
        'text': prompt,
        'clip': ['4', 1],
      },
    },
    '7': {
      'class_type': 'CLIPTextEncode',
      'inputs': {
        'text': NEGATIVE_PROMPT,
        'clip': ['4', 1],
      },
    },
    '3': {
      'class_type': 'KSampler',
      'inputs': {
        'seed': int(uuid.uuid4().int % (2 ** 32)),
        'steps': 20,
        'cfg': 7.0,
        'sampler_name': 'euler',
        'scheduler': 'normal',
        'denoise': 1.0,
        'model': ['4', 0],
        'positive': ['6', 0],
        'negative': ['7', 0],
        'latent_image': ['5', 0],
      },
    },
    '8': {
      'class_type': 'VAEDecode',
      'inputs': {
        'samples': ['3', 0],
        'vae': ['4', 2],
      },
    },
    '9': {
      'class_type': 'SaveImage',
      'inputs': {
        'images': ['8', 0],
        'filename_prefix': 'shorts_',
      },
    },
  }
  return workflow


@retry(
  stop=stop_after_attempt(3),
  wait=wait_exponential(multiplier=1, min=2, max=10),
  reraise=True,
)
def submit_comfyui_prompt(workflow: dict) -> str:
  """ComfyUI prompt 제출 → prompt_id 반환"""
  logger.info('ComfyUI 프롬프트 제출 중...')

  try:
    payload = {
      'prompt': workflow,
      'client_id': str(uuid.uuid4()),
    }

    response = requests.post(
      f'{COMFYUI_BASE_URL}/prompt',
      json=payload,
      timeout=30,
    )
    response.raise_for_status()

    result = response.json()
    prompt_id = result.get('prompt_id')

    if not prompt_id:
      raise ValueError(f'프롬프트 ID를 받지 못했습니다: {result}')

    logger.info('프롬프트 제출 완료 (ID: %s)', prompt_id)
    return prompt_id

  except requests.exceptions.RequestException as e:
    logger.error('ComfyUI 프롬프트 제출 실패: %s', str(e))
    raise RuntimeError(f'ComfyUI API 호출 실패: {str(e)}') from e


@retry(
  stop=stop_after_attempt(3),
  wait=wait_exponential(multiplier=1, min=2, max=10),
  reraise=True,
)
def poll_comfyui_history(prompt_id: str, max_wait: int = 60) -> dict:
  """ComfyUI 실행 완료 대기 (폴링, 최대 60초)"""
  import time

  logger.info('ComfyUI 이미지 생성 대기 중... (최대 %d초)', max_wait)
  start_time = time.time()

  while True:
    elapsed = time.time() - start_time
    if elapsed > max_wait:
      raise TimeoutError(f'ComfyUI 이미지 생성 시간 초과 ({max_wait}초)')

    try:
      response = requests.get(
        f'{COMFYUI_BASE_URL}/history/{prompt_id}',
        timeout=10,
      )
      response.raise_for_status()

      history = response.json()

      if prompt_id in history and history[prompt_id]:
        outputs = history[prompt_id].get('outputs', {})
        if outputs:
          logger.info('ComfyUI 이미지 생성 완료')
          return outputs

    except requests.exceptions.RequestException as e:
      logger.warning('ComfyUI history 조회 실패: %s', str(e))

    time.sleep(1)  # 1초 간격 폴링


@retry(
  stop=stop_after_attempt(3),
  wait=wait_exponential(multiplier=1, min=2, max=10),
  reraise=True,
)
def download_comfyui_image(filename: str) -> bytes:
  """ComfyUI에서 생성된 이미지 다운로드"""
  logger.info('ComfyUI 이미지 다운로드: %s', filename)

  try:
    response = requests.get(
      f'{COMFYUI_BASE_URL}/view',
      params={'filename': filename, 'type': 'output'},
      timeout=30,
    )
    response.raise_for_status()

    logger.info('이미지 다운로드 완료 (%d bytes)', len(response.content))
    return response.content

  except requests.exceptions.RequestException as e:
    logger.error('이미지 다운로드 실패: %s', str(e))
    raise RuntimeError(f'이미지 다운로드 실패: {str(e)}') from e


def generate_image(prompt: str, idx: int, use_cache: bool = True) -> str:
  """씬 1개 이미지 생성 (캐시 지원)"""
  cache_path = get_image_cache_path(prompt, idx)

  # 캐시 확인
  if use_cache:
    cached_path = load_image_from_cache(cache_path)
    if cached_path is not None:
      return cached_path

  # 1. Workflow 조립
  workflow = build_comfyui_workflow(prompt)

  # 2. 프롬프트 제출
  prompt_id = submit_comfyui_prompt(workflow)

  # 3. 이미지 생성 완료 대기
  outputs = poll_comfyui_history(prompt_id)

  # 4. 생성된 이미지 파일명 추출
  image_files = outputs.get('9', {}).get('images', [])
  if not image_files:
    raise RuntimeError(f'ComfyUI가 이미지를 생성하지 못했습니다 (prompt_id: {prompt_id})')

  image_filename = image_files[0].get('filename', '')
  if not image_filename:
    raise RuntimeError('이미지 파일명을 추출할 수 없습니다')

  # 5. 이미지 다운로드
  image_data = download_comfyui_image(image_filename)

  # 6. 캐시 저장
  if use_cache:
    save_image_to_cache(cache_path, image_data)

  logger.info('이미지 생성 완료: 씬 %d (경로: %s)', idx + 1, cache_path)
  return str(cache_path.resolve())


def generate_all_images(
  image_prompts: list[str],
  task_id: str | None = None,
  use_cache: bool = True,
) -> list[str]:
  """
  Step 2 Vision 메인 함수

  Args:
    image_prompts: Step 1에서 생성한 씬별 영문 프롬프트 (list[str])
    task_id: 파이프라인 작업 ID (로깅용, 선택)
    use_cache: 캐시 사용 여부

  Returns:
    generated_image_paths: 생성된 이미지 절대 경로 목록

  Raises:
    RuntimeError: ComfyUI 연결 실패 또는 이미지 생성 실패 시
  """
  if not task_id:
    task_id = str(uuid.uuid4())
    logger.info('task_id 자동 생성: %s', task_id)

  generated_image_paths: list[str] = []

  try:
    logger.info('이미지 생성 시작 (총 %d씬)', len(image_prompts))

    for idx, prompt in enumerate(image_prompts):
      try:
        logger.info('이미지 생성 중: 씬 %d/%d', idx + 1, len(image_prompts))
        image_path = generate_image(prompt, idx, use_cache=use_cache)
        generated_image_paths.append(image_path)

      except Exception as e:
        logger.error('씬 %d 이미지 생성 실패: %s', idx + 1, str(e))
        # 부분 실패 시에도 진행 계속
        raise RuntimeError(f'씬 {idx + 1} 이미지 생성 실패: {str(e)}') from e

    logger.info('모든 이미지 생성 완료 (경로 수: %d)', len(generated_image_paths))
    return generated_image_paths

  except Exception as e:
    logger.error('이미지 생성 처리 실패: %s', str(e))
    raise RuntimeError(f'Step 2 Vision 처리 중 오류: {str(e)}') from e


if __name__ == '__main__':
  import sys

  if len(sys.argv) < 2:
    print('사용법: python step2_vision.py <step1_nlp_캐시_JSON_경로>')
    sys.exit(1)

  nlp_cache_file = sys.argv[1]

  try:
    # Step 1 캐시 로드
    with open(nlp_cache_file, 'r', encoding='utf-8') as f:
      nlp_result = json.load(f)

    image_prompts = nlp_result.get('image_prompts', [])
    if not image_prompts:
      print('❌ image_prompts를 찾을 수 없습니다')
      sys.exit(1)

    print(f'\n📸 Step 2 Vision 시작 (총 {len(image_prompts)}씬)')
    print('=' * 60)

    generated_paths = generate_all_images(image_prompts)

    print('\n✅ 이미지 생성 완료!')
    print('=' * 60)
    for idx, path in enumerate(generated_paths, 1):
      print(f'  씬 {idx}: {path}')

  except FileNotFoundError:
    logger.error('Step 1 캐시 파일을 찾을 수 없습니다: %s', nlp_cache_file)
    sys.exit(1)
  except (json.JSONDecodeError, KeyError) as e:
    logger.error('Step 1 캐시 파일 형식 오류: %s', str(e))
    sys.exit(1)
  except RuntimeError as e:
    logger.error('이미지 생성 실패: %s', str(e))
    sys.exit(1)
