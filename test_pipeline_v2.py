#!/usr/bin/env python3
"""
PRD v2 파이프라인 전체 테스트 (Step 0~5)
- Step 0: OCR (캐시에서 로드)
- Step 1: NLP (캐시에서 로드)
- Step 2: ElevenLabs TTS + alignment
- Step 3: 동적 프레임 스케줄링
- Step 4: AnimateDiff 클립 생성
- Step 5: 최종 병합
"""

import os
import sys
import json
import logging
from pathlib import Path
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

# 로깅 설정
logging.basicConfig(
  level=logging.INFO,
  format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 단계별 임포트
try:
  from audio_generator import generate_all_audio, cmd_check as check_elevenlabs
  from dynamic_scheduler import build_frame_schedules
  from clip_generator import generate_all_clips, cmd_check as check_comfyui
  from video_processor import compose_final_video
except ImportError as e:
  logger.error(f'임포트 실패: {e}')
  sys.exit(1)

def load_step1_cache() -> list:
  """Step 1 캐시에서 NLP 결과 로드"""
  cache_dir = Path('cache/step1')
  nlp_files = list(cache_dir.glob('*_nlp.json'))

  if not nlp_files:
    logger.error('Step 1 캐시를 찾을 수 없습니다')
    return None

  nlp_file = nlp_files[0]  # 가장 최근 파일
  logger.info(f'Step 1 캐시 로드: {nlp_file}')

  with open(nlp_file, 'r', encoding='utf-8') as f:
    data = json.load(f)
    return data.get('modern_script_data', [])

def main():
  logger.info('=== PRD v2 파이프라인 테스트 시작 ===')

  # 1. Step 0~1 캐시 로드
  logger.info('\n[Step 0~1] OCR + NLP 캐시 로드')
  nlp_data = load_step1_cache()
  if not nlp_data:
    logger.error('Step 1 캐시 로드 실패')
    return False

  logger.info(f'✓ {len(nlp_data)}개 씬 로드 완료')
  script_data = nlp_data

  # 2. Step 2: ElevenLabs TTS + alignment
  logger.info('\n[Step 2] ElevenLabs TTS + alignment 생성')
  if not check_elevenlabs():
    logger.error('ElevenLabs API 연결 실패')
    return False

  try:
    audio_paths, alignment_paths = generate_all_audio(script_data, use_cache=True)
    logger.info(f'✓ {len(audio_paths)}개 오디오 생성 완료')
    logger.info(f'  - audio_paths: {audio_paths[:2]}...')
    logger.info(f'  - alignment_paths: {alignment_paths[:2]}...')
  except Exception as e:
    logger.error(f'Step 2 실패: {e}')
    return False

  # 3. Step 3: 동적 프레임 스케줄링
  logger.info('\n[Step 3] 동적 프레임 스케줄 생성')
  try:
    frame_schedule_path = build_frame_schedules(script_data, alignment_paths, use_cache=True)
    logger.info(f'✓ 프레임 스케줄 생성 완료')
    logger.info(f'  - schedule_path: {frame_schedule_path}')

    # 스케줄 내용 확인
    with open(frame_schedule_path, 'r', encoding='utf-8') as f:
      schedule = json.load(f)
      logger.info(f'  - 총 {len(schedule["scene_schedules"])}개 씬 스케줄')
  except Exception as e:
    logger.error(f'Step 3 실패: {e}')
    return False

  # 4. Step 4: AnimateDiff 클립 생성
  logger.info('\n[Step 4] AnimateDiff 클립 생성')
  if not check_comfyui():
    logger.error('ComfyUI 연결 실패')
    return False

  try:
    video_clip_paths = generate_all_clips(frame_schedule_path, use_cache=True)
    logger.info(f'✓ {len(video_clip_paths)}개 클립 생성 완료')
    logger.info(f'  - clip_paths: {video_clip_paths[:2]}...')
  except Exception as e:
    logger.error(f'Step 4 실패: {e}')
    return False

  # 5. Step 5: 최종 병합 (클립 + 오디오 + 자막)
  logger.info('\n[Step 5] 최종 영상 병합')
  try:
    final_video_path = compose_final_video(
      video_clip_paths,
      audio_paths,
      alignment_paths
    )
    logger.info(f'✓ 최종 영상 생성 완료')
    logger.info(f'  - output: {final_video_path}')

    # 파일 크기 확인
    if Path(final_video_path).exists():
      file_size = Path(final_video_path).stat().st_size / (1024 * 1024)
      logger.info(f'  - 파일 크기: {file_size:.2f} MB')
  except Exception as e:
    logger.error(f'Step 5 실패: {e}')
    return False

  logger.info('\n=== ✓ 파이프라인 테스트 완료 ===')
  return True

if __name__ == '__main__':
  success = main()
  sys.exit(0 if success else 1)
