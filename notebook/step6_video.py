"""
Step 6: 이미지+오디오 슬라이드쇼 + 자막 Burn-in + BGM 믹싱 최종 병합
테마별 자막 스타일 + BGM 볼륨 적용
"""

import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from moviepy.editor import (
  AudioFileClip,
  ColorClip,
  CompositeAudioClip,
  CompositeVideoClip,
  ImageClip,
  concatenate_videoclips,
)

load_dotenv()

logger = logging.getLogger(__name__)

# 환경변수
SUBTITLE_FONT_PATH = Path(os.getenv(
  'SUBTITLE_FONT_PATH',
  os.path.expandvars('%LOCALAPPDATA%/Microsoft/Windows/Fonts/NanumSquare.ttf'),
))
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
OUTPUT_FPS = 30


def get_cache_path(poem_dir: Path) -> Path:
  """캐시 경로 생성"""
  return Path(poem_dir) / 'step6' / 'shorts.mp4'


def get_audio_duration(audio_path: str) -> float:
  """오디오 파일 길이(초) 조회"""
  try:
    audio = AudioFileClip(audio_path)
    duration = audio.duration
    audio.close()
    return duration
  except Exception as e:
    logger.error(f'오디오 길이 조회 실패: {audio_path}, {e}')
    return 0.0


def load_alignment_data(alignment_path: str) -> dict:
  """alignment JSON 로드"""
  try:
    with open(alignment_path, 'r', encoding='utf-8') as f:
      return json.load(f)
  except Exception as e:
    logger.error(f'alignment 로드 실패: {alignment_path}, {e}')
    return {'sentences': [], 'total_duration': 0}


def render_subtitle_image(
  text: str,
  canvas_width: int,
  canvas_height: int,
  font_size: int,
  color: tuple,
  opacity: float,
  stroke_color: tuple = (0, 0, 0),
  stroke_width: int = 3,
):
  """
  PIL로 자막 텍스트를 RGBA 이미지로 렌더링.
  배경 없이 테마별 색상 텍스트, 캔버스 크기는 canvas_width × canvas_height.
  텍스트는 세로 50% 위치에 가로 가운데 정렬.
  """
  import numpy as np
  from PIL import Image, ImageDraw, ImageFont

  img = Image.new('RGBA', (canvas_width, canvas_height), (0, 0, 0, 0))
  draw = ImageDraw.Draw(img)

  # 폰트 로드
  try:
    font = ImageFont.truetype(str(SUBTITLE_FONT_PATH), font_size)
  except Exception:
    font = ImageFont.load_default()
    logger.warning('자막 폰트 로드 실패, 기본 폰트 사용')

  # 텍스트 줄바꿈 (어절 단위, 단어 중간에서 잘리지 않도록)
  max_text_width = int(canvas_width * 0.85)
  lines = []
  for paragraph in text.split('\n'):
    words = paragraph.split(' ')  # 어절(띄어쓰기) 단위
    current_line = ''
    for word in words:
      test_line = f'{current_line} {word}'.strip() if current_line else word
      bbox = draw.textbbox((0, 0), test_line, font=font)
      if bbox[2] - bbox[0] > max_text_width and current_line:
        lines.append(current_line)
        current_line = word
      else:
        current_line = test_line
    if current_line:
      lines.append(current_line)

  if not lines:
    import numpy as np
    return np.array(img)

  # 전체 텍스트 블록 높이 계산
  line_height = draw.textbbox((0, 0), '가', font=font)[3] + 8
  total_text_height = line_height * len(lines)

  # 세로 65% 위치 기준 가운데 정렬 (숏츠 하단 자막)
  y_center = int(canvas_height * 0.65)
  y_start = y_center - total_text_height // 2

  # opacity 적용 (0.0~1.0 → 0~255)
  alpha = int(opacity * 255)

  for line in lines:
    bbox = draw.textbbox((0, 0), line, font=font)
    line_width = bbox[2] - bbox[0]
    x = (canvas_width - line_width) // 2
    draw.text(
      (x, y_start), line, font=font,
      fill=(*color, alpha),
      stroke_width=stroke_width,
      stroke_fill=(*stroke_color, alpha),
    )
    y_start += line_height

  import numpy as np
  return np.array(img)


def make_subtitle_clip(
  text: str,
  duration: float,
  start_time: float,
  font_size: int,
  color: tuple,
  opacity: float,
  stroke_color: tuple = (0, 0, 0),
  stroke_width: int = 3,
) -> ImageClip:
  """PIL로 렌더링한 자막 이미지를 MoviePy ImageClip으로 반환"""
  arr = render_subtitle_image(
    text, OUTPUT_WIDTH, OUTPUT_HEIGHT, font_size, color, opacity,
    stroke_color=stroke_color, stroke_width=stroke_width,
  )
  clip = (
    ImageClip(arr, ismask=False)
    .set_duration(duration)
    .set_start(start_time)
    .set_position((0, 0))
  )
  return clip


