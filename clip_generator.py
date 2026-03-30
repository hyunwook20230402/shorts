"""
Step 4: ComfyUI AnimateDiff (SD 1.5 + LoRA)로 씬별 영상 클립 생성
"""

import os
import json
import logging
import hashlib
import math
import time
import base64
import subprocess
import shutil
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
import requests
import websocket

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
KEN_BURNS_MODE = os.getenv('KEN_BURNS_MODE', 'true').lower() == 'true'
I2V_DURATION = float(os.getenv('I2V_DURATION', '3.0'))

MAX_RETRIES = 3


def get_cache_path(schedule_hash: str, scene_index: int) -> Path:
  """Step 4-B 클립 캐시 경로 생성"""
  CACHE_DIR.mkdir(parents=True, exist_ok=True)
  return CACHE_DIR / f'{schedule_hash}_{scene_index:02d}_clip.mp4'


def get_still_cache_path(schedule_hash: str, scene_index: int) -> Path:
  """Step 4-A 정지 이미지 캐시 경로 생성"""
  CACHE_DIR.mkdir(parents=True, exist_ok=True)
  return CACHE_DIR / f'{schedule_hash}_{scene_index:02d}_still.png'


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


def build_still_image_workflow(prompt: str, negative_prompt: str) -> dict:
  """
  Step 4-A: 고품질 정지 이미지 생성 워크플로우
  batch_size=1, steps=30, cfg=7.5
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
    images = outputs.get('8', {}).get('images', [])  # 노드 '8' = SaveImage

    if not images:
      logger.error('SaveImage 노드 출력 없음')
      return None

    filename = images[0]['filename']
    png_path = COMFYUI_OUTPUT_DIR / filename

    if not png_path.exists():
      logger.error(f'PNG 파일 없음: {png_path}')
      return None

    logger.info(f'정지 이미지 발견: {png_path}')
    return png_path

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
  scene_schedule: dict,
  scene_index: int,
  schedule_hash: str,
  use_cache: bool = True
) -> str:
  """
  Step 4-A: ComfyUI로 정지 이미지 생성
  반환: PNG 파일 경로
  """
  still_path = get_still_cache_path(schedule_hash, scene_index)

  if use_cache and still_path.exists():
    logger.info(f'캐시된 정지 이미지 사용: {still_path}')
    return str(still_path)

  logger.info(f'Scene {scene_index} 정지 이미지 생성 중...')

  prompt_schedule = scene_schedule.get('prompt_schedule', {})
  negative_prompt = scene_schedule.get('negative_prompt', '')
  prompt = prompt_schedule.get('0', 'ancient korean landscape, ink painting')

  workflow = build_still_image_workflow(prompt, negative_prompt)
  prompt_id = submit_prompt_to_comfyui(workflow)

  if not poll_until_done(prompt_id):
    raise RuntimeError(f'Scene {scene_index} 정지 이미지 타임아웃')

  output_png = download_generated_still(prompt_id)
  if not output_png:
    raise RuntimeError(f'Scene {scene_index} 정지 이미지 파일 없음')

  still_path.parent.mkdir(parents=True, exist_ok=True)
  shutil.copy2(str(output_png), str(still_path))
  logger.info(f'정지 이미지 캐시 저장: {still_path}')

  return str(still_path)


def animate_with_ken_burns(
  still_path: str,
  scene_index: int,
  schedule_hash: str,
  duration: float = I2V_DURATION,
  use_cache: bool = True
) -> str:
  """
  Step 4-B: ffmpeg zoompan 필터로 Ken Burns 효과 클립 생성
  반환: MP4 파일 경로
  """
  clip_path = get_cache_path(schedule_hash, scene_index)

  if use_cache and clip_path.exists():
    logger.info(f'캐시된 클립 사용: {clip_path}')
    return str(clip_path)

  logger.info(f'Scene {scene_index} Ken Burns 클립 생성 중...')

  fps = ANIMATEDIFF_FPS
  total_frames = int(duration * fps)

  # 씬 인덱스를 홀짝으로 나눠 줌인/줌아웃 교번 적용
  if scene_index % 2 == 0:
    zoom_expr = "'if(lte(zoom,1.0),1.5,max(1.001,zoom-0.0015))'"
  else:
    zoom_expr = "'if(gte(zoom,1.5),1.0,min(1.499,zoom+0.0015))'"

  still_path_fwd = str(still_path).replace('\\', '/')
  clip_path_fwd = str(clip_path).replace('\\', '/')

  cmd = [
    'ffmpeg',
    '-loop', '1',
    '-i', still_path_fwd,
    '-vf', (
      f'zoompan='
      f'z={zoom_expr}:'
      f'd={total_frames}:'
      f"x='iw/2-(iw/zoom/2)':"
      f"y='ih/2-(ih/zoom/2)':"
      f's=512x912'
    ),
    '-t', str(duration),
    '-r', str(fps),
    '-c:v', 'libx264',
    '-crf', '23',
    '-preset', 'fast',
    '-y',
    clip_path_fwd
  ]

  logger.info(f'ffmpeg Ken Burns: {" ".join(cmd)}')
  clip_path.parent.mkdir(parents=True, exist_ok=True)
  result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

  if result.returncode == 0:
    logger.info(f'Ken Burns 클립 생성 완료: {clip_path}')
    return str(clip_path)
  else:
    logger.error(f'ffmpeg 오류: {result.stderr}')
    raise RuntimeError(f'Scene {scene_index} Ken Burns 변환 실패: {result.stderr[:200]}')


def _generate_clip_t2v(
  scene_schedule: dict,
  scene_index: int,
  schedule_hash: str,
  use_cache: bool = True
) -> str:
  """
  레거시 T2V 모드: AnimateDiff로 직접 클립 생성 (KEN_BURNS_MODE=false)
  반환: 클립 파일 경로
  """
  clip_path = get_cache_path(schedule_hash, scene_index)

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

  output_video = download_generated_video(f'shorts_clip')
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
  씬별 영상 클립 생성 (I2V 또는 T2V 모드)
  반환: 클립 파일 경로
  """
  if KEN_BURNS_MODE:
    still_path = generate_still_image(scene_schedule, scene_index, schedule_hash, use_cache)
    return animate_with_ken_burns(still_path, scene_index, schedule_hash, I2V_DURATION, use_cache)
  else:
    return _generate_clip_t2v(scene_schedule, scene_index, schedule_hash, use_cache)


