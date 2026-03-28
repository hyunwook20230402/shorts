"""
Step 5: Video — MoviePy로 이미지 + 오디오 + 자막 합성 (최종 Shorts 영상)

입력: 이미지(cache/step2/) + 오디오(cache/step3/) + 자막(cache/step4/) + QA 리포트
출력: 최종 영상 (cache/step5/{hash}_shorts.mp4, 1080×1920, 60초 이내)

## 사용법
  uv run python step5_video.py --check
  uv run python step5_video.py cache/step1/xxx_nlp.json
  uv run python step5_video.py cache/step1/xxx_nlp.json --no-cache
  uv run python step5_video.py --clean-cache [--force]
"""

import argparse
import hashlib
import json
import logging
import os
import sys
import textwrap
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont

try:
  from moviepy.editor import (
    AudioFileClip,
    concatenate_audioclips,
    concatenate_videoclips,
    ImageClip,
    CompositeVideoClip,
  )
except ImportError as e:
  logging.error('MoviePy 미설치: %s', e)
  sys.exit(1)

# Windows에서 FFmpeg 경로 명시 설정
if sys.platform == 'win32':
  os.environ.setdefault('FFMPEG_BINARY', r'C:/ffmpeg/bin/ffmpeg.exe')

# 로거 설정
logger = logging.getLogger(__name__)
logging.basicConfig(
  level=logging.INFO,
  format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)

# 상수
CACHE_DIR = Path('cache/step5')
CACHE_DIR.mkdir(parents=True, exist_ok=True)

TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920
TARGET_FPS = 30

# Windows 시스템 폰트 경로
FONT_PATH = Path('C:/Windows/Fonts/malgun.ttf')

# ─────────────── SRT 파싱 ────────────────────────────────────────────


def srt_time_to_seconds(time_str: str) -> float:
  """SRT 타임코드 (HH:MM:SS,mmm) → 초 변환"""
  parts = time_str.replace(',', '.').split(':')
  hours = int(parts[0])
  minutes = int(parts[1])
  seconds = float(parts[2])
  return hours * 3600 + minutes * 60 + seconds


def parse_srt(srt_path: str) -> list[dict]:
  """SRT 파일 파싱 → [{"index": 1, "start": 0.0, "end": 9.119, "text": "..."}]"""
  subs = []
  try:
    with open(srt_path, 'r', encoding='utf-8') as f:
      content = f.read()

    # 빈 줄 기준 블록 분리
    blocks = content.strip().split('\n\n')
    for block in blocks:
      lines = block.strip().split('\n')
      if len(lines) < 3:
        continue

      try:
        index = int(lines[0])
        timecode = lines[1]
        text = '\n'.join(lines[2:])

        start_str, end_str = timecode.split(' --> ')
        start = srt_time_to_seconds(start_str)
        end = srt_time_to_seconds(end_str)

        subs.append({'index': index, 'start': start, 'end': end, 'text': text})
      except (ValueError, IndexError) as e:
        logger.warning('SRT 블록 파싱 오류: %s', e)
        continue

  except Exception as e:
    logger.error('SRT 파일 읽기 실패 (%s): %s', srt_path, e)
    return []

  logger.info('SRT 파싱 완료: %d개 자막', len(subs))
  return subs


# ─────────────── 자막 렌더링 (PIL) ────────────────────────────────────


