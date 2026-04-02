"""
Step 5: AnimateDiff 클립 연결 + ElevenLabs 타임스탬프 기반 자막 Burn-in + 최종 병합
"""

import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from moviepy.editor import (
  AudioFileClip,
  ColorClip,
  CompositeVideoClip,
  ImageClip,
  concatenate_audioclips,
  concatenate_videoclips,
)

load_dotenv()

logger = logging.getLogger(__name__)

# 환경변수
CACHE_DIR = Path('cache/step5')
SUBTITLE_FONT_PATH = Path(os.getenv('SUBTITLE_FONT_PATH', 'C:/Windows/Fonts/malgun.ttf'))
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
OUTPUT_FPS = 30  # 10fps → 30fps 업스케일
SUBTITLE_FONT_SIZE = 48
SUBTITLE_COLOR = (255, 255, 255)  # RGB white


def get_cache_path(poem_dir: Path) -> Path:
  """캐시 경로 생성"""
  return poem_dir / 'step5_shorts.mp4'


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


def render_subtitle_image(text: str, canvas_width: int, canvas_height: int):
  """
  PIL로 자막 텍스트를 RGBA 이미지로 렌더링.
  배경 없이 흰색 텍스트만, 캔버스 크기는 canvas_width × canvas_height.
  텍스트는 세로 85% 위치에 가로 가운데 정렬.
  """
  import numpy as np
  from PIL import Image, ImageDraw, ImageFont

  img = Image.new('RGBA', (canvas_width, canvas_height), (0, 0, 0, 0))
  draw = ImageDraw.Draw(img)

  # 폰트 로드
  try:
    font = ImageFont.truetype(str(SUBTITLE_FONT_PATH), SUBTITLE_FONT_SIZE)
  except Exception:
    font = ImageFont.load_default()
    logger.warning('자막 폰트 로드 실패, 기본 폰트 사용')

  # 텍스트 줄바꿈 (최대 너비 기준)
  max_text_width = int(canvas_width * 0.85)
  lines = []
  for paragraph in text.split('\n'):
    words = list(paragraph)  # 한국어는 글자 단위
    current_line = ''
    for ch in words:
      test_line = current_line + ch
      bbox = draw.textbbox((0, 0), test_line, font=font)
      if bbox[2] - bbox[0] > max_text_width and current_line:
        lines.append(current_line)
        current_line = ch
      else:
        current_line = test_line
    if current_line:
      lines.append(current_line)

  if not lines:
    return np.array(img)

  # 전체 텍스트 블록 높이 계산
  line_height = draw.textbbox((0, 0), '가', font=font)[3] + 8
  total_text_height = line_height * len(lines)

  # 세로 85% 위치 기준 가운데 정렬
  y_center = int(canvas_height * 0.85)
  y_start = y_center - total_text_height // 2

  for line in lines:
    bbox = draw.textbbox((0, 0), line, font=font)
    line_width = bbox[2] - bbox[0]
    x = (canvas_width - line_width) // 2
    # 흰색 텍스트 + 얇은 검은 외곽선 (가독성)
    for dx, dy in [(-2, -2), (2, -2), (-2, 2), (2, 2)]:
      draw.text((x + dx, y_start + dy), line, font=font, fill=(0, 0, 0, 200))
    draw.text((x, y_start), line, font=font, fill=(*SUBTITLE_COLOR, 255))
    y_start += line_height

  return np.array(img)


