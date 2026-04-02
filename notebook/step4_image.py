"""
Step 4: ComfyUI (SD 1.5 + LoRA)로 씬별 정지 이미지 생성
"""

import json
import logging
import os
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
SD15_CHECKPOINT = os.getenv('SD15_CHECKPOINT', 'Realistic_Vision_V5.1.safetensors')
LORA_NAME = os.getenv('LORA_NAME', 'E38090E59BBDE9A38EE68F92E794BBE38091E58FAFE7.G2A0.safetensors')
LORA_STRENGTH = float(os.getenv('LORA_STRENGTH', '0.8'))
STILL_IMAGE_STEPS = int(os.getenv('STILL_IMAGE_STEPS', '30'))
STILL_IMAGE_CFG = float(os.getenv('STILL_IMAGE_CFG', '7.5'))
COMFYUI_OUTPUT_DIR = Path(os.getenv('COMFYUI_OUTPUT_DIR', 'ComfyUI/output'))
COMFYUI_INPUT_DIR = Path(os.getenv('COMFYUI_INPUT_DIR', 'ComfyUI/input'))
COMFYUI_MAX_WAIT = int(os.getenv('COMFYUI_MAX_WAIT', '1200'))

# IP-Adapter 관련 환경변수
IPADAPTER_MODEL = os.getenv('IPADAPTER_MODEL', 'ip-adapter_sd15.bin')
IPADAPTER_WEIGHT = float(os.getenv('IPADAPTER_WEIGHT', '0.5'))
CLIP_VISION_MODEL = os.getenv('CLIP_VISION_MODEL', 'clip_vision_h14.safetensors')
REFERENCE_IMAGE_PATH = os.getenv('REFERENCE_IMAGE_PATH', 'cache/reference/character.png')
REFERENCE_IMAGE_PATH2 = os.getenv('REFERENCE_IMAGE_PATH2', '')

MAX_RETRIES = 3


def get_sentence_still_path(poem_dir: Path, scene_idx: int, sent_idx: int) -> Path:
  """문장 단위 정지 이미지 캐시 경로 생성"""
  return poem_dir / f'step4_scene{scene_idx:02d}_sent{sent_idx:02d}_still.png'


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


def upload_reference_image_to_comfyui() -> tuple[str, str | None]:
  """참조 이미지를 ComfyUI input 폴더에 업로드하고 파일명 반환 (1장 또는 2장)"""
  ref_path = Path(REFERENCE_IMAGE_PATH)
  if not ref_path.exists():
    raise FileNotFoundError(f'참조 이미지 없음: {ref_path}')

  dest_path = COMFYUI_INPUT_DIR / 'reference_character.png'
  dest_path.parent.mkdir(parents=True, exist_ok=True)
  shutil.copy2(str(ref_path), str(dest_path))
  logger.info(f'참조 이미지 복사: {ref_path} → {dest_path}')

  ref2_filename = None
  if REFERENCE_IMAGE_PATH2:
    ref2_path = Path(REFERENCE_IMAGE_PATH2)
    if ref2_path.exists():
      dest2_path = COMFYUI_INPUT_DIR / 'reference_character2.png'
      shutil.copy2(str(ref2_path), str(dest2_path))
      ref2_filename = 'reference_character2.png'
      logger.info(f'참조 이미지 2 복사: {ref2_path} → {dest2_path}')

  return 'reference_character.png', ref2_filename


def check_ipadapter_available() -> bool:
  """IP-Adapter 커스텀 노드 설치 여부 확인"""
  try:
    response = requests.get(f'{COMFYUI_HOST}/object_info/IPAdapterModelLoader', timeout=3)
    available = response.status_code == 200
    if available:
      logger.info('✓ IP-Adapter 커스텀 노드 설치됨')
    else:
      logger.info('⚠ IP-Adapter 커스텀 노드 미설치 (기본 워크플로우 사용)')
    return available
  except Exception as e:
    logger.warning(f'IP-Adapter 확인 실패: {e} (기본 워크플로우 사용)')
    return False


