"""
전체 파이프라인 E2E 테스트
Step 0~5 순서대로 실행하거나, 캐시를 활용하여 부분 실행
"""

import json
import logging
from pathlib import Path
import pytest

from step0_ocr import extract_text_from_image
from step1_nlp import process_nlp
from step2_tts import generate_all_audio
from step3_scheduler import build_frame_schedules
from step4_clip import generate_all_clips
from step5_video import compose_final_video

logger = logging.getLogger(__name__)


class TestFullPipeline:
  """전체 파이프라인 E2E 테스트"""

  @pytest.mark.slow
  @pytest.mark.gpu_required
  def test_full_pipeline_from_step2(self, nlp_cache_path):
    """
    Step 2~5 전체 실행 (Step 0, 1은 캐시 활용)
    ElevenLabs API + ComfyUI + MoviePy 필요
    """
    with open(nlp_cache_path, 'r', encoding='utf-8') as f:
      nlp_data = json.load(f)

    script_data = nlp_data.get('modern_script_data', [])

    if not script_data:
      pytest.skip('Step 1 스크립트 데이터 없음')

    try:
      # Step 2: Audio Generation
      logger.info('🎬 Step 2: ElevenLabs TTS + alignment 생성...')
      audio_paths, alignment_paths = generate_all_audio(script_data, use_cache=True)
      assert len(audio_paths) > 0
      logger.info(f'✓ Step 2 완료: {len(audio_paths)}개 오디오')

      # Step 3: Frame Scheduling
      logger.info('🎬 Step 3: 동적 프레임 스케줄 생성...')
      schedule_path = build_frame_schedules(
        script_data,
        alignment_paths,
        use_cache=True
      )
      assert Path(schedule_path).exists()
      logger.info(f'✓ Step 3 완료: {schedule_path}')

      # Step 4: Clip Generation
      logger.info('🎬 Step 4: ComfyUI AnimateDiff 클립 생성...')
      clip_paths = generate_all_clips(
        audio_paths,
        alignment_paths,
        schedule_path,
        use_cache=True
      )
      assert len(clip_paths) > 0
      logger.info(f'✓ Step 4 완료: {len(clip_paths)}개 클립')

      # Step 5: Final Video Composition
      logger.info('🎬 Step 5: 최종 영상 병합 + 자막...')
      output_path = compose_final_video(
        clip_paths,
        audio_paths,
        alignment_paths,
        nlp_data,
        use_cache=True
      )
      assert Path(output_path).exists()
      logger.info(f'✓ Step 5 완료: {output_path}')

      logger.info('\n' + '=' * 60)
      logger.info('✓ 전체 파이프라인 (Step 2~5) 완료')
      logger.info(f'  최종 영상: {output_path}')
      logger.info('=' * 60)

    except Exception as e:
      pytest.fail(f'파이프라인 실행 실패: {e}')


class TestPipelineWithCache:
  """캐시를 활용한 부분 파이프라인 테스트"""

  def test_pipeline_step2_cached(self, script_data):
    """Step 2 결과가 캐시에 있으면 사용"""
    cache_files = sorted(Path('cache/step2').glob('*_audio.mp3'))

    if cache_files:
      logger.info(f'✓ Step 2 캐시 발견: {len(cache_files)}개')
      assert len(cache_files) > 0
    else:
      logger.warning('Step 2 캐시 없음 — ElevenLabs 실행 필요')

  def test_pipeline_step3_cached(self):
    """Step 3 결과가 캐시에 있으면 사용"""
    cache_files = sorted(Path('cache/step3').glob('*_schedule.json'))

    if cache_files:
      logger.info(f'✓ Step 3 캐시 발견: {len(cache_files)}개')
      assert len(cache_files) > 0
    else:
      logger.warning('Step 3 캐시 없음 — 동적 스케줄링 실행 필요')

  def test_pipeline_step4_cached(self):
    """Step 4 결과가 캐시에 있으면 사용"""
    cache_files = sorted(Path('cache/step4').glob('*_clip.mp4'))

    if cache_files:
      logger.info(f'✓ Step 4 캐시 발견: {len(cache_files)}개')
      assert len(cache_files) > 0
    else:
      logger.warning('Step 4 캐시 없음 — ComfyUI 실행 필요')

  def test_pipeline_step5_cached(self):
    """Step 5 결과가 캐시에 있으면 사용"""
    cache_files = sorted(Path('cache/step5').glob('*_shorts.mp4'))

    if cache_files:
      logger.info(f'✓ Step 5 캐시 발견: {len(cache_files)}개')
      assert len(cache_files) > 0
    else:
      logger.warning('Step 5 캐시 없음 — 최종 영상 생성 필요')
