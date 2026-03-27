"""
Step 2: Vision — ComfyUI API로 웹툰 이미지 생성

입력: image_prompts (list[str]) - Step 1 NLP에서 생성한 씬별 영문 프롬프트
출력: generated_image_paths (list[str]) - 생성된 PNG 이미지 경로 목록

## 사용법
  # 서버 연결 확인
  uv run python step2_vision.py --check

  # 씬 1개만 생성 (테스트)
  uv run python step2_vision.py cache/step1/12975cb9eb3c0067_nlp.json --scene 1

  # 전체 씬 생성
  uv run python step2_vision.py cache/step1/12975cb9eb3c0067_nlp.json

## .env 필수 항목
  COMFYUI_HOST=127.0.0.1
  COMFYUI_PORT=8188
  COMFYUI_MODEL=FLUX1/flux1-dev-fp8.safetensors
  COMFYUI_VAE=ae.safetensors
  COMFYUI_CLIP=clip_l.safetensors
  COMFYUI_MAX_WAIT=600
"""

import argparse
import json
import logging
import os
import uuid
from pathlib import Path

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

# ComfyUI 설정 (.env에서 로드)
COMFYUI_HOST = os.environ.get('COMFYUI_HOST', '127.0.0.1')
COMFYUI_PORT = os.environ.get('COMFYUI_PORT', '8188')
COMFYUI_MODEL = os.environ.get('COMFYUI_MODEL', 'flux1-dev-fp8.safetensors')
COMFYUI_VAE = os.environ.get('COMFYUI_VAE', 'ae.safetensors')
COMFYUI_CLIP = os.environ.get('COMFYUI_CLIP', 'clip_l.safetensors')
COMFYUI_CLIP2 = os.environ.get('COMFYUI_CLIP2', 't5xxl_fp8_e4m3fn.safetensors')
COMFYUI_MAX_WAIT = int(os.environ.get('COMFYUI_MAX_WAIT', '600'))

COMFYUI_BASE_URL = f'http://{COMFYUI_HOST}:{COMFYUI_PORT}'

# 고정 네거티브 프롬프트
NEGATIVE_PROMPT = (
  'worst quality, low quality, blurry, deformed, ugly, '
  'duplicate, watermark, text, bad anatomy, extra limbs, '
  'missing limbs, disfigured, out of frame'
)


# ──────────────────────────────────────────────
# 캐시 유틸
# ──────────────────────────────────────────────

def get_cache_path(prompt: str, idx: int) -> Path:
  """이미지 캐시 경로 생성"""
  prompt_hash = str(abs(hash(prompt)))[-8:]
  return CACHE_DIR / f'{prompt_hash}_{idx:02d}_image.png'


# ──────────────────────────────────────────────
# Workflow 조립
# ──────────────────────────────────────────────

def build_workflow(prompt: str) -> dict:
  """FLUX.1 Dev fp8 workflow 조립

  UNETLoader 사용 (diffusion_models 또는 checkpoints 폴더 모두 인식)
  VAE: VAELoader, CLIP: DualCLIPLoader (clip_l + t5xxl, type: flux)
  CLIPTextEncodeFlux의 clip_l, t5xxl은 STRING 직접 입력 (노드 연결 아님)

  ## 해상도 보정 (ComfyUI 50% 축소 패턴)
  현재 ComfyUI 서버에서 생성되는 이미지가 입력 해상도의 50%로 출력됨.
  원하는 최종 해상도 512×912를 얻기 위해 EmptyFlux2LatentImage에
  2배인 1024×1824를 입력함으로써 보정.
  """
  return {
    # diffusion 모델 로드 (fp8)
    '1': {
      'class_type': 'UNETLoader',
      'inputs': {
        'unet_name': COMFYUI_MODEL,
        'weight_dtype': 'fp8_e4m3fn',
      },
    },
    # VAE 로드
    '2': {
      'class_type': 'VAELoader',
      'inputs': {
        'vae_name': COMFYUI_VAE,
      },
    },
    # CLIP 로드 (clip_l + t5xxl 동시)
    '3': {
      'class_type': 'DualCLIPLoader',
      'inputs': {
        'clip_name1': COMFYUI_CLIP,
        'clip_name2': COMFYUI_CLIP2,
        'type': 'flux',
      },
    },
    # 포지티브 프롬프트 (clip_l, t5xxl에 텍스트 직접 입력)
    '4': {
      'class_type': 'CLIPTextEncodeFlux',
      'inputs': {
        'clip': ['3', 0],
        'clip_l': prompt,
        't5xxl': prompt,
        'guidance': 3.5,
      },
    },
    # 빈 Latent (9:16 세로 비율, FLUX는 8의 배수 필요)
    # 주의: 현재 ComfyUI 설정에서 생성 해상도가 약 50% 축소되므로 2배 입력
    '5': {
      'class_type': 'EmptyFlux2LatentImage',
      'inputs': {
        'width': 1024,
        'height': 1824,
        'batch_size': 1,
      },
    },
    # 샘플러
    '6': {
      'class_type': 'KSampler',
      'inputs': {
        'seed': int(uuid.uuid4().int % (2 ** 32)),
        'steps': 20,
        'cfg': 3.5,
        'sampler_name': 'euler',
        'scheduler': 'karras',
        'denoise': 1.0,
        'model': ['1', 0],
        'positive': ['4', 0],
        'negative': ['4', 0],
        'latent_image': ['5', 0],
      },
    },
    # VAE 디코딩
    '7': {
      'class_type': 'VAEDecode',
      'inputs': {
        'samples': ['6', 0],
        'vae': ['2', 0],
      },
    },
    # 이미지 저장
    '8': {
      'class_type': 'SaveImage',
      'inputs': {
        'images': ['7', 0],
        'filename_prefix': 'shorts_',
      },
    },
  }


