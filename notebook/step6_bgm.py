"""
Step 6: Stable Audio BGM 생성 + Step 5 영상과 오디오 믹싱
씬 감정(emotion) 기반으로 배경음악 프롬프트 동적 생성
"""

import json
import logging
import os
from pathlib import Path

import numpy as np
import torch
from dotenv import load_dotenv
from moviepy.editor import AudioFileClip, CompositeAudioClip, VideoFileClip

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(
  level=logging.INFO,
  format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# 환경변수
STABLE_AUDIO_MODEL = os.getenv('STABLE_AUDIO_MODEL', 'stabilityai/stable-audio-open-1.0')
BGM_VOLUME = float(os.getenv('BGM_VOLUME', '0.25'))
BGM_SAMPLE_RATE = 44100  # Stable Audio 출력 샘플레이트
BGM_CHANNELS = 2  # 스테레오


# 감정 매핑: emotion → BGM 프롬프트
EMOTION_PROMPT_MAP = {
  'peaceful': 'soft, ambient, traditional Korean guqin, peaceful, meditative',
  'joyful': 'bright, uplifting, traditional Korean music, cheerful, gentle',
  'melancholic': 'soft, melancholic piano, traditional Korean haegeum, contemplative',
  'solemn': 'serious, orchestral, traditional Korean court music, majestic',
  'dramatic': 'intense, dramatic, traditional Korean pansori-inspired, powerful',
  'romantic': 'romantic, gentle, traditional Korean gayageum, tender',
  'mysterious': 'mysterious, ambient, traditional Korean bamboo flute, enigmatic',
}

DEFAULT_EMOTION_PROMPT = 'soft, ambient, traditional Korean music, peaceful instrumental'


def get_cache_path(poem_dir: Path) -> Path:
  """캐시 경로: step6_final.mp4"""
  return Path(poem_dir) / 'step6_final.mp4'


def load_nlp_data(nlp_path: str) -> dict:
  """Step 1 NLP JSON 로드"""
  try:
    with open(nlp_path, 'r', encoding='utf-8') as f:
      return json.load(f)
  except Exception as e:
    logger.error(f'NLP 데이터 로드 실패: {nlp_path}, {e}')
    return {}


def generate_bgm_prompt(nlp_data: dict) -> str:
  """
  NLP 데이터의 scenes 감정 목록에서 대표 감정 추출 후
  동적으로 BGM 프롬프트 생성
  """
  if not nlp_data or 'scenes' not in nlp_data:
    logger.warning('씬 감정 정보 없음, 기본 프롬프트 사용')
    return DEFAULT_EMOTION_PROMPT

  emotions = [scene.get('emotion', 'peaceful') for scene in nlp_data['scenes']]
  emotion_counts = {}
  for emotion in emotions:
    emotion_counts[emotion] = emotion_counts.get(emotion, 0) + 1

  # 가장 많은 감정 선택 (tie일 경우 첫 번째)
  dominant_emotion = max(emotion_counts, key=emotion_counts.get, default='peaceful')
  prompt = EMOTION_PROMPT_MAP.get(dominant_emotion, DEFAULT_EMOTION_PROMPT)

  logger.info(f'씬 감정 분석: {emotion_counts} → 대표: {dominant_emotion}')
  logger.info(f'BGM 프롬프트: {prompt}')

  return prompt


def generate_stable_audio(prompt: str, duration_seconds: float) -> tuple:
  """
  Stable Audio로 배경음악 생성
  반환: (numpy 오디오 배열, 샘플레이트)
  """
  logger.info(f'Stable Audio 모델 로드: {STABLE_AUDIO_MODEL}')

  try:
    # Stable Audio 모델 로드
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    logger.info(f'Device: {device}')

    # Hugging Face 모델로 로드 (커뮤니티 라이선스 필수)
    from diffusers import StableAudioPipeline

    pipe = StableAudioPipeline.from_pretrained(
      STABLE_AUDIO_MODEL,
      torch_dtype=torch.float16,
      use_safetensors=True,
    )
    pipe = pipe.to(device)

    logger.info(f'오디오 생성 중: {prompt} ({duration_seconds:.1f}초)')

    # 생성
    with torch.no_grad():
      audio = pipe(
        prompt,
        duration=duration_seconds,
        guidance_scale=7.0,
      ).audios

    logger.info(f'오디오 생성 완료: shape={audio.shape}')
    return audio[0].cpu().numpy(), BGM_SAMPLE_RATE

  except Exception as e:
    logger.error(f'Stable Audio 생성 실패: {e}')
    raise


def mix_audio_with_bgm(
  video_path: str,
  bgm_audio: tuple,
  bgm_volume: float = BGM_VOLUME,
) -> tuple:
  """
  Step 5 영상의 나레이션 오디오 + BGM 믹싱
  반환: (CompositeAudioClip, 임시 파일 경로)
  """
  logger.info(f'영상 로드: {video_path}')
  video = VideoFileClip(video_path)
  video_duration = video.duration
  video_audio = video.audio

  logger.info(f'영상 길이: {video_duration:.2f}초')

  # BGM을 numpy에서 AudioFileClip으로 변환
  bgm_np, bgm_sr = bgm_audio
  logger.info(f'BGM: shape={bgm_np.shape}, sr={bgm_sr}')

  # MoviePy는 numpy 오디오를 직접 처리하려면 make_frame 콜백 필요
  # 대신 임시 파일로 저장 후 로드
  import tempfile
  import soundfile as sf

  with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
    tmp_path = tmp.name

  try:
    sf.write(tmp_path, bgm_np.T, bgm_sr)  # numpy는 (channels, samples) 형태
    logger.info(f'임시 BGM 파일 저장: {tmp_path}')

    bgm_clip = AudioFileClip(tmp_path)

    # BGM을 영상 길이만큼 루프 또는 자르기
    if bgm_clip.duration < video_duration:
      logger.warning(f'BGM 길이({bgm_clip.duration:.2f}s) < 영상 길이({video_duration:.2f}s), 루프 처리')
      # 간단한 루프: numpy 배열에서 반복
      required_samples = int(video_duration * bgm_sr)
      bgm_samples = bgm_np
      while bgm_samples.shape[1] < required_samples:
        bgm_samples = np.concatenate([bgm_samples, bgm_np], axis=1)
      bgm_samples = bgm_samples[:, :required_samples]
      sf.write(tmp_path, bgm_samples.T, bgm_sr)
      bgm_clip = AudioFileClip(tmp_path)

    else:
      # BGM을 영상 길이만큼 자르기
      bgm_clip = bgm_clip.subclipped(0, video_duration)

    # 볼륨 조정 (나레이션이 메인이므로 BGM은 낮게)
    bgm_clip = bgm_clip.multiply_volume(bgm_volume)

    logger.info(f'오디오 믹싱: 나레이션 + BGM(volume={bgm_volume})')

    # 두 오디오를 동시에 재생 (믹싱)
    mixed_audio = CompositeAudioClip([video_audio, bgm_clip])

    logger.info(f'최종 오디오: {mixed_audio.duration:.2f}초')

    return mixed_audio, tmp_path

  except Exception as e:
    logger.error(f'오디오 믹싱 실패: {e}')
    if os.path.exists(tmp_path):
      os.remove(tmp_path)
    raise


def compose_final_video_with_bgm(
  video_path: str,
  mixed_audio: 'AudioFileClip',
  output_path: str,
) -> None:
  """
  Step 5 영상에 믹싱된 오디오를 설정하고 최종 저장
  """
  logger.info(f'최종 영상 합성: {video_path}')

  video = VideoFileClip(video_path)
  final_video = video.set_audio(mixed_audio)

  logger.info(f'최종 영상 저장: {output_path}')
  final_video.write_videofile(
    output_path,
    codec='libx264',
    audio_codec='aac',
    fps=30,
    verbose=False,
    logger=None,
  )

  video.close()
  final_video.close()
  logger.info('✓ Step 6 완료')


def run_step6(poem_dir: str, use_cache: bool = True) -> str:
  """
  Main Step 6 함수
  입력: {poem_dir}/step1_nlp.json, {poem_dir}/step5_shorts.mp4
  출력: {poem_dir}/step6_final.mp4
  """
  poem_dir = Path(poem_dir)
  nlp_path = poem_dir / 'step1_nlp.json'
  video_path = poem_dir / 'step5_shorts.mp4'
  output_path = get_cache_path(poem_dir)

  logger.info(f'Step 6 시작: {poem_dir}')

  # 캐시 확인
  if use_cache and output_path.exists():
    logger.info(f'✓ 캐시 사용: {output_path}')
    return str(output_path)

  # Step 5 영상 확인
  if not video_path.exists():
    raise FileNotFoundError(f'Step 5 영상 없음: {video_path}')

  # NLP 데이터 로드
  nlp_data = load_nlp_data(str(nlp_path))

  # BGM 프롬프트 생성
  bgm_prompt = generate_bgm_prompt(nlp_data)

  # Step 5 영상 길이 확인
  video = VideoFileClip(str(video_path))
  video_duration = video.duration
  video.close()

  logger.info(f'영상 길이: {video_duration:.2f}초')

  # Stable Audio로 배경음악 생성
  bgm_audio = generate_stable_audio(bgm_prompt, video_duration)

  # 오디오 믹싱
  mixed_audio, tmp_bgm_path = mix_audio_with_bgm(str(video_path), bgm_audio)

  try:
    # 최종 영상 저장
    compose_final_video_with_bgm(str(video_path), mixed_audio, str(output_path))

  finally:
    # 임시 파일 정리
    if os.path.exists(tmp_bgm_path):
      os.remove(tmp_bgm_path)
      logger.info(f'임시 파일 삭제: {tmp_bgm_path}')

  return str(output_path)


if __name__ == '__main__':
  import sys

  if len(sys.argv) < 2:
    print('사용법: python step6_bgm.py <nlp_json_path>')
    print('예시: python step6_bgm.py cache/poem_01/step1_nlp.json')
    sys.exit(1)

  nlp_path = sys.argv[1]
  poem_dir = Path(nlp_path).parent

  output = run_step6(str(poem_dir), use_cache=False)
  print(f'✓ 최종 출력: {output}')
