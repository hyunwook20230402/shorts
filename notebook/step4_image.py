"""
Step 4: ComfyUI Flux.1-dev FP8로 씬별 정지 이미지 생성
"""

import json
import logging
import os
import random
import shutil
import time
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# 환경변수
COMFYUI_HOST = os.getenv('COMFYUI_HOST', 'http://127.0.0.1:8188')
LORA_STRENGTH = float(os.getenv('LORA_STRENGTH', '0.8'))
STILL_IMAGE_CFG = float(os.getenv('STILL_IMAGE_CFG', '7.5'))
COMFYUI_OUTPUT_DIR = Path(os.getenv('COMFYUI_OUTPUT_DIR', 'ComfyUI/output'))
COMFYUI_INPUT_DIR = Path(os.getenv('COMFYUI_INPUT_DIR', 'ComfyUI/input'))
COMFYUI_MAX_WAIT = int(os.getenv('COMFYUI_MAX_WAIT', '1200'))

# 업스케일링 관련 환경변수
UPSCALE_MODEL = os.getenv('UPSCALE_MODEL', '4x-UltraSharp.pth')

# Flux 관련 환경변수
FLUX_UNET = os.getenv('FLUX_UNET', 'flux1-dev-fp8.safetensors')
FLUX_LORA_NAME = os.getenv('FLUX_LORA_NAME', 'GuoFeng5-FLUX.1-Lora.safetensors')
FLUX_LORA_STRENGTH = float(os.getenv('FLUX_LORA_STRENGTH', '0.8'))
FLUX_STEPS = int(os.getenv('FLUX_STEPS', '20'))
FLUX_GUIDANCE = float(os.getenv('FLUX_GUIDANCE', '4.0'))

MAX_RETRIES = 3


def get_sentence_still_path(poem_dir: Path, scene_idx: int, sent_idx: int) -> Path:
  """문장 단위 정지 이미지 캐시 경로 생성"""
  return poem_dir / 'step4' / f'scene{scene_idx:02d}_sent{sent_idx:02d}_still.png'


def cmd_check() -> bool:
  """ComfyUI 연결 확인"""
  try:
    response = requests.get(f'{COMFYUI_HOST}/system_stats', timeout=3)
    if response.status_code != 200:
      logger.error(f'✗ ComfyUI 오류: {response.status_code}')
      return False
    logger.info(f'✓ ComfyUI 연결 성공: {COMFYUI_HOST}')
    return True
  except Exception as e:
    logger.error(f'✗ ComfyUI 연결 실패: {e}')
    return False


def check_upscale_model_available() -> bool:
  """업스케일 모델 존재 여부 확인"""
  try:
    response = requests.get(f'{COMFYUI_HOST}/object_info/UpscaleModelLoader', timeout=3)
    if response.status_code == 200:
      logger.info('✓ 업스케일 모델 로더 사용 가능')
      return True
    logger.warning('⚠ 업스케일 모델 로더 미지원 (단순 리사이즈로 대체)')
    return False
  except Exception as e:
    logger.warning(f'⚠ 업스케일 모델 확인 실패: {e} (단순 리사이즈로 대체)')
    return False