def build_still_image_workflow(prompt: str, negative_prompt: str) -> dict:
  """
  정지 이미지 생성 워크플로우 (기본 파이프라인, 8노드)

  노드 구성:
  1: CheckpointLoaderSimple
  2: LoraLoader (국풍 LoRA)
  3: CLIPTextEncode (positive)
  4: CLIPTextEncode (negative)
  5: EmptyLatentImage
  6: KSampler
  7: VAEDecode
  8: SaveImage
  """
  return {
    '1': {
      'class_type': 'CheckpointLoaderSimple',
      'inputs': {'ckpt_name': SD15_CHECKPOINT}
    },
    '2': {
      'class_type': 'LoraLoader',
      'inputs': {
        'model': ['1', 0],
        'clip': ['1', 1],
        'lora_name': LORA_NAME,
        'strength_model': LORA_STRENGTH,
        'strength_clip': LORA_STRENGTH
      }
    },
    '3': {
      'class_type': 'CLIPTextEncode',
      'inputs': {'clip': ['2', 1], 'text': prompt}
    },
    '4': {
      'class_type': 'CLIPTextEncode',
      'inputs': {'clip': ['2', 1], 'text': negative_prompt}
    },
    '5': {
      'class_type': 'EmptyLatentImage',
      'inputs': {'width': 512, 'height': 912, 'batch_size': 1}
    },
    '6': {
      'class_type': 'KSampler',
      'inputs': {
        'model': ['2', 0],
        'positive': ['3', 0],
        'negative': ['4', 0],
        'latent_image': ['5', 0],
        'seed': 42,
        'steps': STILL_IMAGE_STEPS,
        'cfg': STILL_IMAGE_CFG,
        'sampler_name': 'euler_ancestral',
        'scheduler': 'karras',
        'denoise': 1.0
      }
    },
    '7': {
      'class_type': 'VAEDecode',
      'inputs': {'samples': ['6', 0], 'vae': ['1', 2]}
    },
    '8': {
      'class_type': 'SaveImage',
      'inputs': {'images': ['7', 0], 'filename_prefix': 'shorts_still'}
    }
  }


def build_still_image_workflow_with_ipadapter(prompt: str, negative_prompt: str, ref_image2: str | None = None) -> dict:
  """
  IP-Adapter 기반 캐릭터 일관성 정지 이미지 생성

  1장 참고 이미지: 12노드 / 2장 참고 이미지: 15노드
  """
  workflow = {
    '1': {
      'class_type': 'CheckpointLoaderSimple',
      'inputs': {'ckpt_name': SD15_CHECKPOINT}
    },
    '2': {
      'class_type': 'LoraLoader',
      'inputs': {
        'model': ['1', 0],
        'clip': ['1', 1],
        'lora_name': LORA_NAME,
        'strength_model': LORA_STRENGTH,
        'strength_clip': LORA_STRENGTH
      }
    },
    '3': {
      'class_type': 'CLIPTextEncode',
      'inputs': {'clip': ['2', 1], 'text': prompt}
    },
    '4': {
      'class_type': 'CLIPTextEncode',
      'inputs': {'clip': ['2', 1], 'text': negative_prompt}
    },
    '5': {
      'class_type': 'EmptyLatentImage',
      'inputs': {'width': 512, 'height': 912, 'batch_size': 1}
    },
    '6': {
      'class_type': 'CLIPVisionLoader',
      'inputs': {'clip_name': CLIP_VISION_MODEL}
    },
    '7': {
      'class_type': 'LoadImage',
      'inputs': {'image': 'reference_character.png'}
    },
    '8': {
      'class_type': 'IPAdapterModelLoader',
      'inputs': {'ipadapter_file': IPADAPTER_MODEL}
    },
    '9': {
      'class_type': 'IPAdapterAdvanced',
      'inputs': {
        'model': ['2', 0],
        'ipadapter': ['8', 0],
        'clip_vision': ['6', 0],
        'image': ['7', 0],
        'weight': IPADAPTER_WEIGHT,
        'weight_type': 'linear',
        'start_at': 0.0,
        'end_at': 1.0,
        'unfold_batch': False,
        'combine_embeds': 'concat',
        'embeds_scaling': 'V only'
      }
    }
  }

  if ref_image2:
    workflow['13'] = {
      'class_type': 'LoadImage',
      'inputs': {'image': ref_image2}
    }
    workflow['14'] = {
      'class_type': 'IPAdapterAdvanced',
      'inputs': {
        'model': ['9', 0],
        'ipadapter': ['8', 0],
        'clip_vision': ['6', 0],
        'image': ['13', 0],
        'weight': IPADAPTER_WEIGHT,
        'weight_type': 'linear',
        'start_at': 0.0,
        'end_at': 1.0,
        'unfold_batch': False,
        'combine_embeds': 'concat',
        'embeds_scaling': 'V only'
      }
    }
    ksampler_model_input = ['14', 0]
  else:
    ksampler_model_input = ['9', 0]

  workflow['10'] = {
    'class_type': 'KSampler',
    'inputs': {
      'model': ksampler_model_input,
      'positive': ['3', 0],
      'negative': ['4', 0],
      'latent_image': ['5', 0],
      'seed': 42,
      'steps': STILL_IMAGE_STEPS,
      'cfg': STILL_IMAGE_CFG,
      'sampler_name': 'euler_ancestral',
      'scheduler': 'karras',
      'denoise': 1.0
    }
  }
  workflow['11'] = {
    'class_type': 'VAEDecode',
    'inputs': {'samples': ['10', 0], 'vae': ['1', 2]}
  }
  workflow['12'] = {
    'class_type': 'SaveImage',
    'inputs': {'images': ['11', 0], 'filename_prefix': 'shorts_still'}
  }

  return workflow


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


