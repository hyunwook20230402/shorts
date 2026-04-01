"""
Step 4: ComfyUI AnimateDiff (SD 1.5 + LoRA)로 씬별 영상 클립 생성
"""

import json
import logging
import os
import shutil
import subprocess
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
ANIMATEDIFF_MOTION_MODULE = os.getenv('ANIMATEDIFF_MOTION_MODULE', 'mm_sd_v15_v2.ckpt')
LORA_NAME = os.getenv('LORA_NAME', 'E38090E59BBDE9A38EE68F92E794BBE38091E58FAFE7.G2A0.safetensors')
LORA_STRENGTH = float(os.getenv('LORA_STRENGTH', '0.8'))
ANIMATEDIFF_FPS = int(os.getenv('ANIMATEDIFF_FPS', '10'))
CHUNK_SIZE = int(os.getenv('ANIMATEDIFF_CHUNK_SIZE', '16'))  # VRAM 보호용 프레임 배치
CACHE_DIR = Path('cache/step4')
COMFYUI_OUTPUT_DIR = Path(os.getenv('COMFYUI_OUTPUT_DIR', 'ComfyUI/output'))
COMFYUI_INPUT_DIR = Path(os.getenv('COMFYUI_INPUT_DIR', 'ComfyUI/input'))
COMFYUI_MAX_WAIT = int(os.getenv('COMFYUI_MAX_WAIT', '1200'))  # 초 단위

# I2V 관련 환경변수
STILL_IMAGE_STEPS = int(os.getenv('STILL_IMAGE_STEPS', '30'))
STILL_IMAGE_CFG = float(os.getenv('STILL_IMAGE_CFG', '7.5'))
I2V_DURATION = float(os.getenv('I2V_DURATION', '3.0'))

# IP-Adapter 관련 환경변수
IPADAPTER_MODEL = os.getenv('IPADAPTER_MODEL', 'ip-adapter_sd15.bin')
IPADAPTER_WEIGHT = float(os.getenv('IPADAPTER_WEIGHT', '0.7'))
CLIP_VISION_MODEL = os.getenv('CLIP_VISION_MODEL', 'clip_vision_h14.safetensors')
REFERENCE_IMAGE_PATH = os.getenv('REFERENCE_IMAGE_PATH', 'cache/reference/character.png')
REFERENCE_IMAGE_PATH2 = os.getenv('REFERENCE_IMAGE_PATH2', '')  # 2번째 참고 이미지 (선택)

MAX_RETRIES = 3


def get_cache_path(poem_dir: Path, scene_index: int) -> Path:
  """Step 4-B 클립 캐시 경로 생성 (씬 단위, 레거시)"""
  return poem_dir / f'step4_scene{scene_index:02d}_clip.mp4'


def get_still_cache_path(poem_dir: Path, scene_index: int) -> Path:
  """Step 4-A 정지 이미지 캐시 경로 생성 (씬 단위, 레거시)"""
  return poem_dir / f'step4_scene{scene_index:02d}_still.png'


def get_sentence_still_path(poem_dir: Path, scene_idx: int, sent_idx: int) -> Path:
  """Step 4-A 정지 이미지 캐시 경로 생성 (문장 단위)"""
  return poem_dir / f'step4_scene{scene_idx:02d}_sent{sent_idx:02d}_still.png'


def get_sentence_clip_path(poem_dir: Path, scene_idx: int, sent_idx: int) -> Path:
  """Step 4-B 클립 캐시 경로 생성 (문장 단위)"""
  return poem_dir / f'step4_scene{scene_idx:02d}_sent{sent_idx:02d}_clip.mp4'