# ──────────────────────────────────────────────
# ComfyUI API 호출
# ──────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10), reraise=True)
def submit_prompt(workflow: dict) -> str:
  """workflow 제출 → prompt_id 반환"""
  payload = {'prompt': workflow, 'client_id': str(uuid.uuid4())}
  response = requests.post(f'{COMFYUI_BASE_URL}/prompt', json=payload, timeout=30)
  response.raise_for_status()
  prompt_id = response.json().get('prompt_id')
  if not prompt_id:
    raise ValueError(f'prompt_id 없음: {response.json()}')
  logger.info('제출 완료 (prompt_id: %s)', prompt_id)
  return prompt_id


def poll_until_done(prompt_id: str) -> dict:
  """이미지 생성 완료 대기 (1초 폴링, 최대 COMFYUI_MAX_WAIT초)"""
  import time

  logger.info('이미지 생성 대기 중... (최대 %d초)', COMFYUI_MAX_WAIT)
  start = time.time()

  while True:
    elapsed = time.time() - start
    if elapsed > COMFYUI_MAX_WAIT:
      raise TimeoutError(f'이미지 생성 시간 초과 ({COMFYUI_MAX_WAIT}초)')

    try:
      response = requests.get(f'{COMFYUI_BASE_URL}/history/{prompt_id}', timeout=10)
      response.raise_for_status()
      history = response.json()

      if prompt_id in history:
        outputs = history[prompt_id].get('outputs', {})
        if outputs:
          logger.info('이미지 생성 완료 (%.1f초 소요)', elapsed)
          return outputs
    except requests.exceptions.RequestException as e:
      logger.warning('history 조회 실패: %s', e)

    time.sleep(1)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10), reraise=True)
def download_image(filename: str) -> bytes:
  """ComfyUI output에서 이미지 다운로드"""
  response = requests.get(
    f'{COMFYUI_BASE_URL}/view',
    params={'filename': filename, 'type': 'output'},
    timeout=30,
  )
  response.raise_for_status()
  logger.info('이미지 다운로드 완료 (%d bytes)', len(response.content))
  return response.content


# ──────────────────────────────────────────────
# 메인 생성 함수
# ──────────────────────────────────────────────

def generate_image(prompt: str, idx: int, use_cache: bool = True) -> str:
  """씬 1개 이미지 생성 → 로컬 캐시 경로 반환"""
  cache_path = get_cache_path(prompt, idx)

  if use_cache and cache_path.exists():
    logger.info('캐시 사용: %s', cache_path)
    return str(cache_path.resolve())

  # 1. workflow 조립 및 제출
  workflow = build_workflow(prompt)
  prompt_id = submit_prompt(workflow)

  # 2. 완료 대기
  outputs = poll_until_done(prompt_id)

  # 3. 파일명 추출
  image_files = outputs.get('8', {}).get('images', [])
  if not image_files:
    raise RuntimeError(f'출력 이미지 없음 (prompt_id: {prompt_id})')

  filename = image_files[0].get('filename', '')
  if not filename:
    raise RuntimeError('이미지 파일명 추출 실패')

  # 4. 다운로드 및 캐시 저장
  image_data = download_image(filename)
  cache_path.write_bytes(image_data)
  logger.info('씬 %d 저장 완료: %s', idx + 1, cache_path)

  return str(cache_path.resolve())


