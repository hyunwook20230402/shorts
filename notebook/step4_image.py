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

# 업스케일링 관련 환경변수
UPSCALE_MODEL = os.getenv('UPSCALE_MODEL', '4x-UltraSharp.pth')

# ControlNet 관련 환경변수
CONTROLNET_MODEL = os.getenv('CONTROLNET_MODEL', 'control_v11p_sd15_openpose.pth')
CONTROLNET_STRENGTH = float(os.getenv('CONTROLNET_STRENGTH', '0.65'))
USE_CONTROLNET = os.getenv('USE_CONTROLNET', 'true').lower() == 'true'

# Flux 관련 환경변수
USE_FLUX = os.getenv('USE_FLUX', 'false').lower() == 'true'
FLUX_UNET = os.getenv('FLUX_UNET', 'flux1-dev-fp8.safetensors')
FLUX_LORA_NAME = os.getenv('FLUX_LORA_NAME', 'GuoFeng5-FLUX.1-Lora.safetensors')
FLUX_LORA_STRENGTH = float(os.getenv('FLUX_LORA_STRENGTH', '0.8'))
FLUX_STEPS = int(os.getenv('FLUX_STEPS', '20'))
FLUX_GUIDANCE = float(os.getenv('FLUX_GUIDANCE', '3.5'))

MAX_RETRIES = 3

# 포즈 스켈레톤 저장 디렉토리
POSE_REFS_DIR = Path('cache/pose_refs')


def get_sentence_still_path(poem_dir: Path, scene_idx: int, sent_idx: int) -> Path:
  """문장 단위 정지 이미지 캐시 경로 생성"""
  return poem_dir / 'step4' / f'scene{scene_idx:02d}_sent{sent_idx:02d}_still.png'


def check_controlnet_available() -> bool:
  """ControlNet 노드 + 모델 파일 존재 확인"""
  try:
    response = requests.get(f'{COMFYUI_HOST}/object_info/ControlNetLoader', timeout=3)
    if response.status_code != 200:
      logger.warning('ControlNetLoader 노드 없음')
      return False
    info = response.json()
    models = info.get('ControlNetLoader', {}).get('input', {}).get('required', {}).get('control_net_name', [[]])[0]
    if CONTROLNET_MODEL not in models:
      logger.warning('ControlNet 모델 미발견: %s', CONTROLNET_MODEL)
      return False
    logger.info('✓ ControlNet 사용 가능: %s', CONTROLNET_MODEL)
    return True
  except Exception as e:
    logger.warning('ControlNet 확인 실패: %s', e)
    return False