def cmd_check() -> bool:
  """ComfyUI + 모델 연결 확인"""
  try:
    # ComfyUI /system_stats 확인
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

  # 2번째 참고 이미지 (선택)
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
  Step 4-A: 고품질 정지 이미지 생성 워크플로우 (기본 파이프라인, 8노드)

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
  Step 4-A: IP-Adapter 기반 캐릭터 일관성 정지 이미지 생성

  1장 참고 이미지: 12노드
  2장 참고 이미지: 15노드 (두 번째 IPAdapterAdvanced 추가)

  노드 구성 (1장):
  1: CheckpointLoaderSimple
  2: LoraLoader
  3: CLIPTextEncode (positive)
  4: CLIPTextEncode (negative)
  5: EmptyLatentImage
  6: CLIPVisionLoader
  7: LoadImage (참고이미지 1)
  8: IPAdapterModelLoader
  9: IPAdapterAdvanced (image1)
  10: KSampler
  11: VAEDecode
  12: SaveImage

  2장일 경우 추가:
  13: LoadImage (참고이미지 2)
  14: IPAdapterAdvanced (image2, model=['9', 0]에 체인)
  (KSampler model 입력 = ['14', 0])
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

  # 2번째 참고 이미지가 있으면 IPAdapterAdvanced 노드 추가
  if ref_image2:
    workflow['13'] = {
      'class_type': 'LoadImage',
      'inputs': {'image': ref_image2}
    }
    workflow['14'] = {
      'class_type': 'IPAdapterAdvanced',
      'inputs': {
        'model': ['9', 0],  # ← 첫 번째 IPAdapter 출력에 체인
        'ipadapter': ['8', 0],
        'clip_vision': ['6', 0],
        'image': ['13', 0],  # ← 두 번째 참고 이미지
        'weight': IPADAPTER_WEIGHT,
        'weight_type': 'linear',
        'start_at': 0.0,
        'end_at': 1.0,
        'unfold_batch': False,
        'combine_embeds': 'concat',
        'embeds_scaling': 'V only'
      }
    }
    # KSampler의 model을 IPAdapterAdvanced(14)에 연결
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


def build_animatediff_workflow(
  prompt: str,
  negative_prompt: str,
  total_frames: int,
  prompt_schedule: dict,
  chunk_start: int = 0
) -> dict:
  """
  AnimateDiff SD 1.5 + LoRA 워크플로우 JSON 빌드

  노드 구성:
  1: CheckpointLoaderSimple
  2: LoraLoader (국풍 LoRA)
  3: CLIPTextEncode (positive)
  4: CLIPTextEncode (negative)
  5: ADE_EmptyLatentImageLarge
  6: KSampler
  7: VAEDecode
  8: VHS_VideoCombine (또는 SaveImage)
  """
  chunk_size = min(CHUNK_SIZE, total_frames)

  workflow = {
    '1': {
      'class_type': 'CheckpointLoaderSimple',
      'inputs': {
        'ckpt_name': SD15_CHECKPOINT
      }
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
      'inputs': {
        'clip': ['2', 1],
        'text': prompt
      }
    },
    '4': {
      'class_type': 'CLIPTextEncode',
      'inputs': {
        'clip': ['2', 1],
        'text': negative_prompt
      }
    },
    '5': {
      'class_type': 'EmptyLatentImage',
      'inputs': {
        'width': 512,
        'height': 912,
        'batch_size': chunk_size
      }
    },
    '6': {
      'class_type': 'KSampler',
      'inputs': {
        'model': ['2', 0],
        'positive': ['3', 0],
        'negative': ['4', 0],
        'latent_image': ['5', 0],
        'seed': 42,
        'steps': 20,
        'cfg': 7.0,
        'sampler_name': 'euler_ancestral',
        'scheduler': 'karras',
        'denoise': 1.0
      }
    },
    '7': {
      'class_type': 'VAEDecode',
      'inputs': {
        'samples': ['6', 0],
        'vae': ['1', 2]
      }
    },
    '8': {
      'class_type': 'SaveImage',
      'inputs': {
        'images': ['7', 0],
        'filename_prefix': 'shorts_clip'
      }
    }
  }

  return workflow


def submit_prompt_to_comfyui(workflow: dict) -> str:
  """
  ComfyUI에 워크플로우 제출
  반환: prompt_id
  """
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
  """
  ComfyUI 작업 완료 대기
  반환: True (성공), False (실패/타임아웃)
  """
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