def build_flux_workflow(
  prompt: str,
  lora_strength: float = FLUX_LORA_STRENGTH,
  steps: int = FLUX_STEPS,
  guidance: float = FLUX_GUIDANCE,
  seed: int = -1,
) -> dict:
  """
  Flux.1-dev FP8 워크플로우 (네거티브 프롬프트 없음).

  노드 구성:
  1: UNETLoader (flux1-dev-fp8)
  2: LoraLoader (Flux LoRA)
  3: DualCLIPLoader (clip_l + t5xxl_fp8)
  4: CLIPTextEncode (positive only)
  5: FluxGuidance
  6: VAELoader (ae.safetensors)
  7: EmptyLatentImage (512×912)
  8: ModelSamplingFlux
  9: RandomNoise
  10: BasicGuider
  11: KSamplerSelect
  12: BasicScheduler
  13: SamplerCustomAdvanced
  14: VAEDecode
  20: UpscaleModelLoader
  21: ImageUpscaleWithModel
  22: ImageScale (1080×1920)
  23: SaveImage
  """
  return {
    '1': {
      'class_type': 'UNETLoader',
      'inputs': {
        'unet_name': FLUX_UNET,
        'weight_dtype': 'fp8_e4m3fn',
      }
    },
    '2': {
      'class_type': 'LoraLoader',
      'inputs': {
        'model': ['1', 0],
        'clip': ['3', 0],
        'lora_name': FLUX_LORA_NAME,
        'strength_model': lora_strength,
        'strength_clip': lora_strength,
      }
    },
    '3': {
      'class_type': 'DualCLIPLoader',
      'inputs': {
        'clip_name1': 'clip_l.safetensors',
        'clip_name2': 't5xxl_fp8_e4m3fn.safetensors',
        'type': 'flux',
      }
    },
    '4': {
      'class_type': 'CLIPTextEncode',
      'inputs': {
        'clip': ['2', 1],
        'text': prompt,
      }
    },
    '5': {
      'class_type': 'FluxGuidance',
      'inputs': {
        'conditioning': ['4', 0],
        'guidance': guidance,
      }
    },
    '6': {
      'class_type': 'VAELoader',
      'inputs': {'vae_name': 'ae.safetensors'}
    },
    '7': {
      'class_type': 'EmptyLatentImage',
      'inputs': {'width': 576, 'height': 1024, 'batch_size': 1}
    },
    '8': {
      'class_type': 'ModelSamplingFlux',
      'inputs': {
        'model': ['2', 0],
        'max_shift': 1.15,
        'base_shift': 0.5,
        'width': 576,
        'height': 1024,
      }
    },
    '9': {
      'class_type': 'RandomNoise',
      'inputs': {'noise_seed': seed if seed >= 0 else random.randint(0, 2**31 - 1)}
    },
    '10': {
      'class_type': 'BasicGuider',
      'inputs': {
        'model': ['8', 0],
        'conditioning': ['5', 0],
      }
    },
    '11': {
      'class_type': 'KSamplerSelect',
      'inputs': {'sampler_name': 'euler'}
    },
    '12': {
      'class_type': 'BasicScheduler',
      'inputs': {
        'model': ['8', 0],
        'scheduler': 'simple',
        'steps': steps,
        'denoise': 1.0,
      }
    },
    '13': {
      'class_type': 'SamplerCustomAdvanced',
      'inputs': {
        'noise': ['9', 0],
        'guider': ['10', 0],
        'sampler': ['11', 0],
        'sigmas': ['12', 0],
        'latent_image': ['7', 0],
      }
    },
    '14': {
      'class_type': 'VAEDecode',
      'inputs': {
        'samples': ['13', 0],
        'vae': ['6', 0],
      }
    },
    '20': {
      'class_type': 'UpscaleModelLoader',
      'inputs': {'model_name': UPSCALE_MODEL}
    },
    '21': {
      'class_type': 'ImageUpscaleWithModel',
      'inputs': {'upscale_model': ['20', 0], 'image': ['14', 0]}
    },
    '22': {
      'class_type': 'ImageScale',
      'inputs': {
        'image': ['21', 0],
        'upscale_method': 'lanczos',
        'width': 1080,
        'height': 1920,
        'crop': 'center',
      }
    },
    '23': {
      'class_type': 'SaveImage',
      'inputs': {'images': ['22', 0], 'filename_prefix': 'shorts_flux'}
    }
  }


def submit_prompt_to_comfyui(workflow: dict) -> str:
  """ComfyUI에 워크플로우 제출. 반환: prompt_id"""
  try:
    response = requests.post(
      f'{COMFYUI_HOST}/prompt',
      json={"prompt": workflow, "client_id": "shorts_pipeline"},
      timeout=30
    )
    if response.status_code == 200:
      data = response.json()
      prompt_id = data.get('prompt_id')
      logger.info(f'워크플로우 제출 성공: {prompt_id}')
      return prompt_id
    else:
      logger.error(f'ComfyUI 제출 실패: {response.status_code} {response.text}')
      raise RuntimeError(f'ComfyUI 오류: {response.status_code}')
  except Exception as e:
    logger.error(f'ComfyUI 제출 오류: {e}')
    raise