def concatenate_clips(
  still_paths: list[str],
  audio_paths: list[str]
) -> object:
  """
  문장 단위 이미지들을 시간순서대로 연결 + 오디오 싱크.
  각 이미지 duration은 오디오 길이에 맞춤.
  반환: 연결된 VideoClip
  """
  import numpy as np
  from PIL import Image as PILImage

  clips = []
  total_duration = 0

  for clip_idx, still_path in enumerate(still_paths):
    if clip_idx >= len(audio_paths):
      logger.warning(f'문장{clip_idx}: audio_paths 범위 초과, 스킵')
      continue

    try:
      audio = AudioFileClip(audio_paths[clip_idx])
      audio_duration = audio.duration

      img = PILImage.open(still_path).convert('RGB')
      img_arr = np.array(img, dtype=np.uint8)
      clip = ImageClip(img_arr, ismask=False).set_duration(audio_duration).set_fps(OUTPUT_FPS)
      clip = clip.set_audio(audio)

      clips.append(clip)
      total_duration += clip.duration
      logger.info(f'문장{clip_idx} 로드: {Path(still_path).name} ({clip.duration:.2f}s)')
    except Exception as e:
      logger.error(f'이미지 로드 실패: {still_path}, {e}')
      raise

  if not clips:
    raise ValueError('연결할 이미지가 없습니다')

  concatenated = concatenate_videoclips(clips)
  logger.info(f'이미지 연결 완료: 총 {len(clips)}개 문장, {total_duration:.2f}s')
  return concatenated


def add_subtitles_to_video(
  video_clip,
  sentence_schedules: list[dict],
  font_size: int,
  color: tuple,
  opacity: float,
  stroke_color: tuple = (0, 0, 0),
  stroke_width: int = 3,
):
  """이미 합성된 비디오 위에 씬별 자막을 순차적으로 얹음 (숏츠 스타일 적용)"""
  subtitle_clips = []
  current_time = 0.0

  for entry in sentence_schedules:
    text = entry.get('text', '')
    duration = entry.get('duration', 0.0)

    if text and duration > 0:
      sub = make_subtitle_clip(
        text, duration, current_time, font_size, color, opacity,
        stroke_color=stroke_color, stroke_width=stroke_width,
      )
      subtitle_clips.append(sub)

    current_time += duration

  if not subtitle_clips:
    logger.warning('자막 클립이 없습니다')
    return video_clip

  logger.info('자막 클립 %d개 생성 완료', len(subtitle_clips))
  return CompositeVideoClip([video_clip] + subtitle_clips, size=video_clip.size)


def mix_bgm_into_video(video_clip, bgm_path: str, tts_vol: float, bgm_vol: float):
  """
  video_clip의 TTS 오디오 + step5_bgm.wav 믹싱.
  tts_vol / bgm_vol 은 theme_config에서 조회한 볼륨 값.
  """
  import numpy as np
  import soundfile as sf

  logger.info(f'BGM 믹싱: {bgm_path} (TTS={tts_vol}, BGM={bgm_vol})')

  # TTS 볼륨 조정
  tts_audio = video_clip.audio.volumex(tts_vol)
  video_duration = video_clip.duration

  # BGM 로드
  bgm_data, bgm_sr = sf.read(bgm_path)  # shape: (samples, channels)
  bgm_np = bgm_data.T  # → (channels, samples)

  # BGM 영상 길이만큼 조정 (루프 또는 자르기)
  import tempfile
  with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
    tmp_path = tmp.name

  try:
    required_samples = int(video_duration * bgm_sr)
    bgm_samples = bgm_np

    if bgm_samples.shape[1] < required_samples:
      # 루프
      while bgm_samples.shape[1] < required_samples:
        bgm_samples = np.concatenate([bgm_samples, bgm_np], axis=1)

    bgm_samples = bgm_samples[:, :required_samples]
    sf.write(tmp_path, bgm_samples.T, bgm_sr)

    bgm_clip = AudioFileClip(tmp_path).subclip(0, video_duration)
    bgm_clip = bgm_clip.volumex(bgm_vol)

    mixed = CompositeAudioClip([tts_audio, bgm_clip])
    logger.info(f'BGM 믹싱 완료: {mixed.duration:.2f}초')
    return video_clip.set_audio(mixed), tmp_path

  except Exception as e:
    logger.error(f'BGM 믹싱 실패: {e}')
    import os
    if os.path.exists(tmp_path):
      os.remove(tmp_path)
    raise