def make_subtitle_clip(
  text: str, start_sec: float, end_sec: float
) -> ImageClip:
  """PIL로 한글 자막 이미지 생성 → ImageClip 반환"""
  # 이미지 크기 (자막 영역)
  img_width, img_height = 1080, 150

  # 투명 배경 이미지
  img = Image.new('RGBA', (img_width, img_height), (0, 0, 0, 0))
  draw = ImageDraw.Draw(img)

  # 폰트 로드
  try:
    font = ImageFont.truetype(str(FONT_PATH), size=42)
  except Exception:
    logger.warning('폰트 로드 실패 (%s), 기본 폰트 사용', FONT_PATH)
    font = ImageFont.load_default()

  # 텍스트 줄바꿈
  wrapped_text = '\n'.join(textwrap.wrap(text, width=25))

  # 텍스트 바운드박스 계산
  bbox = draw.textbbox((0, 0), wrapped_text, font=font)
  text_width = bbox[2] - bbox[0]
  text_height = bbox[3] - bbox[1]

  # 텍스트 위치 (중앙, 상단 20px)
  text_x = (img_width - text_width) // 2
  text_y = 20

  # 배경 박스 (반투명 검정)
  padding = 10
  box_coords = [
    text_x - padding,
    text_y - padding,
    text_x + text_width + padding,
    text_y + text_height + padding,
  ]
  draw.rectangle(box_coords, fill=(0, 0, 0, 160))

  # 텍스트 렌더링 (흰색)
  draw.text((text_x, text_y), wrapped_text, font=font, fill=(255, 255, 255, 255))

  # ImageClip 생성 및 타이밍 설정
  clip = ImageClip(np.array(img))
  clip = clip.set_duration(end_sec - start_sec)
  clip = clip.set_start(start_sec)
  clip = clip.set_pos(('center', 'bottom'))

  return clip


# ─────────────── 파일 수집 ─────────────────────────────────────────


def collect_image_files(image_dir: Path) -> list[Path]:
  """이미지 파일 수집 (씬 인덱스 순 정렬)"""
  img_files = []
  for f in image_dir.glob('*_*_image.png'):
    parts = f.stem.split('_')
    if len(parts) >= 2:
      try:
        scene_idx = int(parts[1])
        img_files.append((scene_idx, f))
      except ValueError:
        continue

  img_files.sort(key=lambda x: x[0])
  paths = [f for _, f in img_files]
  logger.info('이미지 파일 %d개 수집', len(paths))
  return paths


def collect_audio_files(audio_dir: Path) -> list[Path]:
  """오디오 파일 수집 (씬 인덱스 순 정렬)"""
  audio_files = []
  for f in audio_dir.glob('*_*_audio.mp3'):
    parts = f.stem.split('_')
    if len(parts) >= 2:
      try:
        scene_idx = int(parts[1])
        audio_files.append((scene_idx, f))
      except ValueError:
        continue

  audio_files.sort(key=lambda x: x[0])
  paths = [f for _, f in audio_files]
  logger.info('오디오 파일 %d개 수집', len(paths))
  return paths


def load_scene_durations(qa_report_path: Path) -> list[float]:
  """QA 리포트에서 scene_durations 추출"""
  try:
    with open(qa_report_path, 'r', encoding='utf-8') as f:
      data = json.load(f)

    # 우선순위 1: step4_parameters.scene_durations
    if 'step4_parameters' in data and 'scene_durations' in data['step4_parameters']:
      durations = data['step4_parameters']['scene_durations']
      logger.info('scene_durations 로드 완료: %d개 값', len(durations))
      return durations

    # 우선순위 2: scenes 순회해서 audio_duration 추출
    if 'scenes' in data:
      scenes = data['scenes']
      durations = []
      for key in sorted(scenes.keys(), key=lambda x: int(x) if x.isdigit() else 0):
        dur = scenes[key].get('audio_duration', 0.0)
        durations.append(dur)
      logger.info('audio_duration에서 추출: %d개 값', len(durations))
      return durations

  except Exception as e:
    logger.error('QA 리포트 로드 실패 (%s): %s', qa_report_path, e)

  return []


# ─────────────── 캐시 키 생성 ─────────────────────────────────────


def get_cache_path(
  image_paths: list[Path], audio_paths: list[Path], srt_path: Path
) -> Path:
  """캐시 경로 생성 (이미지 + 오디오 + SRT 경로 기반 MD5 해시)"""
  paths_key = '|'.join(
    [str(p.resolve()) for p in sorted(image_paths)]
    + [str(p.resolve()) for p in sorted(audio_paths)]
    + [str(srt_path.resolve())]
  )
  video_hash = hashlib.md5(paths_key.encode('utf-8')).hexdigest()[:8]
  return CACHE_DIR / f'{video_hash}_shorts.mp4'