def generate_all_images(
  image_prompts: list[str],
  use_cache: bool = True,
) -> list[str]:
  """Step 2 메인 함수: 전체 씬 이미지 생성"""
  logger.info('이미지 생성 시작 (총 %d씬)', len(image_prompts))
  paths: list[str] = []

  for idx, prompt in enumerate(image_prompts):
    logger.info('씬 %d/%d 생성 중...', idx + 1, len(image_prompts))
    path = generate_image(prompt, idx, use_cache=use_cache)
    paths.append(path)

  logger.info('전체 이미지 생성 완료 (%d개)', len(paths))
  return paths


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def cmd_check() -> None:
  """서버 연결 및 모델 존재 여부 확인"""
  print(f'서버 주소: {COMFYUI_BASE_URL}')

  try:
    response = requests.get(f'{COMFYUI_BASE_URL}/system_stats', timeout=10)
    response.raise_for_status()
    info = response.json()
    print(f'[OK] 서버 연결 성공')
    print(f'     ComfyUI: {info["system"].get("comfyui_version", "?")}')
    print(f'     GPU: {info["devices"][0]["name"] if info.get("devices") else "없음"}')
  except Exception as e:
    print(f'[FAIL] 서버 연결 실패: {e}')
    return

  try:
    # UNETLoader 기준으로 diffusion_models 폴더 모델 목록 확인
    response = requests.get(f'{COMFYUI_BASE_URL}/object_info/UNETLoader', timeout=10)
    data = response.json()
    models = data.get('UNETLoader', {}).get('input', {}).get('required', {}).get('unet_name', [[]])[0]
    if COMFYUI_MODEL in models:
      print(f'[OK] 모델 확인: {COMFYUI_MODEL}')
    else:
      print(f'[WARN] 모델 미확인: {COMFYUI_MODEL}')
      print(f'       diffusion_models 목록: {models}')
      # checkpoints 폴더도 추가 확인
      resp2 = requests.get(f'{COMFYUI_BASE_URL}/object_info/CheckpointLoaderSimple', timeout=10)
      ckpts = resp2.json().get('CheckpointLoaderSimple', {}).get('input', {}).get('required', {}).get('ckpt_name', [[]])[0]
      if COMFYUI_MODEL in ckpts:
        print(f'[INFO] checkpoints 폴더에서 발견: {COMFYUI_MODEL}')
      else:
        print(f'       checkpoints 목록: {ckpts}')
  except Exception as e:
    print(f'[FAIL] 모델 확인 실패: {e}')


if __name__ == '__main__':
  parser = argparse.ArgumentParser(description='Step 2: ComfyUI 웹툰 이미지 생성')
  parser.add_argument('nlp_cache', nargs='?', help='Step 1 캐시 JSON 파일 경로')
  parser.add_argument('--check', action='store_true', help='서버 연결 및 모델 확인')
  parser.add_argument('--scene', type=int, default=0, help='특정 씬만 생성 (1부터 시작, 0=전체)')
  parser.add_argument('--no-cache', action='store_true', help='캐시 무시하고 재생성')
  args = parser.parse_args()

  if args.check:
    cmd_check()
    raise SystemExit(0)

  if not args.nlp_cache:
    parser.print_help()
    raise SystemExit(1)

  nlp_path = Path(args.nlp_cache)
  if not nlp_path.exists():
    logger.error('파일 없음: %s', nlp_path)
    raise SystemExit(1)

  with open(nlp_path, 'r', encoding='utf-8') as f:
    nlp_result = json.load(f)

  image_prompts: list[str] = nlp_result.get('image_prompts', [])
  if not image_prompts:
    logger.error('image_prompts 없음')
    raise SystemExit(1)

  use_cache = not args.no_cache

  if args.scene > 0:
    # 단일 씬 생성
    scene_idx = args.scene - 1
    if scene_idx >= len(image_prompts):
      logger.error('씬 번호 범위 초과 (최대 %d)', len(image_prompts))
      raise SystemExit(1)
    prompt = image_prompts[scene_idx]
    print(f'\n씬 {args.scene} 이미지 생성 시작')
    print(f'프롬프트: {prompt[:80]}...\n')
    path = generate_image(prompt, scene_idx, use_cache=use_cache)
    print(f'\n[OK] 씬 {args.scene} 완료: {path}')
  else:
    # 전체 씬 생성
    print(f'\n전체 {len(image_prompts)}씬 이미지 생성 시작\n')
    paths = generate_all_images(image_prompts, use_cache=use_cache)
    print(f'\n[OK] 전체 완료')
    for i, p in enumerate(paths, 1):
      print(f'  씬 {i}: {p}')
