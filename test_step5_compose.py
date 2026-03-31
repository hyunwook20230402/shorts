#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Step 5 최종 영상 합성 테스트"""

import os
import json
import logging
from pathlib import Path

# 로깅 설정 (UTF-8)
logging.basicConfig(
  level=logging.INFO,
  format='%(asctime)s - %(levelname)s - %(message)s',
  handlers=[
    logging.FileHandler('test_step5.log', encoding='utf-8'),
    logging.StreamHandler()
  ]
)
logger = logging.getLogger(__name__)

from step5_video import compose_final_video

def find_files_by_hash(directory, pattern):
  """해시별로 파일 그룹화"""
  by_hash = {}
  for file_path in Path(directory).glob(pattern):
    parts = file_path.stem.split('_')
    file_hash = parts[0]
    if len(parts) >= 2 and parts[1].isdigit():
      scene_idx = int(parts[1])
      if file_hash not in by_hash:
        by_hash[file_hash] = []
      by_hash[file_hash].append((scene_idx, str(file_path)))
  return by_hash

def main():
  logger.info('=' * 60)
  logger.info('Step 5 테스트: 최종 영상 합성')
  logger.info('=' * 60)

  # Step 4 클립
  clips_by_hash = find_files_by_hash('cache/step4', '*_clip.mp4')
  if not clips_by_hash:
    logger.error('Step 4 클립 없음')
    return False

  latest_clip_hash = max(clips_by_hash.keys())
  clip_paths = sorted(clips_by_hash[latest_clip_hash], key=lambda x: x[0])
  clip_paths = [p[1] for p in clip_paths]
  logger.info(f'클립: {len(clip_paths)}개 (해시: {latest_clip_hash})')

  # Step 2 오디오
  audio_by_hash = find_files_by_hash('cache/step2', '*_audio.mp3')
  if not audio_by_hash:
    logger.error('Step 2 오디오 없음')
    return False

  latest_audio_hash = max(audio_by_hash.keys())
  audio_paths = sorted(audio_by_hash[latest_audio_hash], key=lambda x: x[0])
  audio_paths = [p[1] for p in audio_paths]
  logger.info(f'오디오: {len(audio_paths)}개 (해시: {latest_audio_hash})')

  # Step 2 alignment
  align_by_hash = find_files_by_hash('cache/step2', '*_alignment.json')
  alignment_paths = sorted(align_by_hash[latest_audio_hash], key=lambda x: x[0])
  alignment_paths = [p[1] for p in alignment_paths]
  logger.info(f'Alignment: {len(alignment_paths)}개')

  # 씬 수 일치 확인
  if not (len(clip_paths) == len(audio_paths) == len(alignment_paths)):
    logger.error(f'씬 개수 불일치: clips={len(clip_paths)}, audio={len(audio_paths)}, align={len(alignment_paths)}')
    return False

  # Step 1 NLP 데이터
  nlp_paths = sorted(Path('cache/step1').glob('*_nlp.json'))
  if not nlp_paths:
    logger.error('Step 1 NLP 데이터 없음')
    return False

  nlp_path = nlp_paths[-1]
  with open(nlp_path, 'r', encoding='utf-8') as f:
    nlp_data = json.load(f)
  logger.info(f'NLP: {nlp_path.name} ({len(nlp_data.get("scenes", []))}개 씬)')

  # Step 5 실행
  logger.info('\n최종 영상 합성 시작...')
  try:
    output_path = compose_final_video(
      clip_paths,
      audio_paths,
      alignment_paths,
      nlp_data,
      use_cache=True
    )

    if Path(output_path).exists():
      size_mb = Path(output_path).stat().st_size / (1024 * 1024)
      logger.info(f'✓ 완료: {output_path}')
      logger.info(f'  파일 크기: {size_mb:.1f}MB')
      return True
    else:
      logger.error(f'출력 파일 없음: {output_path}')
      return False

  except Exception as e:
    logger.error(f'오류: {e}', exc_info=True)
    return False

if __name__ == '__main__':
  success = main()
  exit(0 if success else 1)