def resize_video_to_shorts_format(video_clip, target_width: int = OUTPUT_WIDTH, target_height: int = OUTPUT_HEIGHT):
  """비디오를 쇼츠 형식으로 리사이즈 (1080×1920)"""
  current_width, current_height = video_clip.size

  if (current_width, current_height) == (target_width, target_height):
    logger.info(f'이미 쇼츠 형식: {target_width}×{target_height}')
    return video_clip

  logger.info(f'비디오 리사이즈: {current_width}×{current_height} → {target_width}×{target_height}')

  aspect_ratio = current_width / current_height
  target_aspect = target_width / target_height

  if aspect_ratio > target_aspect:
    new_height = target_height
    new_width = int(new_height * aspect_ratio)
  else:
    new_width = target_width
    new_height = int(new_width / aspect_ratio)

  resized = video_clip.resize((new_width, new_height))

  background = ColorClip(
    size=(target_width, target_height),
    color=(0, 0, 0)
  ).set_duration(resized.duration)

  offset_x = (target_width - new_width) // 2
  offset_y = (target_height - new_height) // 2

  final_clip = CompositeVideoClip(
    [background, resized.set_position((offset_x, offset_y))]
  ).set_fps(OUTPUT_FPS)

  logger.info('리사이즈 완료')
  return final_clip


def compose_final_video(
  still_image_paths: list[str],
  audio_paths: list[str],
  sentence_schedule_path: str,
  poem_dir: Path,
  use_cache: bool = True
) -> str:
  """
  최종 영상 합성:
  1. 문장 단위 이미지 연결 + 오디오 싱크
  2. 쇼츠 형식 리사이즈 (1080×1920)
  3. 테마별 자막 Burn-in
  4. BGM 믹싱 (step5_bgm.wav 존재 시)
  5. MP4 저장

  반환: 최종 영상 파일 경로
  """
  import os

  output_path = get_cache_path(poem_dir)

  # 캐시 확인
  if use_cache and output_path.exists():
    logger.info(f'캐시된 영상 사용: {output_path}')
    return str(output_path)

  logger.info('최종 영상 합성 중...')

  # 테마 기반 자막 스타일 로드
  nlp_path = Path(poem_dir) / 'step1' / 'nlp.json'
  primary_theme = 'A'
  surface_theme = 'A'
  if nlp_path.exists():
    try:
      with open(nlp_path, 'r', encoding='utf-8') as f:
        nlp_data = json.load(f)
      primary_theme = nlp_data.get('primary_theme', nlp_data.get('theme', 'A'))
      surface_theme = nlp_data.get('surface_theme', nlp_data.get('theme', 'A'))
    except Exception:
      primary_theme = 'A'
      surface_theme = 'A'

  try:
    from theme_config import get_bgm_volume, get_subtitle_style
    subtitle_style = get_subtitle_style(surface_theme)   # 자막: 시각적 표면 테마
    bgm_volume = get_bgm_volume(primary_theme)           # 볼륨: 감정 진심 테마
  except Exception:
    subtitle_style = {'color': (0, 0, 0), 'size': 48, 'opacity': 1.0}
    bgm_volume = {'tts': 0.9, 'bgm': 0.25}

  logger.info(
    f'primary_theme={primary_theme}, surface_theme={surface_theme}, '
    f'자막색={subtitle_style["color"]}, 자막크기={subtitle_style["size"]}'
  )

  tmp_bgm_path = None
  try:
    # 문장 스케줄 JSON 로드
    with open(sentence_schedule_path, 'r', encoding='utf-8') as f:
      schedule_data = json.load(f)
    sentence_schedules = schedule_data.get('sentence_schedules', [])

    # 1. 문장 단위 이미지 연결 + 오디오 싱크
    video = concatenate_clips(still_image_paths, audio_paths)
    logger.info(f'이미지 연결 완료: {video.duration:.2f}s')

    # 2. 쇼츠 형식 리사이즈
    video = resize_video_to_shorts_format(video)
    logger.info('쇼츠 형식 변환 완료')

    # 3. 테마별 자막 Burn-in
    try:
      video = add_subtitles_to_video(
        video,
        sentence_schedules,
        font_size=subtitle_style['size'],
        color=subtitle_style['color'],
        opacity=subtitle_style['opacity'],
        stroke_color=subtitle_style.get('stroke_color', (0, 0, 0)),
        stroke_width=subtitle_style.get('stroke_width', 3),
      )
      logger.info('자막 Burn-in 완료')
    except Exception as e:
      logger.warning(f'자막 추가 실패 (계속): {e}')

    # 4. BGM 믹싱 (step5_bgm.wav 존재 시)
    bgm_path = Path(poem_dir) / 'step5' / 'bgm.wav'
    if bgm_path.exists():
      try:
        video, tmp_bgm_path = mix_bgm_into_video(
          video,
          str(bgm_path),
          tts_vol=bgm_volume['tts'],
          bgm_vol=bgm_volume['bgm'],
        )
        logger.info('BGM 믹싱 완료')
      except Exception as e:
        logger.warning(f'BGM 믹싱 실패 (자막만 영상 저장): {e}')
    else:
      logger.info('step5_bgm.wav 없음, BGM 믹싱 스킵')

    # 5. 최종 저장
    output_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f'최종 영상 저장 중: {output_path}')

    video.write_videofile(
      str(output_path),
      fps=OUTPUT_FPS,
      codec='libx264',
      audio_codec='aac',
      verbose=False,
      logger=None
    )

    logger.info(f'최종 영상 저장 완료: {output_path}')
    video.close()

    return str(output_path)

  except Exception as e:
    logger.error(f'최종 영상 합성 실패: {e}')
    raise
  finally:
    # 임시 BGM 파일 정리
    if tmp_bgm_path and os.path.exists(tmp_bgm_path):
      os.remove(tmp_bgm_path)
      logger.info(f'임시 파일 삭제: {tmp_bgm_path}')


