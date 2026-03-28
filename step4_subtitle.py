"""
Step 4: Subtitle — Step 3 오디오 기반 SRT 자막 생성

입력: modern_script_data (list[dict]) + audio_paths (list[str])
출력: subtitle_path (str)

## 사용법
  uv run python step4_subtitle.py cache/step1/xxx_nlp.json --audio-dir cache/step3
  uv run python step4_subtitle.py cache/step1/xxx_nlp.json cache/step3/hash_00_audio.mp3 cache/step3/hash_01_audio.mp3 ...
  uv run python step4_subtitle.py --clean-cache [--force]
"""

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path
from typing import Any

# 로거 설정
logger = logging.getLogger(__name__)
logging.basicConfig(
  level=logging.INFO,
  format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)

# 상수
CACHE_DIR = Path('cache/step4')
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────── 자막 생성 ────────────────────────────────────────────


def seconds_to_srt_time(seconds: float) -> str:
  """초(float)를 SRT 타임코드 형식(HH:MM:SS,mmm)으로 변환"""
  h = int(seconds // 3600)
  m = int((seconds % 3600) // 60)
  s = int(seconds % 60)
  ms = int((seconds % 1) * 1000)
  return f'{h:02d}:{m:02d}:{s:02d},{ms:03d}'


def get_audio_duration(path: str) -> float:
  """MP3 재생 길이(초) 반환. 실패 시 0.0"""
  try:
    from mutagen.mp3 import MP3

    audio = MP3(path)
    return audio.info.length
  except ImportError:
    logger.warning('mutagen 라이브러리 미설치, 오디오 길이 조회 불가')
    return 0.0
  except Exception as e:
    logger.warning('오디오 길이 조회 실패 (%s): %s', path, e)
    return 0.0


def generate_subtitles(
  audio_paths: list[str],
  script_data: list[dict],
  output_path: Path,
) -> str:
  """오디오 길이 기반으로 SRT 자막 파일 생성 → 경로 반환"""
  blocks: list[str] = []
  current_time = 0.0

  for idx, (path, scene) in enumerate(zip(audio_paths, script_data)):
    narration: str = scene.get('narration', '')
    if not path or not narration.strip():
      continue

    duration = get_audio_duration(path)
    end_time = current_time + duration

    start_str = seconds_to_srt_time(current_time)
    end_str = seconds_to_srt_time(end_time)
    block = f'{idx + 1}\n{start_str} --> {end_str}\n{narration}\n'
    blocks.append(block)

    current_time = end_time

  srt_content = '\n'.join(blocks)
  output_path.write_text(srt_content, encoding='utf-8')
  logger.info('자막 파일 생성 완료: %s (%d개 블록)', output_path, len(blocks))
  return str(output_path.resolve())


# ─────────────── 캐시 정리 ─────────────────────────────────────────────


def cmd_clean_cache(force: bool = False) -> None:
  """중복 캐시 파일 정리 (모든 subtitles.srt 유지)"""
  srt_files = list(CACHE_DIR.glob('*_subtitles.srt'))

  if not srt_files:
    logger.info('정리할 파일 없음')
    return

  logger.info('SRT 캐시 파일 %d개 존재:', len(srt_files))
  for f in srt_files:
    logger.info('  - %s (%d bytes)', f, f.stat().st_size)


# ─────────────── CLI ───────────────────────────────────────────────


def main() -> None:
  """명령행 인터페이스"""
  parser = argparse.ArgumentParser(
    description='Step 4: Step 3 오디오 기반 SRT 자막 생성'
  )
  parser.add_argument(
    'nlp_cache',
    nargs='?',
    help='Step 1 NLP 캐시 JSON 파일 경로 (예: cache/step1/xxx_nlp.json)',
  )
  parser.add_argument(
    'audio_files',
    nargs='*',
    help='Step 3 MP3 파일 경로 목록 (지정 안 하면 --audio-dir 사용)',
  )
  parser.add_argument(
    '--audio-dir',
    type=str,
    help='Step 3 오디오 파일 디렉터리 (자동 수집)',
  )
  parser.add_argument(
    '--clean-cache', action='store_true', help='캐시 파일 목록 출력'
  )
  parser.add_argument(
    '--force', action='store_true', help='--clean-cache와 함께 사용 시 실제 삭제'
  )
  parser.add_argument(
    '--no-cache', action='store_true', help='캐시 무시하고 재생성'
  )

  args = parser.parse_args()

  if args.clean_cache:
    cmd_clean_cache(force=args.force)
    return

  if not args.nlp_cache:
    parser.print_help()
    sys.exit(1)

  # JSON 파일 로드
  try:
    with open(args.nlp_cache, 'r', encoding='utf-8') as f:
      data: dict[str, Any] = json.load(f)
    script_data: list[dict] = data.get('modern_script_data', [])
    if not script_data:
      logger.error('modern_script_data 키 없음: %s', args.nlp_cache)
      sys.exit(1)
  except FileNotFoundError:
    logger.error('파일 없음: %s', args.nlp_cache)
    sys.exit(1)
  except json.JSONDecodeError as e:
    logger.error('JSON 파싱 오류 (%s): %s', args.nlp_cache, e)
    sys.exit(1)

  # 오디오 파일 경로 수집
  audio_paths: list[str] = []

  if args.audio_dir:
    # --audio-dir 방식: 디렉터리 내 *.mp3 자동 수집 (씬 인덱스 순서)
    audio_dir = Path(args.audio_dir)
    if not audio_dir.is_dir():
      logger.error('디렉터리 없음: %s', audio_dir)
      sys.exit(1)

    # 파일명 패턴: {hash8}_{idx:02d}_audio.mp3 → 씬 인덱스(idx) 기준 정렬
    mp3_files = []
    for f in audio_dir.glob('*_*_audio.mp3'):
      # 파일명에서 씬 인덱스 추출 (e.g., "67bb43b5_00_audio.mp3" → 00)
      parts = f.stem.split('_')
      if len(parts) >= 2:
        scene_idx = int(parts[1])
        mp3_files.append((scene_idx, f))

    # 씬 인덱스 순서로 정렬
    mp3_files.sort(key=lambda x: x[0])
    for _, f in mp3_files:
      audio_paths.append(str(f.resolve()))
    logger.info('오디오 파일 %d개 수집 (--audio-dir)', len(audio_paths))

  elif args.audio_files:
    # 명시적 파일 목록
    for f in args.audio_files:
      audio_paths.append(str(Path(f).resolve()))
    logger.info('오디오 파일 %d개 수집 (명시적)', len(audio_paths))

  else:
    logger.error('오디오 파일 경로 필요: --audio-dir 또는 파일 목록')
    sys.exit(1)

  # 캐시 키 생성
  paths_key = '|'.join(sorted(p for p in audio_paths if p))
  subtitle_hash = hashlib.md5(paths_key.encode('utf-8')).hexdigest()[:8]
  output_path = CACHE_DIR / f'{subtitle_hash}_subtitles.srt'

  # 캐시 확인
  if not args.no_cache and output_path.exists():
    logger.info('자막 캐시 사용: %s', output_path)
    print(f'자막 파일: {str(output_path.resolve())}')
    return

  # 자막 생성
  subtitle_path = generate_subtitles(audio_paths, script_data, output_path)
  print(f'자막 파일: {subtitle_path}')


if __name__ == '__main__':
  main()