def create_pose_skeleton(pose_type: str) -> Path:
  """
  PIL로 OpenPose 스타일 스켈레톤 PNG 생성 (512×912, 검정 배경 + 흰색 관절/뼈대).
  pose_type별로 한 번 생성 후 재사용.
  """
  from PIL import Image, ImageDraw

  POSE_REFS_DIR.mkdir(parents=True, exist_ok=True)
  out_path = POSE_REFS_DIR / f'{pose_type}.png'
  if out_path.exists():
    return out_path

  W, H = 512, 912
  img = Image.new('RGB', (W, H), (0, 0, 0))
  draw = ImageDraw.Draw(img)

  def joint(x: int, y: int, r: int = 8) -> None:
    draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255))

  def bone(x1: int, y1: int, x2: int, y2: int) -> None:
    draw.line([(x1, y1), (x2, y2)], fill=(255, 255, 255), width=4)

  def draw_standing(cx: int, head_y: int, scale: float = 1.0) -> None:
    """서 있는 자세 스켈레톤"""
    s = scale
    hy = head_y
    neck_y = int(hy + 60 * s)
    hip_y = int(hy + 220 * s)
    knee_y = int(hy + 400 * s)
    foot_y = int(hy + 580 * s)
    shoulder_l, shoulder_r = cx - int(70 * s), cx + int(70 * s)
    elbow_l, elbow_r = cx - int(90 * s), cx + int(90 * s)
    wrist_l, wrist_r = cx - int(80 * s), cx + int(80 * s)
    elbow_y = int(hy + 200 * s)
    wrist_y = int(hy + 360 * s)
    hip_l, hip_r = cx - int(45 * s), cx + int(45 * s)
    knee_l, knee_r = cx - int(40 * s), cx + int(40 * s)
    foot_l, foot_r = cx - int(35 * s), cx + int(35 * s)

    joint(cx, hy, int(18 * s))
    bone(cx, hy, cx, neck_y)
    joint(cx, neck_y, int(10 * s))
    bone(cx, neck_y, shoulder_l, neck_y + int(30 * s))
    bone(cx, neck_y, shoulder_r, neck_y + int(30 * s))
    joint(shoulder_l, neck_y + int(30 * s))
    joint(shoulder_r, neck_y + int(30 * s))
    bone(shoulder_l, neck_y + int(30 * s), elbow_l, elbow_y)
    bone(shoulder_r, neck_y + int(30 * s), elbow_r, elbow_y)
    joint(elbow_l, elbow_y)
    joint(elbow_r, elbow_y)
    bone(elbow_l, elbow_y, wrist_l, wrist_y)
    bone(elbow_r, elbow_y, wrist_r, wrist_y)
    joint(wrist_l, wrist_y)
    joint(wrist_r, wrist_y)
    bone(cx, neck_y, cx, hip_y)
    joint(cx, hip_y, int(10 * s))
    bone(cx, hip_y, hip_l, hip_y + int(20 * s))
    bone(cx, hip_y, hip_r, hip_y + int(20 * s))
    joint(hip_l, hip_y + int(20 * s))
    joint(hip_r, hip_y + int(20 * s))
    bone(hip_l, hip_y + int(20 * s), knee_l, knee_y)
    bone(hip_r, hip_y + int(20 * s), knee_r, knee_y)
    joint(knee_l, knee_y)
    joint(knee_r, knee_y)
    bone(knee_l, knee_y, foot_l, foot_y)
    bone(knee_r, knee_y, foot_r, foot_y)
    joint(foot_l, foot_y)
    joint(foot_r, foot_y)

  if pose_type == 'prone':
    # 엎드린 자세: 수평으로 누운 형태, 화면 하단
    cy = 750
    bone(100, cy, 420, cy)  # 몸통 수평
    joint(100, cy)  # 머리
    joint(420, cy)  # 엉덩이
    bone(100, cy, 60, cy - 80)  # 왼팔 앞으로
    bone(100, cy, 140, cy - 80)
    joint(60, cy - 80)
    joint(140, cy - 80)
    bone(420, cy, 390, cy + 100)  # 왼다리
    bone(420, cy, 450, cy + 100)  # 오른다리
    joint(390, cy + 100)
    joint(450, cy + 100)
    bone(250, cy, 250, cy - 60)  # 어깨
    joint(250, cy - 60)

  elif pose_type == 'kneeling':
    # 무릎 꿇고 고개 숙인 자세
    cx = W // 2
    head_y = 300
    joint(cx, head_y, 18)
    bone(cx, head_y, cx, head_y + 60)  # 목
    bone(cx, head_y + 60, cx - 70, head_y + 100)  # 어깨
    bone(cx, head_y + 60, cx + 70, head_y + 100)
    joint(cx - 70, head_y + 100)
    joint(cx + 70, head_y + 100)
    bone(cx, head_y + 60, cx, head_y + 220)  # 몸통
    joint(cx, head_y + 220)
    bone(cx - 70, head_y + 100, cx - 100, head_y + 280)  # 팔 (앞으로)
    bone(cx + 70, head_y + 100, cx + 100, head_y + 280)
    joint(cx - 100, head_y + 280)
    joint(cx + 100, head_y + 280)
    bone(cx, head_y + 220, cx - 50, head_y + 350)  # 허벅지
    bone(cx, head_y + 220, cx + 50, head_y + 350)
    joint(cx - 50, head_y + 350)
    joint(cx + 50, head_y + 350)
    bone(cx - 50, head_y + 350, cx - 40, head_y + 480)  # 종아리 (수직)
    bone(cx + 50, head_y + 350, cx + 40, head_y + 480)
    joint(cx - 40, head_y + 480)
    joint(cx + 40, head_y + 480)

  elif pose_type == 'standing_single':
    draw_standing(W // 2, 100)

  elif pose_type == 'standing_confrontation':
    # 두 인물 대립 (좌측 = 농부/약자, 우측 = 관리/강자)
    draw_standing(160, 150, 0.85)
    draw_standing(350, 120, 0.95)

  elif pose_type == 'group_labor':
    # 3명이 숙여서 일하는 자세
    for cx_pos, head_y in [(120, 350), (256, 320), (390, 360)]:
      joint(cx_pos, head_y, 14)
      bone(cx_pos, head_y, cx_pos, head_y + 160)
      joint(cx_pos, head_y + 160)
      bone(cx_pos, head_y + 160, cx_pos - 60, head_y + 200)
      bone(cx_pos, head_y + 160, cx_pos + 60, head_y + 200)
      joint(cx_pos - 60, head_y + 200)
      joint(cx_pos + 60, head_y + 200)
      bone(cx_pos - 60, head_y + 200, cx_pos - 80, head_y + 340)
      bone(cx_pos + 60, head_y + 200, cx_pos + 80, head_y + 340)
      joint(cx_pos - 80, head_y + 340)
      joint(cx_pos + 80, head_y + 340)
      bone(cx_pos, head_y + 160, cx_pos - 30, head_y + 360)
      bone(cx_pos, head_y + 160, cx_pos + 30, head_y + 360)
      joint(cx_pos - 30, head_y + 360)
      joint(cx_pos + 30, head_y + 360)

  elif pose_type == 'group_celebration':
    # 3명이 서서 모인 자세
    for cx_pos, head_y in [(130, 160), (256, 120), (380, 150)]:
      draw_standing(cx_pos, head_y, 0.82)

  elif pose_type == 'sitting_scholar':
    # 앉아서 글 읽는 자세 (다리 접고 앉음)
    cx = W // 2
    head_y = 200
    joint(cx, head_y, 18)
    bone(cx, head_y, cx, head_y + 60)
    bone(cx, head_y + 60, cx - 70, head_y + 100)
    bone(cx, head_y + 60, cx + 70, head_y + 100)
    joint(cx - 70, head_y + 100)
    joint(cx + 70, head_y + 100)
    bone(cx - 70, head_y + 100, cx - 100, head_y + 280)  # 팔 (아래로 책 들기)
    bone(cx + 70, head_y + 100, cx + 100, head_y + 280)
    joint(cx - 100, head_y + 280)
    joint(cx + 100, head_y + 280)
    bone(cx, head_y + 60, cx, head_y + 320)  # 몸통
    joint(cx, head_y + 320)
    bone(cx, head_y + 320, cx - 100, head_y + 420)  # 접은 다리
    bone(cx, head_y + 320, cx + 100, head_y + 420)
    joint(cx - 100, head_y + 420)
    joint(cx + 100, head_y + 420)
    bone(cx - 100, head_y + 420, cx - 60, head_y + 520)
    bone(cx + 100, head_y + 420, cx + 60, head_y + 520)
    joint(cx - 60, head_y + 520)
    joint(cx + 60, head_y + 520)

  elif pose_type == 'walking_journey':
    # 걷는 자세 (한 발 앞으로)
    cx = W // 2
    head_y = 100
    joint(cx, head_y, 18)
    bone(cx, head_y, cx, head_y + 60)
    bone(cx, head_y + 60, cx - 70, head_y + 100)
    bone(cx, head_y + 60, cx + 70, head_y + 100)
    joint(cx - 70, head_y + 100)
    joint(cx + 70, head_y + 100)
    bone(cx - 70, head_y + 100, cx - 110, head_y + 280)
    bone(cx + 70, head_y + 100, cx + 60, head_y + 260)
    joint(cx - 110, head_y + 280)
    joint(cx + 60, head_y + 260)
    bone(cx, head_y + 60, cx, head_y + 320)
    joint(cx, head_y + 320)
    bone(cx, head_y + 320, cx - 40, head_y + 500)  # 앞발
    bone(cx, head_y + 320, cx + 60, head_y + 480)  # 뒷발
    joint(cx - 40, head_y + 500)
    joint(cx + 60, head_y + 480)
    bone(cx - 40, head_y + 500, cx - 60, head_y + 680)
    bone(cx + 60, head_y + 480, cx + 80, head_y + 660)
    joint(cx - 60, head_y + 680)
    joint(cx + 80, head_y + 660)

  elif pose_type == 'landscape_only':
    # 인물 없는 자연 풍경 — 빈 스켈레톤 (ControlNet 영향 최소화)
    pass

  elif pose_type == 'embrace_grief':
    # 슬픔/애도 — 고개 숙이고 손으로 얼굴 가리는 자세
    cx = W // 2
    head_y = 200
    joint(cx, head_y, 18)
    bone(cx, head_y, cx, head_y + 60)
    bone(cx, head_y + 60, cx - 70, head_y + 100)
    bone(cx, head_y + 60, cx + 70, head_y + 100)
    joint(cx - 70, head_y + 100)
    joint(cx + 70, head_y + 100)
    bone(cx - 70, head_y + 100, cx - 30, head_y + 160)  # 손을 얼굴로
    bone(cx + 70, head_y + 100, cx + 30, head_y + 160)
    joint(cx - 30, head_y + 160)
    joint(cx + 30, head_y + 160)
    bone(cx, head_y + 60, cx, head_y + 380)
    joint(cx, head_y + 380)
    bone(cx, head_y + 380, cx - 50, head_y + 560)
    bone(cx, head_y + 380, cx + 50, head_y + 560)
    joint(cx - 50, head_y + 560)
    joint(cx + 50, head_y + 560)
    bone(cx - 50, head_y + 560, cx - 60, head_y + 740)
    bone(cx + 50, head_y + 560, cx + 60, head_y + 740)
    joint(cx - 60, head_y + 740)
    joint(cx + 60, head_y + 740)

  img.save(str(out_path))
  logger.info('포즈 스켈레톤 생성: %s', out_path)
  return out_path


def upload_pose_to_comfyui(pose_path: Path) -> str:
  """포즈 스켈레톤을 ComfyUI input 폴더에 복사. 반환: ComfyUI 파일명"""
  dest = COMFYUI_INPUT_DIR / pose_path.name
  dest.parent.mkdir(parents=True, exist_ok=True)
  shutil.copy2(str(pose_path), str(dest))
  logger.info('포즈 이미지 복사: %s → %s', pose_path.name, dest)
  return pose_path.name


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


def build_still_image_workflow(
  prompt: str,
  negative_prompt: str,
  lora_strength: float = LORA_STRENGTH,
  cfg_scale: float = STILL_IMAGE_CFG,
) -> dict:
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
        'strength_model': lora_strength,
        'strength_clip': lora_strength
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
        'cfg': cfg_scale,
        'sampler_name': 'euler_ancestral',
        'scheduler': 'karras',
        'denoise': 1.0
      }
    },
    '7': {
      'class_type': 'VAEDecode',
      'inputs': {'samples': ['6', 0], 'vae': ['1', 2]}
    },
    '20': {
      'class_type': 'UpscaleModelLoader',
      'inputs': {'model_name': UPSCALE_MODEL}
    },
    '21': {
      'class_type': 'ImageUpscaleWithModel',
      'inputs': {'upscale_model': ['20', 0], 'image': ['7', 0]}
    },
    '22': {
      'class_type': 'ImageScale',
      'inputs': {
        'image': ['21', 0],
        'upscale_method': 'lanczos',
        'width': 1080,
        'height': 1920,
        'crop': 'center'
      }
    },
    '8': {
      'class_type': 'SaveImage',
      'inputs': {'images': ['22', 0], 'filename_prefix': 'shorts_still'}
    }
  }