def poll_until_done(prompt_id: str, timeout: int = COMFYUI_MAX_WAIT) -> bool:
  """ComfyUI 작업 완료 대기. 반환: True (성공), False (실패/타임아웃)"""
  start_time = time.time()

  while time.time() - start_time < timeout:
    try:
      response = requests.get(f'{COMFYUI_HOST}/history/{prompt_id}', timeout=5)
      if response.status_code == 200:
        history = response.json()
        if prompt_id in history:
          record = history[prompt_id]
          if record.get('status', {}).get('status_str') == 'success':
            logger.info(f'작업 완료: {prompt_id}')
            return True
          elif record.get('status', {}).get('status_str') == 'executing':
            logger.debug(f'작업 진행 중: {prompt_id}')
            time.sleep(5)
            continue
    except Exception as e:
      logger.debug(f'상태 조회 오류: {e}')

    time.sleep(5)

  logger.error(f'작업 타임아웃: {prompt_id}')
  return False


def download_generated_still(prompt_id: str) -> Optional[Path]:
  """ComfyUI history API에서 생성된 정지 이미지 PNG 파일 추출"""
  try:
    response = requests.get(f'{COMFYUI_HOST}/history/{prompt_id}', timeout=5)
    if response.status_code != 200:
      logger.error(f'history 조회 실패: {response.status_code}')
      return None

    history = response.json()
    if prompt_id not in history:
      logger.error(f'history에서 {prompt_id} 찾을 수 없음')
      return None

    outputs = history[prompt_id].get('outputs', {})

    # SaveImage 노드를 순회하여 첫 번째 이미지 찾기
    for node_id in outputs:
      node_output = outputs[node_id]
      images = node_output.get('images', [])
      if images:
        filename = images[0]['filename']
        png_path = COMFYUI_OUTPUT_DIR / filename
        if png_path.exists():
          logger.info(f'정지 이미지 발견: {png_path}')
          return png_path

    logger.error('SaveImage 노드 출력 없음')
    return None

  except Exception as e:
    logger.error(f'정지 이미지 다운로드 오류: {e}')
    return None


FLUX_STYLE_SUFFIX_CHARACTER = (
  'traditional korean hanbok, joseon dynasty clothing, '
  'traditional korean accessories, korean traditional hair ornaments, '
  'gat hat, binyeo hairpin, '
  'traditional straw sandals, wooden clogs, leather shoes, '
  'traditional east asian robes, ink wash painting style, guofeng, '
  'ancient joseon era attire only, historical garments'
)

FLUX_STYLE_SUFFIX_NO_CHARACTER = (
  'traditional east asian scenery, ink wash painting style, guofeng, '
  'uninhabited landscape, empty scenery, desolate nature, '
  'still life of nature, untouched wilderness'
)

COMPOSITION_KEYWORDS = {
  'back_view': 'viewed from behind, back of the figure facing the camera',
  'front_closeup': 'close-up front view, face and upper body filling the frame',
  'side_profile': 'side profile view, silhouette against the background',
  'over_shoulder': 'over-the-shoulder shot, viewing from behind one figure',
  'bird_eye': "bird's eye view, looking straight down from above",
  'low_angle': 'low angle shot, looking up from below',
  'wide_establishing': 'wide establishing shot, vast landscape, distant view',
  'dutch_tilt': 'dutch angle, tilted camera frame, dramatic diagonal composition',
}


