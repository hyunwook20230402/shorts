#!/usr/bin/env python3
"""
Step 5 테스트: 최종 병합 (클립 + 오디오 + 자막)
"""

import json
import logging
from pathlib import Path

logging.basicConfig(
  level=logging.INFO,
  format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

try:
  from video_processor import compose_final_video
except ImportError as e:
  logger.error(f'임포트 실패: {e}')
  exit(1)

def main():
  logger.info('=== Step 5 최종 병합 테스트 ===\n')

  # Step 2 오디오 경로
  audio_paths = [
    'cache/step2/dc64e692_00_audio.mp3',
    'cache/step2/61e252b9_01_audio.mp3',
    'cache/step2/8d4da020_02_audio.mp3',
    'cache/step2/9052fb61_03_audio.mp3',
    'cache/step2/7103a0ec_04_audio.mp3',
    'cache/step2/1fea6706_05_audio.mp3',
    'cache/step2/db8d0e3e_06_audio.mp3',
  ]

  # Step 2 alignment 경로
  alignment_paths = [
    'cache/step2/dc64e692_00_alignment.json',
    'cache/step2/61e252b9_01_alignment.json',
    'cache/step2/8d4da020_02_alignment.json',
    'cache/step2/9052fb61_03_alignment.json',
    'cache/step2/7103a0ec_04_alignment.json',
    'cache/step2/1fea6706_05_alignment.json',
    'cache/step2/db8d0e3e_06_alignment.json',
  ]

  # Step 4 클립 경로 (더미)
  video_clip_paths = [
    'cache/step4/6803db9d_00_clip.mp4',
    'cache/step4/6803db9d_01_clip.mp4',
    'cache/step4/6803db9d_02_clip.mp4',
    'cache/step4/6803db9d_03_clip.mp4',
    'cache/step4/6803db9d_04_clip.mp4',
    'cache/step4/6803db9d_05_clip.mp4',
    'cache/step4/6803db9d_06_clip.mp4',
  ]

  # 파일 존재 확인
  logger.info('[검증] 파일 존재 확인')
  all_exist = True
  for path in audio_paths + alignment_paths + video_clip_paths:
    if not Path(path).exists():
      logger.error(f'  ✗ 없음: {path}')
      all_exist = False
    else:
      logger.info(f'  ✓ {path}')

  if not all_exist:
    logger.error('필수 파일이 없습니다')
    return False

  # Step 5 실행
  logger.info('\n[Step 5] 최종 병합 실행')
  try:
    final_video_path = compose_final_video(
      video_clip_paths,
      audio_paths,
      alignment_paths
    )
    logger.info(f'✓ 최종 영상 생성 완료')
    logger.info(f'  - output: {final_video_path}')

    if Path(final_video_path).exists():
      file_size = Path(final_video_path).stat().st_size / (1024 * 1024)
      logger.info(f'  - 파일 크기: {file_size:.2f} MB')
      return True
    else:
      logger.error(f'생성된 파일을 찾을 수 없음: {final_video_path}')
      return False

  except Exception as e:
    logger.error(f'Step 5 실패: {e}')
    import traceback
    traceback.print_exc()
    return False

if __name__ == '__main__':
  success = main()
  exit(0 if success else 1)