def run_comfyui_still_workflow(prompt: str, negative: str, output_name: str) -> str:
  """ComfyUI API를 호출하여 정지 이미지를 생성하고 결과 경로 반환"""
  workflow = build_still_image_workflow(prompt, negative)
  workflow['8']['inputs']['filename_prefix'] = output_name.replace('.png', '')

  prompt_id = submit_prompt_to_comfyui(workflow)
  if not poll_until_done(prompt_id):
    raise RuntimeError(f'ComfyUI 작업 타임아웃: {output_name}')

  output_png = download_generated_still(prompt_id)
  if not output_png or not output_png.exists():
    raise FileNotFoundError(f'생성된 이미지를 찾을 수 없습니다: {output_name}')

  return str(output_png)


def generate_still_image(
  image_prompt: str,
  negative_prompt: str,
  scene_idx: int,
  sent_idx: int,
  poem_dir: Path,
  use_cache: bool = True,
  use_ipadapter: bool = False,
  ref_image2: str | None = None
) -> str:
  """
  문장 단위 정지 이미지 생성 (IP-Adapter 옵션 지원)

  반환: PNG 파일 경로
  """
  still_path = get_sentence_still_path(poem_dir, scene_idx, sent_idx)

  if use_cache and still_path.exists():
    logger.info(f'캐시된 정지 이미지 사용: {still_path}')
    return str(still_path)

  logger.info(f'Scene {scene_idx} Sent {sent_idx} 정지 이미지 생성 중...')

  prompt = image_prompt if image_prompt else 'ancient korean landscape, ink painting'

  if use_ipadapter and Path(REFERENCE_IMAGE_PATH).exists() and check_ipadapter_available():
    logger.info(f'Scene {scene_idx}: IP-Adapter 워크플로우 사용')
    workflow = build_still_image_workflow_with_ipadapter(prompt, negative_prompt, ref_image2)
    prompt_id = submit_prompt_to_comfyui(workflow)
  else:
    if use_ipadapter:
      logger.info(f'Scene {scene_idx}: 기본 워크플로우로 폴백 (IP-Adapter 미사용)')
    workflow = build_still_image_workflow(prompt, negative_prompt)
    prompt_id = submit_prompt_to_comfyui(workflow)

  if not poll_until_done(prompt_id):
    raise RuntimeError(f'Scene {scene_idx} 정지 이미지 타임아웃')

  output_png = download_generated_still(prompt_id)
  if not output_png:
    raise RuntimeError(f'Scene {scene_idx} 정지 이미지 파일 없음')

  still_path.parent.mkdir(parents=True, exist_ok=True)
  shutil.copy2(str(output_png), str(still_path))
  logger.info(f'정지 이미지 캐시 저장: {still_path}')

  return str(still_path)


def generate_all_images(
  schedule_path: str,
  poem_dir: Path,
  use_cache: bool = True
) -> list[str]:
  """
  Step 4: 모든 문장별 정지 이미지 생성

  반환: still_image_paths (문장 순서대로 정렬된 PNG 경로 리스트)
  """
  with open(schedule_path, 'r', encoding='utf-8') as f:
    schedule_data = json.load(f)

  schedules = schedule_data.get('sentence_schedules', [])
  still_paths = []

  logger.info(f'이미지 생성 시작: 총 {len(schedules)}개 문장')

  for i, sched in enumerate(schedules):
    scene_idx = sched['scene_index']
    sent_idx = sched.get('sentence_index', 0)

    out_name = f'step4_scene{scene_idx:02d}_sent{sent_idx:02d}_still.png'
    out_path = poem_dir / out_name

    if use_cache and out_path.exists():
      logger.info(f'  - [{i+1}/{len(schedules)}] 캐시 사용: {out_name}')
      still_paths.append(str(out_path))
      continue

    prompt_text = sched['image_prompt']
    neg_prompt = sched.get('negative_prompt', '')

    logger.info(f'  - [{i+1}/{len(schedules)}] ComfyUI 호출 중: {out_name}')

    try:
      result_file = run_comfyui_still_workflow(
        prompt=prompt_text,
        negative=neg_prompt,
        output_name=out_name
      )

      if result_file and os.path.exists(result_file):
        shutil.copy(result_file, out_path)
        still_paths.append(str(out_path))
        logger.info(f'    ✓ 생성 완료: {out_name}')
      else:
        raise RuntimeError(f'결과 파일 생성 실패: {out_name}')

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
  logger.info('Step 4: ComfyUI 정지 이미지 생성')
  logger.info('=' * 70)

  if len(sys.argv) < 2:
    logger.error('✗ 사용법: python step4_image.py <poem_dir>')
    exit(1)

  poem_dir = Path(sys.argv[1])

  if not cmd_check():
    logger.error('✗ ComfyUI 연결 실패')
    exit(1)

  schedule_path = poem_dir / 'step3_sentence_schedule.json'
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
    logger.error(f'\n✗ Step 4 실패: {e}', exc_info=True)
    exit(1)