def build_still_image_workflow_with_ipadapter(
  prompt: str,
  negative_prompt: str,
  ref_image2: str | None = None,
  lora_strength: float = LORA_STRENGTH,
  cfg_scale: float = STILL_IMAGE_CFG,
) -> dict:
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
        'strength_model': lora_strength,
        'strength_clip': lora_strength
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
      'cfg': cfg_scale,
      'sampler_name': 'euler_ancestral',
      'scheduler': 'karras',
      'denoise': 1.0
    }
  }
  workflow['11'] = {
    'class_type': 'VAEDecode',
    'inputs': {'samples': ['10', 0], 'vae': ['1', 2]}
  }
  workflow['20'] = {
    'class_type': 'UpscaleModelLoader',
    'inputs': {'model_name': UPSCALE_MODEL}
  }
  workflow['21'] = {
    'class_type': 'ImageUpscaleWithModel',
    'inputs': {'upscale_model': ['20', 0], 'image': ['11', 0]}
  }
  workflow['22'] = {
    'class_type': 'ImageScale',
    'inputs': {
      'image': ['21', 0],
      'upscale_method': 'lanczos',
      'width': 1080,
      'height': 1920,
      'crop': 'center'
    }
  }
  workflow['12'] = {
    'class_type': 'SaveImage',
    'inputs': {'images': ['22', 0], 'filename_prefix': 'shorts_still'}
  }

  return workflow