# ─────────────── 영상 합성 ─────────────────────────────────────────


def compose_video(
  image_paths: list[Path],
  audio_paths: list[Path],
  srt_path: Path,
  scene_durations: list[float],
  output_path: Path,
) -> str:
  """이미지 + 오디오 + 자막 합성 → MP4 생성"""

  if not image_paths or not audio_paths:
    logger.error('이미지 또는 오디오 파일 없음')
    return ''

  if len(image_paths) != len(audio_paths):
    logger.warning(
      '이미지(%d)와 오디오(%d) 개수 불일치, 짧은 쪽 기준 사용',
      len(image_paths),
      len(audio_paths),
    )
    min_count = min(len(image_paths), len(audio_paths))
    image_paths = image_paths[:min_count]
    audio_paths = audio_paths[:min_count]
    scene_durations = scene_durations[:min_count]

  logger.info('영상 합성 시작: %d개 씬', len(image_paths))

  # 1. 이미지 클립 생성
  image_clips = []
  for idx, img_path in enumerate(image_paths):
    try:
      duration = scene_durations[idx] if idx < len(scene_durations) else 5.0
      clip = ImageClip(str(img_path))
      clip = clip.set_duration(duration)
      # 리사이즈: 512×912 → 1080×1920
      clip = clip.resize((TARGET_WIDTH, TARGET_HEIGHT))
      image_clips.append(clip)
      logger.info('씬 %d 로드 완료: %s (%.2f초)', idx + 1, img_path.name, duration)
    except Exception as e:
      logger.error('이미지 로드 실패 (%s): %s', img_path, e)
      return ''

  # 2. 오디오 클립 생성 및 연결
  audio_clips = []
  for idx, audio_path in enumerate(audio_paths):
    try:
      clip = AudioFileClip(str(audio_path))
      audio_clips.append(clip)
      logger.info('씬 %d 오디오 로드 완료: %s (%.2f초)', idx + 1, audio_path.name, clip.duration)
    except Exception as e:
      logger.error('오디오 로드 실패 (%s): %s', audio_path, e)
      return ''

  # 오디오 연결
  try:
    concat_audio = concatenate_audioclips(audio_clips)
    logger.info('오디오 합성: 총 %.2f초', concat_audio.duration)
  except Exception as e:
    logger.error('오디오 합성 실패: %s', e)
    return ''

  # 3. 이미지 영상 연결
  try:
    base_video = concatenate_videoclips(image_clips)
    logger.info('이미지 영상 합성: 총 %.2f초', base_video.duration)
  except Exception as e:
    logger.error('이미지 합성 실패: %s', e)
    return ''

  # 4. 오디오 결합
  try:
    base_video = base_video.set_audio(concat_audio)
    logger.info('오디오 트랙 설정 완료')
  except Exception as e:
    logger.error('오디오 설정 실패: %s', e)
    return ''

  # 5. SRT 자막 파싱 및 오버레이
  subtitle_clips = []
  try:
    subs = parse_srt(str(srt_path))
    for sub in subs:
      try:
        sub_clip = make_subtitle_clip(sub['text'], sub['start'], sub['end'])
        subtitle_clips.append(sub_clip)
      except Exception as e:
        logger.warning('자막 %d 렌더링 오류: %s', sub['index'], e)
        continue

    if subtitle_clips:
      logger.info('자막 오버레이: %d개', len(subtitle_clips))
      final_video = CompositeVideoClip([base_video] + subtitle_clips)
    else:
      logger.warning('자막 없음, 영상만 생성')
      final_video = base_video
  except Exception as e:
    logger.error('자막 처리 실패: %s', e)
    final_video = base_video

  # 6. 최종 영상 저장
  try:
    logger.info('영상 인코딩 시작: %s', output_path)
    final_video.write_videofile(
      str(output_path),
      fps=TARGET_FPS,
      codec='libx264',
      audio_codec='aac',
      verbose=False,
      logger=None,
    )
    logger.info('영상 저장 완료: %s (%d bytes)', output_path, output_path.stat().st_size)

    # 길이 검증
    final_duration = final_video.duration
    if final_duration > 60:
      logger.warning('영상 길이 초과: %.2f초 (60초 제한)', final_duration)

    return str(output_path.resolve())
  except Exception as e:
    logger.error('영상 저장 실패: %s', e)
    return ''