def generate_reference_image(scene_schedule: dict) -> str:
  """
  첫 씬 기반으로 참조 캐릭터 이미지 생성 (IP-Adapter용)
  기본 워크플로우(8노드)로 생성 후 cache/reference/character.png 저장

  반환: 참조 이미지 경로 (ComfyUI input 폴더 기준)
  """
  # 씬의 첫 프롬프트 추출
  prompt_schedule = scene_schedule.get('prompt_schedule', {})
  if not prompt_schedule:
    logger.error('프롬프트 스케줄 없음')
    raise ValueError('참조 이미지 생성 실패: 프롬프트 없음')

  first_prompt = prompt_schedule.get('0', 'cute character illustration, soft watercolor')
  negative_prompt = scene_schedule.get('negative_prompt', '')

  logger.info(f'참조 이미지 생성: {first_prompt[:100]}...')

  # 기본 워크플로우로 생성 (IP-Adapter 미적용)
  workflow = build_still_image_workflow(first_prompt, negative_prompt)

  try:
    prompt_id = submit_prompt_to_comfyui(workflow)
    if not poll_until_done(prompt_id):
      raise RuntimeError('ComfyUI 작업 실패')

    png_path = download_generated_still(prompt_id)
    if not png_path:
      raise RuntimeError('PNG 다운로드 실패')

    # cache/reference/ 디렉토리 생성
    ref_dir = Path('cache/reference')
    ref_dir.mkdir(parents=True, exist_ok=True)

    # PNG를 reference/character.png로 복사
    ref_path = ref_dir / 'character.png'
    shutil.copy2(str(png_path), str(ref_path))
    logger.info(f'✓ 참조 이미지 저장: {ref_path}')

    return str(ref_path)

  except Exception as e:
    logger.error(f'참조 이미지 생성 실패: {e}')
    raise


def download_generated_still(prompt_id: str) -> Optional[Path]:
  """
  ComfyUI history API에서 생성된 정지 이미지 PNG 파일 추출
  반환: PNG 파일 경로
  """
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
    # (기본 워크플로우: 노드 '8', IP-Adapter 워크플로우: 노드 '12')
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


