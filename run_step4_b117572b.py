#!/usr/bin/env python3
"""
Step 4 실행 스크립트 (b117572b 스케줄)

사용법:
  python run_step4_b117572b.py
"""

import os
import sys
import logging
from pathlib import Path

# 환경 변수 확인 및 설정
os.environ['COMFYUI_HOST'] = os.environ.get('COMFYUI_HOST', 'http://127.0.0.1:8188')

from step4_clip import generate_all_clips, cmd_check, check_ipadapter_available

logging.basicConfig(
  level=logging.INFO,
  format='%(asctime)s - %(levelname)s - %(message)s',
  handlers=[
    logging.FileHandler('step4_run_b117572b.log', encoding='utf-8'),
    logging.StreamHandler()
  ]
)

logger = logging.getLogger(__name__)

def main():
  logger.info('=' * 70)
  logger.info('Step 4: ComfyUI 클립 생성 (b117572b 스케줄)')
  logger.info('=' * 70)

  # 1. ComfyUI 연결 확인
  if not cmd_check():
    logger.error('✗ ComfyUI 연결 실패')
    return False

  # 2. b117572b 스케줄 파일 확인
  schedule_path = 'cache/step3/b117572b_schedule.json'
  if not Path(schedule_path).exists():
    logger.error(f'✗ 스케줄 파일 없음: {schedule_path}')
    return False

  logger.info(f'스케줄: {schedule_path}')

  # 3. IP-Adapter 확인
  ipadapter_available = check_ipadapter_available()
  logger.info(f'IP-Adapter: {"✓ 설치됨" if ipadapter_available else "⚠ 미설치"}')

  # 4. Step 4 실행
  try:
    logger.info('\n클립 생성 실행 중...')
    clip_paths, still_paths = generate_all_clips(schedule_path, use_cache=True)

    logger.info(f'\n✓ 클립 생성 완료: {len(clip_paths)}개')
    for i, (clip, still) in enumerate(zip(clip_paths, still_paths)):
      logger.info(f'\nScene {i}:')
      logger.info(f'  Still: {Path(still).name}')
      logger.info(f'  Clip: {Path(clip).name}')
      if Path(clip).exists():
        size_mb = Path(clip).stat().st_size / (1024 * 1024)
        logger.info(f'  크기: {size_mb:.1f}MB')

    logger.info('\n' + '=' * 70)
    logger.info('✓ Step 4 클립 생성 완료')
    logger.info('=' * 70)
    return True

  except Exception as e:
    logger.error(f'\n✗ Step 4 실패: {e}', exc_info=True)
    return False

if __name__ == '__main__':
  success = main()
  sys.exit(0 if success else 1)