def make_subtitle_clip(text: str, duration: float, start_time: float) -> ImageClip:
  """PIL로 렌더링한 자막 이미지를 MoviePy ImageClip으로 반환"""
  arr = render_subtitle_image(text, OUTPUT_WIDTH, OUTPUT_HEIGHT)
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
  문장 단위 이미지들을 시간순서대로 연결 + 오디오 싱크
  각 이미지 duration은 오디오 길이에 맞춤
  반환: 연결된 VideoClip (각 문장별 오디오 포함)
  """
  clips = []
  total_duration = 0

  for clip_idx, still_path in enumerate(still_paths):
    try:
      # 오디오 길이 확인
      if clip_idx >= len(audio_paths):
        logger.warning(f'문장{clip_idx}: audio_paths 범위 초과, 스킵')
        continue

      audio = AudioFileClip(audio_paths[clip_idx])
      audio_duration = audio.duration

      # PNG 이미지를 ImageClip으로 로드, 오디오 길이만큼 duration 설정
      clip = ImageClip(still_path).set_duration(audio_duration).set_fps(OUTPUT_FPS)
      clip = clip.set_audio(audio)

      clips.append(clip)
      total_duration += clip.duration
      logger.info(f'문장{clip_idx} 이미지 로드: {Path(still_path).name} ({clip.duration:.2f}s)')
    except Exception as e:
      logger.error(f'이미지 로드 실패: {still_path}, {e}')
      raise

  if not clips:
    raise ValueError('연결할 이미지가 없습니다')

  # 클립 연결
  concatenated = concatenate_videoclips(clips)
  logger.info(f'이미지 연결 완료: 총 {len(clips)}개 문장, {total_duration:.2f}s')
  return concatenated


def add_subtitles_to_video(video_clip, sentence_schedules: list[dict]):
  """이미 합성된 비디오 위에 씬별 자막을 순차적으로 얹음 (PIL 기반)"""
  subtitle_clips = []
  current_time = 0.0

  for entry in sentence_schedules:
    text = entry.get('text', '')
    duration = entry.get('duration', 0.0)

    if text and duration > 0:
      sub = make_subtitle_clip(text, duration, current_time)
      subtitle_clips.append(sub)

    current_time += duration

  if not subtitle_clips:
    logger.warning('자막 클립이 없습니다')
    return video_clip

  logger.info('자막 클립 %d개 생성 완료', len(subtitle_clips))
  return CompositeVideoClip([video_clip] + subtitle_clips, size=video_clip.size)


def composite_video_with_audio(
  video_clip,
  audio_paths: list[str]
):
  """
  비디오에 오디오 합치기
  여러 MP3 파일을 순차적으로 연결하여 오디오 트랙으로 설정
  """
  if not audio_paths:
    logger.warning('오디오 파일이 없습니다')
    return video_clip

  try:
    # 오디오 파일들을 순차적으로 연결
    audio_clips = []
    for audio_path in audio_paths:
      audio = AudioFileClip(audio_path)
      audio_clips.append(audio)
      logger.info(f'오디오 로드: {audio_path} ({audio.duration:.2f}s)')

    # 오디오 연결 (concatenate_audioclips 사용)
    if len(audio_clips) > 1:
      combined_audio = concatenate_audioclips(audio_clips)
    else:
      combined_audio = audio_clips[0]

    # 비디오에 오디오 설정
    final_video = video_clip.set_audio(combined_audio)
    logger.info(f'오디오 싱크 완료: {combined_audio.duration:.2f}s')
    return final_video

  except Exception as e:
    logger.error(f'오디오 합치기 실패: {e}')
    import traceback
    traceback.print_exc()
    return video_clip


def resize_video_to_shorts_format(
  video_clip,
  target_width: int = OUTPUT_WIDTH,
  target_height: int = OUTPUT_HEIGHT
):
  """
  비디오를 쇼츠 형식으로 리사이즈 (1080×1920)
  """
  current_width, current_height = video_clip.size

  if (current_width, current_height) == (target_width, target_height):
    logger.info(f'이미 쇼츠 형식: {target_width}×{target_height}')
    return video_clip

  logger.info(f'비디오 리사이즈: {current_width}×{current_height} → {target_width}×{target_height}')

  # 가로세로 비율 유지하며 리사이즈
  aspect_ratio = current_width / current_height
  target_aspect = target_width / target_height

  if aspect_ratio > target_aspect:
    # 현재 비디오가 더 넓음: 높이 기준으로 조정
    new_height = target_height
    new_width = int(new_height * aspect_ratio)
  else:
    # 현재 비디오가 더 좁음: 너비 기준으로 조정
    new_width = target_width
    new_height = int(new_width / aspect_ratio)

  resized = video_clip.resize((new_width, new_height))

  # 검은색 배경으로 센터링
  background = ColorClip(
    size=(target_width, target_height),
    color=(0, 0, 0)
  ).set_duration(resized.duration)

  # 비디오를 중앙에 배치
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
  최종 영상 합성 (문장 단위):
  1. 문장 단위 이미지 연결 + 오디오 싱크
  2. 문장 단위 자막 Burn-in
  3. 쇼츠 형식 리사이즈 (1080×1920)
  4. MP4 저장

  반환: 최종 영상 파일 경로
  """
  output_path = get_cache_path(poem_dir)

  # 캐시 확인
  if use_cache and output_path.exists():
    logger.info(f'캐시된 영상 사용: {output_path}')
    return str(output_path)

  logger.info('최종 영상 합성 중...')

  try:
    # 문장 스케줄 JSON 로드
    with open(sentence_schedule_path, 'r', encoding='utf-8') as f:
      schedule_data = json.load(f)
    sentence_schedules = schedule_data.get('sentence_schedules', [])

    # 1. 문장 단위 이미지 연결 + 오디오 싱크
    video = concatenate_clips(still_image_paths, audio_paths)
    logger.info(f'이미지 연결 완료: {video.duration:.2f}s')

    # 2. 쇼츠 형식 리사이즈 (자막 좌표 기준이 되는 1080×1920 확정)
    video = resize_video_to_shorts_format(video)
    logger.info('쇼츠 형식 변환 완료')

    # 3. 문장 단위 자막 Burn-in (리사이즈 후에 적용)
    try:
      video = add_subtitles_to_video(video, sentence_schedules)
      logger.info('자막 Burn-in 완료')
    except Exception as e:
      logger.warning(f'자막 추가 실패 (계속): {e}')

    # 4. 최종 저장
    output_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f'최종 영상 저장 중: {output_path}')

    video.write_videofile(
      str(output_path),
      fps=OUTPUT_FPS,
      codec='libx264',
      audio_codec='aac',
      verbose=False,
      logger=None  # 진행률 로그 억제
    )

    logger.info(f'✓ 최종 영상 저장 완료: {output_path}')
    video.close()

    return str(output_path)

  except Exception as e:
    logger.error(f'최종 영상 합성 실패: {e}')
    raise