def build_flux_workflow(
  prompt: str,
  lora_strength: float = FLUX_LORA_STRENGTH,
  steps: int = FLUX_STEPS,
  guidance: float = FLUX_GUIDANCE,
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
      'inputs': {'noise_seed': 42}
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


def build_still_image_workflow_with_controlnet(
  prompt: str,
  negative_prompt: str,
  pose_filename: str,
  lora_strength: float = LORA_STRENGTH,
  cfg_scale: float = STILL_IMAGE_CFG,
  controlnet_strength: float = CONTROLNET_STRENGTH,
) -> dict:
  """
  ControlNet OpenPose 기반 정지 이미지 생성 워크플로우.

  노드 구성:
  1~8, 20~22: 기존 기본 워크플로우 (SaveImage 노드8)
  30: LoadImage (포즈 스켈레톤)
  31: ControlNetLoader
  32: ControlNetApplyAdvanced → KSampler positive/negative 교체
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
        'strength_model': lora_strength,
        'strength_clip': lora_strength
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
    '30': {
      'class_type': 'LoadImage',
      'inputs': {'image': pose_filename}
    },
    '31': {
      'class_type': 'ControlNetLoader',
      'inputs': {'control_net_name': CONTROLNET_MODEL}
    },
    '32': {
      'class_type': 'ControlNetApplyAdvanced',
      'inputs': {
        'positive': ['3', 0],
        'negative': ['4', 0],
        'control_net': ['31', 0],
        'image': ['30', 0],
        'strength': controlnet_strength,
        'start_percent': 0.0,
        'end_percent': 0.8,
      }
    },
    '6': {
      'class_type': 'KSampler',
      'inputs': {
        'model': ['2', 0],
        'positive': ['32', 0],
        'negative': ['32', 1],
        'latent_image': ['5', 0],
        'seed': 42,
        'steps': STILL_IMAGE_STEPS,
        'cfg': cfg_scale,
        'sampler_name': 'euler_ancestral',
        'scheduler': 'karras',
        'denoise': 1.0
      }
    },
    '7': {
      'class_type': 'VAEDecode',
      'inputs': {'samples': ['6', 0], 'vae': ['1', 2]}
    },
    '20': {
      'class_type': 'UpscaleModelLoader',
      'inputs': {'model_name': UPSCALE_MODEL}
    },
    '21': {
      'class_type': 'ImageUpscaleWithModel',
      'inputs': {'upscale_model': ['20', 0], 'image': ['7', 0]}
    },
    '22': {
      'class_type': 'ImageScale',
      'inputs': {
        'image': ['21', 0],
        'upscale_method': 'lanczos',
        'width': 1080,
        'height': 1920,
        'crop': 'center'
      }
    },
    '8': {
      'class_type': 'SaveImage',
      'inputs': {'images': ['22', 0], 'filename_prefix': 'shorts_still'}
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


def run_comfyui_still_workflow(
  prompt: str,
  negative: str,
  output_name: str,
  lora_strength: float = LORA_STRENGTH,
  cfg_scale: float = STILL_IMAGE_CFG,
) -> str:
  """ComfyUI API를 호출하여 정지 이미지를 생성하고 결과 경로 반환"""
  workflow = build_still_image_workflow(prompt, negative, lora_strength=lora_strength, cfg_scale=cfg_scale)
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
  ref_image2: str | None = None,
  lora_strength: float = LORA_STRENGTH,
  cfg_scale: float = STILL_IMAGE_CFG,
) -> str:
  """
  문장 단위 정지 이미지 생성 (IP-Adapter 옵션 + 테마별 LoRA/CFG 지원)

  반환: PNG 파일 경로
  """
  still_path = get_sentence_still_path(poem_dir, scene_idx, sent_idx)

  if use_cache and still_path.exists():
    logger.info(f'캐시된 정지 이미지 사용: {still_path}')
    return str(still_path)

  logger.info(f'Scene {scene_idx} Sent {sent_idx} 정지 이미지 생성 중... (lora={lora_strength}, cfg={cfg_scale})')

  prompt = image_prompt if image_prompt else 'ancient korean landscape, ink painting'

  if use_ipadapter and Path(REFERENCE_IMAGE_PATH).exists() and check_ipadapter_available():
    logger.info(f'Scene {scene_idx}: IP-Adapter 워크플로우 사용')
    workflow = build_still_image_workflow_with_ipadapter(
      prompt, negative_prompt, ref_image2,
      lora_strength=lora_strength, cfg_scale=cfg_scale
    )
    prompt_id = submit_prompt_to_comfyui(workflow)
  else:
    if use_ipadapter:
      logger.info(f'Scene {scene_idx}: 기본 워크플로우로 폴백 (IP-Adapter 미사용)')
    workflow = build_still_image_workflow(
      prompt, negative_prompt,
      lora_strength=lora_strength, cfg_scale=cfg_scale
    )
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
  Step 4: 모든 문장별 정지 이미지 생성 (테마별 LoRA/CFG/색감 적용)

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

  theme_lora = theme_params.get('lora', LORA_STRENGTH)
  theme_cfg = theme_params.get('cfg', STILL_IMAGE_CFG)
  theme_color = theme_params.get('color', '')
  theme_neg_extra = theme_params.get('neg_extra', '')
  logger.info(f'테마={theme_code}: lora={theme_lora}, cfg={theme_cfg}, color={theme_color!r}')

  # 생성 모드 결정 (Flux > ControlNet > 기본 순서)
  if USE_FLUX:
    logger.info('모드: Flux.1-dev FP8 (USE_FLUX=true)')
    use_controlnet = False
  else:
    use_controlnet = USE_CONTROLNET and check_controlnet_available()
    logger.info('모드: SD 1.5 + ControlNet=%s', '활성화' if use_controlnet else '비활성화')

  schedules = schedule_data.get('sentence_schedules', [])
  still_paths = []

  logger.info(f'이미지 생성 시작: 총 {len(schedules)}개 문장')

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

    # 테마 네거티브 키워드 추가 (Flux는 사용 안 함)
    base_neg = sched.get('negative_prompt', '')
    neg_prompt = f'{base_neg}, {theme_neg_extra}' if theme_neg_extra else base_neg

    logger.info(f'  - [{i+1}/{len(schedules)}] ComfyUI 호출 중: {out_name}')

    try:
      if USE_FLUX:
        # Flux는 네거티브 프롬프트 미지원 → 포지티브에 전통 의상/소품 키워드 강제 추가
        FLUX_STYLE_SUFFIX = (
          'traditional korean hanbok, joseon dynasty clothing, '
          'traditional korean accessories, korean traditional hair ornaments, '
          'gat hat, binyeo hairpin, traditional korean shoes, '
          'traditional east asian robes, ink wash painting style, guofeng, '
          'no modern clothing, no coat, no jacket, no western shoes, no sneakers'
        )
        flux_prompt = f'{prompt_text}, {FLUX_STYLE_SUFFIX}'
        # Flux.1-dev FP8 워크플로우 (네거티브 프롬프트 없음)
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
        logger.info(f'    ✓ 생성 완료 (Flux): {out_name}')
        continue

      if use_controlnet:
        # ControlNet OpenPose 워크플로우
        pose_type = sched.get('pose_type', 'standing_single')
        pose_path = create_pose_skeleton(pose_type)
        pose_filename = upload_pose_to_comfyui(pose_path)
        logger.info(f'    pose_type={pose_type}')

        workflow = build_still_image_workflow_with_controlnet(
          prompt_text, neg_prompt, pose_filename,
          lora_strength=theme_lora, cfg_scale=theme_cfg,
          controlnet_strength=CONTROLNET_STRENGTH,
        )
        prompt_id = submit_prompt_to_comfyui(workflow)
        if not poll_until_done(prompt_id):
          raise RuntimeError(f'Scene {scene_idx} ControlNet 타임아웃')
        output_png = download_generated_still(prompt_id)
        if not output_png:
          raise RuntimeError(f'Scene {scene_idx} ControlNet 이미지 없음')
        out_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(output_png), str(out_path))
        still_paths.append(str(out_path))
        logger.info(f'    ✓ 생성 완료 (ControlNet): {out_name}')
        continue

      # 기본 SD 1.5 워크플로우
      result_file = run_comfyui_still_workflow(
        prompt=prompt_text,
        negative=neg_prompt,
        output_name=out_name,
        lora_strength=theme_lora,
        cfg_scale=theme_cfg,
      )

      if result_file and os.path.exists(result_file):
        out_path.parent.mkdir(parents=True, exist_ok=True)
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
    logger.error(f'\n✗ Step 4 실패: {e}', exc_info=True)
    exit(1)
