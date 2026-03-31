#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""전체 파이프라인 통합 테스트 (Step 0~5)"""

import json
import logging
from pathlib import Path

# 로깅 설정 (UTF-8)
logging.basicConfig(
  level=logging.INFO,
  format='%(asctime)s - %(levelname)s - %(message)s',
  handlers=[
    logging.FileHandler('test_full_pipeline.log', encoding='utf-8'),
    logging.StreamHandler()
  ]
)
logger = logging.getLogger(__name__)

def main():
  logger.info('=' * 70)
  logger.info('전체 파이프라인 테스트: Step 0~5')
  logger.info('=' * 70)

  # Step 1 NLP 로드 (이미 실행됨)
  nlp_paths = sorted(Path('cache/step1').glob('*_nlp.json'))
  if not nlp_paths:
    logger.error('Step 1 캐시 없음')
    return False

  nlp_path = nlp_paths[-1]
  with open(nlp_path, 'r', encoding='utf-8') as f:
    nlp_data = json.load(f)
  logger.info(f'\n[Step 1] NLP: {nlp_path.name}')
  logger.info(f'  씬: {len(nlp_data["modern_script_data"])}개')

  # Step 2: TTS + alignment
  logger.info('\n[Step 2] ElevenLabs TTS 실행 중...')
  from step2_tts import generate_all_audio
  script_data = nlp_data['modern_script_data']
  audio_paths, alignment_paths = generate_all_audio(script_data, use_cache=False)
  logger.info(f'  오디오: {len(audio_paths)}개')
  logger.info(f'  Alignment: {len(alignment_paths)}개')

  if not audio_paths or len(audio_paths) != len(script_data):
    logger.error(f'Step 2 실패: {len(audio_paths)}개만 생성됨')
    return False

  # Step 3: 프레임 스케줄
  logger.info('\n[Step 3] 프레임 스케줄 생성 중...')
  from step3_scheduler import build_frame_schedules
  schedule_path = build_frame_schedules(script_data, alignment_paths, use_cache=False)
  logger.info(f'  스케줄: {Path(schedule_path).name}')

  # Step 4: 클립 생성
  logger.info('\n[Step 4] AnimateDiff 클립 생성 중...')
  from step4_clip import generate_all_clips
  clip_paths, still_paths = generate_all_clips(schedule_path, use_cache=True)
  logger.info(f'  정지 이미지: {len(still_paths)}개')
  logger.info(f'  클립: {len(clip_paths)}개')

  if len(clip_paths) != len(script_data):
    logger.error(f'Step 4 실패: {len(clip_paths)}개만 생성됨')
    return False

  # Step 5: 최종 병합
  logger.info('\n[Step 5] 최종 영상 합성 중...')
  from step5_video import compose_final_video
  output_path = compose_final_video(
    clip_paths,
    audio_paths,
    alignment_paths,
    use_cache=True
  )

  if Path(output_path).exists():
    size_mb = Path(output_path).stat().st_size / (1024 * 1024)
    logger.info(f'  완료: {Path(output_path).name}')
    logger.info(f'  파일 크기: {size_mb:.1f}MB')

    logger.info('\n' + '=' * 70)
    logger.info('✓ 파이프라인 완료!')
    logger.info('=' * 70)
    return True
  else:
    logger.error(f'Step 5 실패: {output_path} 없음')
    return False

if __name__ == '__main__':
  success = main()
  exit(0 if success else 1)