def generate_all_images(
  schedule_path: str,
  poem_dir: Path,
  use_cache: bool = True
) -> list[str]:
  """
  Step 4: 모든 문장별 정지 이미지 생성 (Flux.1-dev FP8, 테마별 색감 적용)

  반환: still_image_paths (문장 순서대로 정렬된 PNG 경로 리스트)
  """
  with open(schedule_path, 'r', encoding='utf-8') as f:
    schedule_data = json.load(f)

  # 테마 파라미터 로드
  theme_code = 'A'
  nlp_path = Path(poem_dir) / 'step1' / 'nlp.json'
  if nlp_path.exists():
    try:
      with open(nlp_path, 'r', encoding='utf-8') as f:
        nlp_data = json.load(f)
      theme_code = nlp_data.get('surface_theme', nlp_data.get('theme', 'A'))
    except Exception:
      pass

  try:
    from theme_config import get_image_params
    theme_params = get_image_params(theme_code)
  except Exception:
    theme_params = {'lora': LORA_STRENGTH, 'cfg': STILL_IMAGE_CFG, 'color': '', 'neg_extra': ''}

  theme_color = theme_params.get('color', '')
  logger.info(f'테마={theme_code}: color={theme_color!r}')

  schedules = schedule_data.get('sentence_schedules', [])
  still_paths = []

  logger.info(f'이미지 생성 시작: 총 {len(schedules)}개 문장 (Flux.1-dev FP8)')

  for i, sched in enumerate(schedules):
    scene_idx = sched['scene_index']
    sent_idx = sched.get('sentence_index', 0)

    out_path = get_sentence_still_path(poem_dir, scene_idx, sent_idx)
    out_name = out_path.name

    if use_cache and out_path.exists():
      logger.info(f'  - [{i+1}/{len(schedules)}] 캐시 사용: {out_name}')
      still_paths.append(str(out_path))
      continue

    # 테마 색감 키워드를 프롬프트에 추가
    base_prompt = sched['image_prompt']
    prompt_text = f'{base_prompt}, {theme_color}' if theme_color else base_prompt

    # main_focus 파싱 (composition 방어에 필요)
    main_focus = sched.get('main_focus', ['background'])
    if isinstance(main_focus, str):
      main_focus = [main_focus]
    has_character = 'character' in main_focus

    # composition 구도 키워드 강제 주입
    comp = sched.get('composition', 'wide_establishing')
    # 비인물 씬에서 인물 구도 키워드 사용 방지 → wide_establishing 폴백
    figure_comps = {'back_view', 'front_closeup', 'side_profile', 'over_shoulder'}
    if not has_character and comp in figure_comps:
      comp = 'wide_establishing'
    comp_keywords = COMPOSITION_KEYWORDS.get(comp, '')
    if comp_keywords:
      prompt_text = f'{prompt_text}, {comp_keywords}'

    if has_character:
      flux_prompt = f'{prompt_text}, {FLUX_STYLE_SUFFIX_CHARACTER}'
    else:
      flux_prompt = f'{prompt_text}, {FLUX_STYLE_SUFFIX_NO_CHARACTER}'

    logger.info(f'  - [{i+1}/{len(schedules)}] ComfyUI Flux 호출 중: {out_name}')

    try:
      workflow = build_flux_workflow(
        flux_prompt,
        lora_strength=FLUX_LORA_STRENGTH,
        steps=FLUX_STEPS,
        guidance=FLUX_GUIDANCE,
      )
      prompt_id = submit_prompt_to_comfyui(workflow)
      if not poll_until_done(prompt_id):
        raise RuntimeError(f'Scene {scene_idx} Flux 타임아웃')
      output_png = download_generated_still(prompt_id)
      if not output_png:
        raise RuntimeError(f'Scene {scene_idx} Flux 이미지 없음')
      out_path.parent.mkdir(parents=True, exist_ok=True)
      shutil.copy2(str(output_png), str(out_path))
      still_paths.append(str(out_path))
      logger.info(f'    ✓ 생성 완료: {out_name}')

    except Exception as e:
      logger.error(f'✗ Scene {scene_idx} Sent {sent_idx} 생성 실패: {e}')
      raise

  return still_paths


if __name__ == '__main__':
  import sys

  logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
      logging.FileHandler('step4_image.log', encoding='utf-8'),
      logging.StreamHandler()
    ]
  )

  logger.info('=' * 70)
  logger.info('Step 4: ComfyUI Flux.1-dev FP8 정지 이미지 생성')
  logger.info('=' * 70)

  if len(sys.argv) < 2:
    logger.error('✗ 사용법: python step4_image.py <poem_dir>')
    exit(1)

  poem_dir = Path(sys.argv[1])

  if not cmd_check():
    logger.error('✗ ComfyUI 연결 실패')
    exit(1)

  schedule_path = poem_dir / 'step3' / 'sentence_schedule.json'
  if not schedule_path.exists():
    logger.error(f'✗ Step 3 문장 스케줄 없음: {schedule_path}')
    exit(1)

  try:
    still_paths = generate_all_images(str(schedule_path), poem_dir, use_cache=True)

    logger.info(f'\n✓ 정지 이미지 생성 완료: {len(still_paths)}개')
    for i, still in enumerate(still_paths):
      logger.info(f'  [{i}] {Path(still).name}')

    logger.info('=' * 70)
    exit(0)
  except Exception as e:
    logger.error(f'✗ Step 4 실패: {e}')
    exit(1)