# ─────────────── --check 모드 ────────────────────────────────────


def cmd_check() -> None:
  """의존성 및 파일 상태 확인"""
  print('=== Step 5 환경 검증 ===\n')

  # 1. FFmpeg 확인
  try:
    import subprocess
    result = subprocess.run(
      ['ffmpeg', '-version'],
      capture_output=True,
      timeout=5,
      text=True,
    )
    if result.returncode == 0:
      version_line = result.stdout.split('\n')[0]
      print(f'[OK] FFmpeg: {version_line}')
    else:
      print('[FAIL] FFmpeg 명령 실패')
  except FileNotFoundError:
    print('[FAIL] FFmpeg 미발견 (C:/ffmpeg/bin/ffmpeg.exe 확인)')
  except Exception as e:
    print(f'[FAIL] FFmpeg 확인 실패: {e}')

  # 2. MoviePy 확인
  try:
    import moviepy
    print(f'[OK] MoviePy {moviepy.__version__} 임포트 성공')
  except ImportError as e:
    print(f'[FAIL] MoviePy 미설치: {e}')
    return

  # 3. Pillow 확인
  try:
    from PIL import Image, ImageDraw, ImageFont
    print('[OK] Pillow 임포트 성공')
  except ImportError as e:
    print(f'[FAIL] Pillow 미설치: {e}')
    return

  # 4. 폰트 확인
  if FONT_PATH.exists():
    print(f'[OK] 한글 폰트: {FONT_PATH}')
  else:
    print(f'[FAIL] 한글 폰트 미발견: {FONT_PATH}')

  # 5. 캐시 디렉터리 확인
  print(f'[OK] 캐시 디렉터리: {CACHE_DIR}')

  # 6. 입력 파일 확인
  image_dir = Path('cache/step2')
  audio_dir = Path('cache/step3')
  srt_path = Path('cache/step4') / '2287f371_subtitles.srt'
  qa_path = Path('cache/step4') / 'audio_visual_qa_report.json'

  if image_dir.exists():
    images = list(image_dir.glob('*_*_image.png'))
    print(f'[OK] 이미지: {len(images)}개 ({image_dir})')
  else:
    print(f'[FAIL] 이미지 디렉터리 없음: {image_dir}')

  if audio_dir.exists():
    audios = list(audio_dir.glob('*_*_audio.mp3'))
    print(f'[OK] 오디오: {len(audios)}개 ({audio_dir})')
  else:
    print(f'[FAIL] 오디오 디렉터리 없음: {audio_dir}')

  if srt_path.exists():
    print(f'[OK] SRT 자막: {srt_path.name}')
  else:
    print(f'[FAIL] SRT 자막 없음: {srt_path}')

  if qa_path.exists():
    print(f'[OK] QA 리포트: {qa_path.name}')
  else:
    print(f'[FAIL] QA 리포트 없음: {qa_path}')

  print('\n[OK] 환경 검증 완료')


# ─────────────── 캐시 정리 ────────────────────────────────────────


def cmd_clean_cache(force: bool = False) -> None:
  """중복 캐시 파일 정리"""
  mp4_files = list(CACHE_DIR.glob('*_shorts.mp4'))

  if not mp4_files:
    logger.info('정리할 MP4 파일 없음')
    return

  logger.info('MP4 캐시 파일 %d개 존재:', len(mp4_files))
  for f in mp4_files:
    logger.info('  - %s (%.2f MB)', f.name, f.stat().st_size / (1024 * 1024))

  if force:
    for f in mp4_files:
      f.unlink()
      logger.info('삭제 완료: %s', f.name)
    logger.info('캐시 정리 완료')
  else:
    logger.info('[DRY-RUN] 실제 삭제하려면 --clean-cache --force 사용')