def generate_all_clips(
  frame_schedule_path: str,
  use_cache: bool = True
) -> tuple[list[str], list[str]]:
  """
  전체 씬의 영상 클립 생성 (I2V 또는 T2V 모드)
  반환: (clip_paths, still_image_paths)
  """
  # 스케줄 JSON 로드
  try:
    with open(frame_schedule_path, 'r', encoding='utf-8') as f:
      schedule_data = json.load(f)
  except Exception as e:
    logger.error(f'스케줄 로드 실패: {frame_schedule_path}, {e}')
    raise

  scene_schedules = schedule_data.get('scene_schedules', [])
  schedule_hash = hashlib.md5(
    json.dumps(schedule_data, sort_keys=True, ensure_ascii=False).encode()
  ).hexdigest()[:8]

  clip_paths = []
  still_paths = []

  for scene_schedule in scene_schedules:
    scene_index = scene_schedule.get('scene_index', 0)
    try:
      if KEN_BURNS_MODE:
        # Step 4-A: 정지 이미지 생성
        still_path = generate_still_image(scene_schedule, scene_index, schedule_hash, use_cache)
        still_paths.append(still_path)
        # Step 4-B: Ken Burns 클립 생성
        clip_path = animate_with_ken_burns(still_path, scene_index, schedule_hash, I2V_DURATION, use_cache)
      else:
        # 레거시 T2V 모드
        clip_path = _generate_clip_t2v(scene_schedule, scene_index, schedule_hash, use_cache)
      clip_paths.append(clip_path)
    except Exception as e:
      logger.error(f'Scene {scene_index} 클립 생성 실패: {e}')
      raise

  logger.info(f'전체 클립 생성 완료: {len(clip_paths)}개 씬 (I2V: {KEN_BURNS_MODE})')
  return clip_paths, still_paths


if __name__ == '__main__':
  logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
  )

  if cmd_check():
    print('ComfyUI 환경 준비 완료')
  else:
    print('ComfyUI 연결 실패')
