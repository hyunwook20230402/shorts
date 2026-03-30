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
COMFYUI_MAX_WAIT = int(os.getenv('COMFYUI_MAX_WAIT', '1200'))  # 초 단위

MAX_RETRIES = 3


def get_cache_path(schedule_hash: str, scene_index: int) -> Path:
  """캐시 경로 생성"""
  CACHE_DIR.mkdir(parents=True, exist_ok=True)
  return CACHE_DIR / f'{schedule_hash}_{scene_index:02d}_clip.mp4'


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


def generate_clip(
  scene_schedule: dict,
  scene_index: int,
  schedule_hash: str,
  use_cache: bool = True
) -> str:
  """
  씬별 영상 클립 생성
  반환: 클립 파일 경로
  """
  clip_path = get_cache_path(schedule_hash, scene_index)

  # 캐시 확인
  if use_cache and clip_path.exists():
    logger.info(f'캐시된 클립 사용: {clip_path}')
    return str(clip_path)

  logger.info(f'Scene {scene_index} 클립 생성 중...')

  total_frames = scene_schedule.get('total_frames', 0)
  prompt_schedule = scene_schedule.get('prompt_schedule', {})
  negative_prompt = scene_schedule.get('negative_prompt', '')

  # 프롬프트 선택 (첫 번째 프레임의 프롬프트 사용)
  prompt = prompt_schedule.get('0', 'ancient korean landscape, ink painting')

  # 워크플로우 빌드
  workflow = build_animatediff_workflow(
    prompt,
    negative_prompt,
    total_frames,
    prompt_schedule
  )

  # ComfyUI 제출
  prompt_id = submit_prompt_to_comfyui(workflow)

  # 완료 대기
  if not poll_until_done(prompt_id):
    raise RuntimeError(f'Scene {scene_index} 클립 생성 타임아웃')

  # 생성된 파일 다운로드
  output_video = download_generated_video(f'shorts_clip')
  if not output_video:
    raise RuntimeError(f'Scene {scene_index} 클립 파일을 찾을 수 없음')

  # 캐시 디렉토리로 이동
  clip_path.parent.mkdir(parents=True, exist_ok=True)
  output_video.rename(clip_path)
  logger.info(f'클립 캐시 저장: {clip_path}')

  return str(clip_path)


def generate_all_clips(
  frame_schedule_path: str,
  use_cache: bool = True
) -> list[str]:
  """
  전체 씬의 영상 클립 생성
  반환: 클립 파일 경로 목록
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

  for scene_schedule in scene_schedules:
    scene_index = scene_schedule.get('scene_index', 0)
    try:
      clip_path = generate_clip(
        scene_schedule,
        scene_index,
        schedule_hash,
        use_cache=use_cache
      )
      clip_paths.append(clip_path)
    except Exception as e:
      logger.error(f'Scene {scene_index} 클립 생성 실패: {e}')
      raise

  logger.info(f'전체 클립 생성 완료: {len(clip_paths)}개 씬')
  return clip_paths


if __name__ == '__main__':
  logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
  )

  if cmd_check():
    print('ComfyUI 환경 준비 완료')
  else:
    print('ComfyUI 연결 실패')
