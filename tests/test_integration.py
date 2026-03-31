"""
통합 테스트 — Step 2~5 순서대로, 실제 API/GPU 필요
ElevenLabs API, ComfyUI, MoviePy 등의 실제 의존성이 필요합니다.
"""

import json
import logging
from pathlib import Path
import pytest

from step2_tts import generate_all_audio
from step3_scheduler import build_frame_schedules
from step4_clip import generate_all_clips

# MoviePy 의존성이 없을 수 있으므로 조건부 import
try:
  from step5_video import compose_final_video
except ModuleNotFoundError:
  compose_final_video = None

logger = logging.getLogger(__name__)


class TestStep2AudioGeneration:
  """Step 2: ElevenLabs TTS + alignment 생성"""

  @pytest.mark.slow
  def test_step2_audio_generation(self, script_data):
    """오디오 + alignment 생성 (ElevenLabs API 필요)"""
    if not script_data:
      pytest.skip('Step 1 스크립트 데이터 없음')

    try:
      audio_paths, alignment_paths = generate_all_audio(script_data, use_cache=True)

      assert len(audio_paths) > 0, 'MP3 경로 생성 실패'
      assert len(alignment_paths) > 0, 'alignment JSON 경로 생성 실패'
      assert len(audio_paths) == len(alignment_paths), '오디오와 alignment 개수 불일치'

      # 각 파일 존재 여부 확인
      for audio_path in audio_paths:
        assert Path(audio_path).exists(), f'{audio_path} 파일 없음'

      for alignment_path in alignment_paths:
        assert Path(alignment_path).exists(), f'{alignment_path} 파일 없음'
        # alignment JSON 구조 검증
        with open(alignment_path, 'r', encoding='utf-8') as f:
          alignment = json.load(f)
        assert 'total_duration' in alignment
        assert 'words' in alignment
        assert 'sentences' in alignment

      logger.info(f'✓ Step 2 완료: {len(audio_paths)}개 오디오 + alignment 생성')
    except Exception as e:
      pytest.fail(f'Step 2 실행 실패: {e}')


class TestStep3Scheduling:
  """Step 3: 동적 프레임 스케줄링"""

  @pytest.mark.slow
  def test_step3_schedule_with_mock_alignment(self, script_data, mock_alignment_data):
    """Mock alignment로 스케줄 생성 (실제 API 불필요)"""
    if not script_data:
      pytest.skip('Step 1 스크립트 데이터 없음')

    # Mock alignment 파일 생성
    from pathlib import Path
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='_alignment.json',
                                     dir='cache/step2', delete=False, encoding='utf-8') as f:
      json.dump(mock_alignment_data, f)
      mock_alignment_path = f.name

    try:
      alignment_paths = [mock_alignment_path] * len(script_data)

      schedule_path = build_frame_schedules(
        script_data,
        alignment_paths,
        use_cache=False  # Mock 데이터이므로 캐시 무시
      )

      assert Path(schedule_path).exists(), f'스케줄 파일 생성 실패: {schedule_path}'

      with open(schedule_path, 'r', encoding='utf-8') as f:
        schedule = json.load(f)

      # scene_schedules 또는 prompts 중 하나가 있어야 함
      has_schedule = 'scene_schedules' in schedule or 'prompts' in schedule
      assert has_schedule, 'schedule에 scene_schedules 또는 prompts 키 없음'

      if 'scene_schedules' in schedule:
        logger.info(f'✓ Step 3 완료: {len(schedule["scene_schedules"])}개 씬 스케줄 생성')
      else:
        logger.info(f'✓ Step 3 완료: {len(schedule["prompts"])}개 프레임 스케줄 생성')
    except Exception as e:
      pytest.fail(f'Step 3 실행 실패: {e}')
    finally:
      # cleanup
      Path(mock_alignment_path).unlink(missing_ok=True)


class TestStep4ClipGeneration:
  """Step 4: ComfyUI AnimateDiff 클립 생성"""

  @pytest.mark.slow
  @pytest.mark.gpu_required
  def test_step4_clip_generation(self, nlp_cache_path):
    """ComfyUI 클립 생성 (GPU + ComfyUI 서버 필요)"""
    # Step 2, 3 결과가 있어야 함
    cache_step2 = sorted(Path('cache/step2').glob('*_audio.mp3'))
    cache_step3 = sorted(Path('cache/step3').glob('*_schedule.json'))

    if not cache_step2:
      pytest.skip('Step 2 캐시 없음 (ElevenLabs 실행 필요)')
    if not cache_step3:
      pytest.skip('Step 3 캐시 없음 (동적 스케줄링 필요)')

    try:
      schedule_path = str(cache_step3[0])

      clip_paths = generate_all_clips(
        schedule_path,
        use_cache=True
      )

      assert len(clip_paths) > 0, '클립 생성 실패'
      for clip_path in clip_paths:
        assert Path(clip_path).exists(), f'{clip_path} 파일 없음'

      logger.info(f'✓ Step 4 완료: {len(clip_paths)}개 클립 생성')
    except Exception as e:
      pytest.fail(f'Step 4 실행 실패: {e}')


class TestStep5Merge:
  """Step 5: 최종 영상 병합 + 자막"""

  @pytest.mark.slow
  def test_step5_compose_final_video(self, nlp_cache_path):
    """최종 영상 병합 (Step 4 결과 필요)"""
    if compose_final_video is None:
      pytest.skip('MoviePy 모듈 없음')

    cache_step4 = sorted(Path('cache/step4').glob('*_clip.mp4'))

    if not cache_step4:
      pytest.skip('Step 4 캐시 없음 (AnimateDiff 실행 필요)')

    try:
      with open(nlp_cache_path, 'r', encoding='utf-8') as f:
        nlp_data = json.load(f)

      alignment_paths = sorted(Path('cache/step2').glob('*_alignment.json'))
      audio_paths = sorted(Path('cache/step2').glob('*_audio.mp3'))

      if not alignment_paths or not audio_paths:
        pytest.skip('Step 2 alignment/audio 캐시 없음')

      output_path = compose_final_video(
        [str(p) for p in cache_step4],
        [str(p) for p in audio_paths],
        [str(p) for p in alignment_paths],
        nlp_data,
        use_cache=True
      )

      assert Path(output_path).exists(), f'최종 영상 생성 실패: {output_path}'
      assert output_path.endswith('.mp4'), '출력 파일이 MP4가 아님'

      logger.info(f'✓ Step 5 완료: {output_path}')
    except Exception as e:
      pytest.fail(f'Step 5 실행 실패: {e}')