def cmd_check() -> bool:
  """환경 확인"""
  checks = []

  # 폰트 파일 확인
  if SUBTITLE_FONT_PATH.exists():
    logger.info(f'✓ 자막 폰트 존재: {SUBTITLE_FONT_PATH}')
    checks.append(True)
  else:
    logger.warning(f'⚠ 자막 폰트 없음: {SUBTITLE_FONT_PATH} (기본값 사용)')
    checks.append(True)  # 경고지만 계속 진행 가능

  # MoviePy 확인
  try:
    import moviepy  # noqa: F401
    logger.info('✓ MoviePy 설치됨')
    checks.append(True)
  except ImportError:
    logger.error('✗ MoviePy 설치 필요')
    checks.append(False)

  return all(checks)


if __name__ == '__main__':
  import sys

  logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
      logging.FileHandler('step5_video.log', encoding='utf-8'),
      logging.StreamHandler()
    ]
  )

  logger.info('=' * 70)
  logger.info('Step 5: 최종 영상 합성 테스트')
  logger.info('=' * 70)

  # 파라미터 파싱
  if len(sys.argv) < 2:
    logger.error('✗ 사용법: python step5_video.py <poem_dir>')
    exit(1)

  poem_dir = Path(sys.argv[1])

  # 1. 환경 확인
  if not cmd_check():
    logger.error('✗ 환경 확인 실패')
    exit(1)

  # 2. Step 4 이미지 파일 탐색
  still_files = sorted(poem_dir.glob('step4_*_sent00_still.png'))
  if not still_files:
    logger.error(f'✗ Step 4 정지 이미지 없음: {poem_dir}')
    exit(1)

  still_paths = sorted([str(f) for f in still_files])
  logger.info(f'정지 이미지: {len(still_paths)}개')

  # 3. Step 2 오디오/alignment 파일 탐색
  audio_files = sorted(poem_dir.glob('step2_*_sent00_audio.mp3'))
  alignment_files = sorted(poem_dir.glob('step2_*_alignment.json'))

  if not audio_files or not alignment_files:
    logger.error(f'✗ Step 2 오디오/alignment 없음: {poem_dir}')
    exit(1)

  audio_paths = sorted([str(f) for f in audio_files])
  alignment_paths = sorted([str(f) for f in alignment_files])

  logger.info(f'오디오: {len(audio_paths)}개')

  if not (len(still_paths) == len(audio_paths)):
    logger.error(f'✗ 문장 개수 불일치: still={len(still_paths)}, audio={len(audio_paths)}')
    exit(1)

  # 4. Step 3 문장 스케줄 파일 로드
  schedule_path = poem_dir / 'step3_sentence_schedule.json'
  if not schedule_path.exists():
    logger.error(f'✗ Step 3 문장 스케줄 없음: {schedule_path}')
    exit(1)

  # 5. Step 5 실행
  try:
    logger.info('\n최종 영상 합성 실행 중...')
    output_path = compose_final_video(still_paths, audio_paths, str(schedule_path), poem_dir, use_cache=True)

    if Path(output_path).exists():
      size_mb = Path(output_path).stat().st_size / (1024 * 1024)
      logger.info(f'\n✓ 영상 합성 완료: {Path(output_path).name}')
      logger.info(f'  파일 크기: {size_mb:.1f}MB')

      logger.info('\n' + '=' * 70)
      logger.info('✓ Step 5 테스트 완료')
      logger.info('=' * 70)
      exit(0)
    else:
      logger.error(f'✗ 출력 파일 없음: {output_path}')
      exit(1)

  except Exception as e:
    logger.error(f'\n✗ Step 5 실패: {e}', exc_info=True)
    exit(1)