# ─────────────── CLI ────────────────────────────────────────────


def main() -> None:
  """명령행 인터페이스"""
  parser = argparse.ArgumentParser(
    description='Step 5: MoviePy로 이미지 + 오디오 + 자막 합성 (최종 Shorts 영상)'
  )
  parser.add_argument(
    'nlp_cache',
    nargs='?',
    help='Step 1 NLP 캐시 JSON 파일 경로 (선택, 파일 자동 수집에만 사용)',
  )
  parser.add_argument(
    '--image-dir', type=str, default='cache/step2', help='이미지 디렉터리 (기본: cache/step2)'
  )
  parser.add_argument(
    '--audio-dir', type=str, default='cache/step3', help='오디오 디렉터리 (기본: cache/step3)'
  )
  parser.add_argument(
    '--subtitle-path',
    type=str,
    help='SRT 자막 경로 (기본: cache/step4/첫 SRT 파일)',
  )
  parser.add_argument(
    '--qa-report',
    type=str,
    default='cache/step4/audio_visual_qa_report.json',
    help='QA 리포트 JSON 경로',
  )
  parser.add_argument('--no-cache', action='store_true', help='캐시 무시하고 재생성')
  parser.add_argument('--check', action='store_true', help='환경 검증')
  parser.add_argument('--clean-cache', action='store_true', help='캐시 파일 목록 출력')
  parser.add_argument('--force', action='store_true', help='--clean-cache와 함께 삭제 실행')

  args = parser.parse_args()

  if args.check:
    cmd_check()
    return

  if args.clean_cache:
    cmd_clean_cache(force=args.force)
    return

  # 파일 수집
  image_dir = Path(args.image_dir)
  audio_dir = Path(args.audio_dir)

  if not image_dir.is_dir():
    logger.error('이미지 디렉터리 없음: %s', image_dir)
    sys.exit(1)

  if not audio_dir.is_dir():
    logger.error('오디오 디렉터리 없음: %s', audio_dir)
    sys.exit(1)

  image_paths = collect_image_files(image_dir)
  audio_paths = collect_audio_files(audio_dir)

  if not image_paths or not audio_paths:
    logger.error('이미지 또는 오디오 파일 없음')
    sys.exit(1)

  # SRT 경로 결정
  if args.subtitle_path:
    srt_path = Path(args.subtitle_path)
  else:
    srt_files = list(Path('cache/step4').glob('*_subtitles.srt'))
    if srt_files:
      srt_path = srt_files[0]
    else:
      logger.error('SRT 파일을 찾을 수 없음')
      sys.exit(1)

  if not srt_path.exists():
    logger.error('SRT 파일 없음: %s', srt_path)
    sys.exit(1)

  # QA 리포트 로드
  qa_report_path = Path(args.qa_report)
  if not qa_report_path.exists():
    logger.error('QA 리포트 없음: %s', qa_report_path)
    sys.exit(1)

  scene_durations = load_scene_durations(qa_report_path)
  if not scene_durations:
    logger.error('scene_durations를 로드할 수 없음')
    sys.exit(1)

  # 캐시 확인
  output_path = get_cache_path(image_paths, audio_paths, srt_path)

  if not args.no_cache and output_path.exists():
    logger.info('영상 캐시 사용: %s', output_path)
    print(f'영상 파일: {str(output_path.resolve())}')
    return

  # 영상 합성
  video_path = compose_video(image_paths, audio_paths, srt_path, scene_durations, output_path)
  if video_path:
    print(f'영상 파일: {video_path}')
  else:
    sys.exit(1)


if __name__ == '__main__':
  main()