def download_generated_video(output_prefix: str) -> Optional[Path]:
  """
  ComfyUI output 디렉토리에서 생성된 PNG 프레임 수집 → ffmpeg로 MP4 변환
  반환: 생성된 MP4 파일 경로
  """
  try:
    # 최근 생성된 PNG 파일들 찾기 (output_prefix 기준)
    png_files = sorted(
      COMFYUI_OUTPUT_DIR.glob(f'{output_prefix}_*.png'),
      key=lambda p: p.stat().st_mtime,
      reverse=False  # 오름차순 (프레임 순서)
    )

    if not png_files:
      logger.error(f'{output_prefix}_*.png 파일을 찾을 수 없음')
      return None

    logger.info(f'수집된 PNG 프레임: {len(png_files)}개')

    # ffmpeg로 MP4 변환 (Windows 경로 처리)
    output_mp4 = COMFYUI_OUTPUT_DIR / f'{output_prefix}.mp4'
    # input_pattern은 forward slash 사용 (ffmpeg 호환성)
    # ComfyUI는 파일명 뒤에 밑줄을 추가함: shorts_clip_00001_.png
    input_pattern = str(COMFYUI_OUTPUT_DIR / f'{output_prefix}_%05d_.png').replace('\\', '/')

    cmd = [
      'ffmpeg',
      '-framerate', str(ANIMATEDIFF_FPS),
      '-i', input_pattern,
      '-c:v', 'libx264',
      '-crf', '23',
      '-preset', 'fast',
      '-y',  # 덮어쓰기
      str(output_mp4)
    ]

    logger.info(f'ffmpeg 실행: {" ".join(cmd)}')
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    if result.returncode == 0:
      logger.info(f'MP4 변환 완료: {output_mp4}')
      return output_mp4
    else:
      logger.error(f'ffmpeg 오류: {result.stderr}')
      return None

  except Exception as e:
    logger.error(f'비디오 변환 오류: {e}')
    return None


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
  Step 4-A: ComfyUI로 정지 이미지 생성 (문장 단위, IP-Adapter 옵션)

  Args:
    image_prompt: 이미지 생성 프롬프트 문자열 (scene_schedule dict 대신 직접 전달)
    negative_prompt: 부정 프롬프트
    scene_idx, sent_idx: 씬/문장 인덱스
    use_ipadapter: IP-Adapter 노드 사용 여부 (참조 이미지 필수)
    ref_image2: 두 번째 참고 이미지 파일명 (선택)

  반환: PNG 파일 경로
  """
  still_path = get_sentence_still_path(poem_dir, scene_idx, sent_idx)

  if use_cache and still_path.exists():
    logger.info(f'캐시된 정지 이미지 사용: {still_path}')
    return str(still_path)

  logger.info(f'Scene {scene_idx} Sent {sent_idx} 정지 이미지 생성 중...')

  prompt = image_prompt if image_prompt else 'ancient korean landscape, ink painting'

  # IP-Adapter 사용 여부 결정 (참조 이미지 + 노드 설치 여부)
  if use_ipadapter and Path(REFERENCE_IMAGE_PATH).exists() and check_ipadapter_available():
    logger.info(f'Scene {scene_idx}: IP-Adapter 워크플로우 사용' + (' (2장 참고 이미지)' if ref_image2 else ''))
    workflow = build_still_image_workflow_with_ipadapter(prompt, negative_prompt, ref_image2)
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


def _generate_clip_t2v(
  scene_schedule: dict,
  scene_index: int,
  poem_dir: Path,
  use_cache: bool = True
) -> str:
  """
  레거시 T2V 모드: AnimateDiff로 직접 클립 생성 (KEN_BURNS_MODE=false)
  반환: 클립 파일 경로
  """
  clip_path = get_cache_path(poem_dir, scene_index)

  if use_cache and clip_path.exists():
    logger.info(f'캐시된 클립 사용: {clip_path}')
    return str(clip_path)

  logger.info(f'Scene {scene_index} 클립 생성 중 (T2V 레거시 모드)...')

  total_frames = scene_schedule.get('total_frames', 0)
  prompt_schedule = scene_schedule.get('prompt_schedule', {})
  negative_prompt = scene_schedule.get('negative_prompt', '')
  prompt = prompt_schedule.get('0', 'ancient korean landscape, ink painting')

  workflow = build_animatediff_workflow(prompt, negative_prompt, total_frames, prompt_schedule)
  prompt_id = submit_prompt_to_comfyui(workflow)

  if not poll_until_done(prompt_id):
    raise RuntimeError(f'Scene {scene_index} 클립 생성 타임아웃')

  output_video = download_generated_video('shorts_clip')
  if not output_video:
    raise RuntimeError(f'Scene {scene_index} 클립 파일을 찾을 수 없음')

  clip_path.parent.mkdir(parents=True, exist_ok=True)
  shutil.copy2(str(output_video), str(clip_path))
  logger.info(f'클립 캐시 저장: {clip_path}')

  return str(clip_path)


def generate_clip(
  scene_schedule: dict,
  scene_index: int,
  schedule_hash: str,
  use_cache: bool = True
) -> str:
  """
  씬별 영상 클립 생성 (레거시 함수, 현재 미사용)
  반환: 클립 파일 경로
  """
  # Ken Burns 모드는 제거되었으므로 이 함수는 더이상 호출되지 않음
  return _generate_clip_t2v(scene_schedule, scene_index, schedule_hash, use_cache)


def _setup_ipadapter(sentence_schedules: list[dict]) -> tuple[bool, str | None]:
  """IP-Adapter 참조 이미지 초기화. 반환: (use_ipadapter, ref_image2)"""
  use_ipadapter = False
  ref_image2 = None

  if not check_ipadapter_available():
    return False, None

  if not Path(REFERENCE_IMAGE_PATH).exists():
    try:
      logger.info('참조 이미지 자동 생성 중...')
      # 씬 0의 첫 문장으로 자동 생성 (간단한 씬 데이터 구성)
      scene_ctx = {
        'emotion': sentence_schedules[0].get('emotion', 'serene') if sentence_schedules else 'serene',
        'background': sentence_schedules[0].get('background', 'korean landscape') if sentence_schedules else 'korean landscape',
        'image_prompt': sentence_schedules[0].get('image_prompt', '') if sentence_schedules else ''
      }
      generate_reference_image(scene_ctx)
      use_ipadapter = True
    except Exception as e:
      logger.warning(f'참조 이미지 생성 실패: {e} (기본 워크플로우 사용)')
      return False, None
  else:
    use_ipadapter = True

  # 참조 이미지를 ComfyUI input 폴더에 복사
  if use_ipadapter:
    try:
      ref_image1, ref_image2 = upload_reference_image_to_comfyui()
      logger.info(f'참조 이미지 업로드: {ref_image1}' + (f', {ref_image2}' if ref_image2 else ''))
    except Exception as e:
      logger.warning(f'참조 이미지 업로드 실패: {e}')
      return False, None

  return use_ipadapter, ref_image2


def generate_all_clips(
  sentence_schedule_path: str,
  poem_dir: Path,
  use_cache: bool = True
) -> list[str]:
  """
  문장 단위 정지 이미지 생성 (Step 4-A)

  입력: sentence_schedule_path (Step 3 문장 스케줄 JSON)
  출력: still_image_paths - 문장 순서대로 flat list

  IP-Adapter 캐릭터 일관성 처리:
  - 참조 이미지 자동 생성 (필요한 경우)
  - ComfyUI input 폴더에 복사
  - 각 정지이미지 생성 시 적용
  """
  # 스케줄 JSON 로드
  try:
    with open(sentence_schedule_path, 'r', encoding='utf-8') as f:
      schedule_data = json.load(f)
  except Exception as e:
    logger.error(f'문장 스케줄 로드 실패: {sentence_schedule_path}, {e}')
    raise

  sentence_schedules = schedule_data.get('sentence_schedules', [])
  logger.info(f'정지 이미지 생성: {len(sentence_schedules)}개 문장')

  # IP-Adapter 초기화
  use_ipadapter, ref_image2 = _setup_ipadapter(sentence_schedules)

  still_paths = []

  for entry in sentence_schedules:
    scene_idx = entry.get('scene_index', 0)
    sent_idx = entry.get('sent_index', 0)
    image_prompt = entry.get('image_prompt', '')
    negative_prompt = entry.get('negative_prompt', '')

    try:
      # Step 4-A: 정지 이미지 생성 (IP-Adapter 옵션)
      still_path = generate_still_image(
        image_prompt, negative_prompt, scene_idx, sent_idx, poem_dir,
        use_cache=use_cache, use_ipadapter=use_ipadapter, ref_image2=ref_image2
      )
      still_paths.append(still_path)

    except Exception as e:
      logger.error(f'Scene {scene_idx} Sent {sent_idx} 정지 이미지 생성 실패: {e}')
      raise

  logger.info(f'정지 이미지 생성 완료: {len(still_paths)}개 문장 (IP-Adapter: {use_ipadapter})')
  return still_paths


if __name__ == '__main__':
  import sys

  logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
      logging.FileHandler('step4_clip.log', encoding='utf-8'),
      logging.StreamHandler()
    ]
  )

  logger.info('=' * 70)
  logger.info('Step 4: ComfyUI 클립 생성 테스트')
  logger.info('=' * 70)

  # 파라미터 파싱
  if len(sys.argv) < 2:
    logger.error('✗ 사용법: python step4_clip.py <poem_dir>')
    exit(1)

  poem_dir = Path(sys.argv[1])

  # 1. ComfyUI 환경 확인
  if not cmd_check():
    logger.error('✗ ComfyUI 연결 실패')
    exit(1)

  # 2. Step 3 문장 스케줄 파일 로드
  schedule_path = poem_dir / 'step3_sentence_schedule.json'
  if not schedule_path.exists():
    logger.error(f'✗ Step 3 문장 스케줄 없음: {schedule_path}')
    exit(1)

  logger.info(f'사용할 스케줄: {schedule_path.name}')

  # 3. IP-Adapter 확인
  ipadapter_available = check_ipadapter_available()
  logger.info(f'IP-Adapter: {"✓ 설치됨" if ipadapter_available else "⚠ 미설치"}')

  # 4. Step 4 실행
  try:
    logger.info('\n정지 이미지 생성 실행 중...')
    still_paths = generate_all_clips(str(schedule_path), poem_dir, use_cache=True)

    logger.info(f'\n✓ 정지 이미지 생성 완료: {len(still_paths)}개')
    for i, still in enumerate(still_paths):
      logger.info(f'\nScene {i}:')
      logger.info(f'  Still: {Path(still).name}')
      if Path(still).exists():
        size_mb = Path(still).stat().st_size / (1024 * 1024)
        logger.info(f'  크기: {size_mb:.1f}MB')

    logger.info('\n' + '=' * 70)
    logger.info('✓ Step 4 테스트 완료')
    logger.info('=' * 70)
    exit(0)

  except Exception as e:
    logger.error(f'\n✗ Step 4 실패: {e}', exc_info=True)
    exit(1)
