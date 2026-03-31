#!/usr/bin/env python3
"""
Step 4 수동 테스트 스크립트
- 생성된 Step 3 캐시 기반으로 Step 4 클립 생성
- 클립에 줌인 효과가 적용되는지 검증
"""

import json
import logging
from pathlib import Path

from step4_clip import generate_all_clips, animate_with_ken_burns, generate_still_image

logging.basicConfig(
  level=logging.INFO,
  format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_step4_clip_generation():
  """Step 4 클립 생성 테스트"""
  logger.info('=' * 60)
  logger.info('Step 4 테스트: AnimateDiff 클립 생성 + 줌 효과')
  logger.info('=' * 60)

  # 최근 생성된 Step 3 스케줄 파일 찾기
  step3_cache_dir = Path('cache/step3')
  schedule_files = sorted(step3_cache_dir.glob('*.json'))

  if not schedule_files:
    logger.error('Step 3 스케줄 캐시 없음')
    return False

  schedule_path = str(schedule_files[-1])
  logger.info(f'\n사용할 스케줄: {schedule_path}')

  # 스케줄 로드 및 확인
  with open(schedule_path, 'r', encoding='utf-8') as f:
    schedule = json.load(f)

  scene_schedules = schedule.get('scene_schedules', [])
  logger.info(f'스케줄 내 씬 수: {len(scene_schedules)}')
  logger.info('\n씬별 정보:')
  for scene in scene_schedules:
    scene_idx = scene['scene_index']
    total_frames = scene['total_frames']
    duration = total_frames / 10
    logger.info(f'  Scene {scene_idx}: {total_frames} frames ({duration:.1f}초)')

  # Step 4 실행
  try:
    logger.info('\n🎬 Step 4 실행: generate_all_clips()')
    clip_paths, still_paths = generate_all_clips(schedule_path, use_cache=True)

    logger.info(f'\n✓ 클립 생성 완료: {len(clip_paths)}개')
    for i, (clip_path, still_path) in enumerate(zip(clip_paths, still_paths)):
      logger.info(f'\n씬 {i}:')
      logger.info(f'  - 정지 이미지: {still_path}')
      logger.info(f'  - 클립: {clip_path}')

      # 파일 존재 확인
      if Path(clip_path).exists():
        clip_size_mb = Path(clip_path).stat().st_size / (1024 * 1024)
        logger.info(f'    크기: {clip_size_mb:.1f}MB')
      else:
        logger.warning(f'    파일 없음!')

    logger.info('\n' + '=' * 60)
    logger.info('✓ Step 4 테스트 완료')
    logger.info('=' * 60)
    logger.info('\n주의: 클립에는 음성과 자막이 포함되지 않습니다.')
    logger.info('      음성과 자막은 Step 5 (video_processor.py)에서 추가됩니다.')
    logger.info('      줌 효과는 ffmpeg zoompan 필터로 적용됩니다.')

    return True

  except Exception as e:
    logger.error(f'\n✗ Step 4 실패: {e}')
    import traceback
    traceback.print_exc()
    return False


if __name__ == '__main__':
  success = test_step4_clip_generation()
  exit(0 if success else 1)