def run_step6(
  poem_dir: str,
  still_image_paths: list[str] | None = None,
  audio_paths: list[str] | None = None,
  sentence_schedule_path: str | None = None,
  use_cache: bool = True,
) -> str:
  """
  Main Step 6 함수 — 이미지+오디오+자막+BGM 최종 병합.
  입력: step4 PNG, step2 MP3, step3 schedule JSON, step5 BGM WAV (선택)
  출력: {poem_dir}/step6_shorts.mp4
  """
  poem_dir = Path(poem_dir)

  # 파일 자동 탐색 (파라미터 미제공 시)
  if still_image_paths is None:
    still_image_paths = sorted([str(f) for f in (poem_dir / 'step4').glob('*_still.png')])
  if audio_paths is None:
    audio_paths = sorted([str(f) for f in (poem_dir / 'step2').glob('*_audio.mp3')])
  if sentence_schedule_path is None:
    schedule_path = poem_dir / 'step3' / 'sentence_schedule.json'
    if not schedule_path.exists():
      raise FileNotFoundError(f'Step 3 스케줄 없음: {schedule_path}')
    sentence_schedule_path = str(schedule_path)

  if not still_image_paths:
    raise FileNotFoundError(f'Step 4 이미지 없음: {poem_dir}')
  if not audio_paths:
    raise FileNotFoundError(f'Step 2 오디오 없음: {poem_dir}')

  return compose_final_video(
    still_image_paths,
    audio_paths,
    sentence_schedule_path,
    poem_dir,
    use_cache=use_cache,
  )


def cmd_check() -> bool:
  """환경 확인"""
  checks = []

  if SUBTITLE_FONT_PATH.exists():
    logger.info(f'자막 폰트 존재: {SUBTITLE_FONT_PATH}')
    checks.append(True)
  else:
    logger.warning(f'자막 폰트 없음: {SUBTITLE_FONT_PATH} (기본값 사용)')
    checks.append(True)

  try:
    import moviepy  # noqa: F401
    logger.info('MoviePy 설치됨')
    checks.append(True)
  except ImportError:
    logger.error('MoviePy 설치 필요')
    checks.append(False)

  return all(checks)


if __name__ == '__main__':
  import sys

  logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
      logging.FileHandler('step6_video.log', encoding='utf-8'),
      logging.StreamHandler()
    ]
  )

  if len(sys.argv) < 2:
    logger.error('사용법: python step6_video.py <poem_dir>')
    sys.exit(1)

  poem_dir_arg = Path(sys.argv[1])

  if not cmd_check():
    logger.error('환경 확인 실패')
    sys.exit(1)

  try:
    output_path = run_step6(str(poem_dir_arg), use_cache=True)
    if Path(output_path).exists():
      size_mb = Path(output_path).stat().st_size / (1024 * 1024)
      logger.info(f'영상 합성 완료: {Path(output_path).name} ({size_mb:.1f}MB)')
    else:
      logger.error(f'출력 파일 없음: {output_path}')
      sys.exit(1)
  except Exception as e:
    logger.error(f'Step 6 실패: {e}', exc_info=True)
    sys.exit(1)
