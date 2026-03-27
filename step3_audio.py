"""
Step 3: Audio — Edge-TTS로 나레이션 오디오 생성

입력: modern_script_data (list[dict])
출력: generated_audio_paths (list[str])

## 사용법
  uv run python step3_audio.py --check
  uv run python step3_audio.py cache/step1/xxx_nlp.json
  uv run python step3_audio.py cache/step1/xxx_nlp.json --scene 1
  uv run python step3_audio.py cache/step1/xxx_nlp.json --no-cache

## .env 필수 항목
  TTS_VOICE=ko-KR-SunHiNeural  # 기본값, 선택 가능: ko-KR-InJoonNeural
"""

import asyncio
import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import edge_tts
from tenacity import (
  retry,
  stop_after_attempt,
  wait_exponential,
)

# 로거 설정
logger = logging.getLogger(__name__)
logging.basicConfig(
  level=logging.INFO,
  format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)

# 상수
CACHE_DIR = Path('cache/step3')
CACHE_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_VOICE = 'ko-KR-SunHiNeural'
TTS_VOICE: str = os.environ.get('TTS_VOICE', DEFAULT_VOICE)

# Windows 환경에서 asyncio 이벤트 루프 정책 설정
if sys.platform == 'win32':
  asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


# ─────────────── 캐시 유틸 ───────────────────────────────────────────


def get_cache_path(text: str, idx: int) -> Path:
  """나레이션 텍스트와 씬 인덱스로 캐시 경로 생성"""
  text_hash = str(abs(hash(text)))[-8:]
  return CACHE_DIR / f'{text_hash}_{idx:02d}_audio.mp3'


# ─────────────── edge-tts 핵심 호출 ───────────────────────────────────


@retry(
  stop=stop_after_attempt(3),
  wait=wait_exponential(min=2, max=10),
  reraise=True,
)
async def generate_audio_async(
  text: str,
  voice: str,
  output_path: Path,
) -> None:
  """edge-tts API 호출 (최대 3회 retry)"""
  communicate = edge_tts.Communicate(text=text, voice=voice)
  await communicate.save(str(output_path))
  logger.info('오디오 저장 완료: %s', output_path)


# ─────────────── 단일 씬 처리 ─────────────────────────────────────────


async def generate_audio(
  text: str,
  idx: int,
  voice: str = TTS_VOICE,
  use_cache: bool = True,
) -> str:
  """씬 1개 나레이션 오디오 생성 → 로컬 캐시 경로 반환"""
  cache_path = get_cache_path(text, idx)

  if use_cache and cache_path.exists():
    logger.info('캐시 사용: %s', cache_path)
    return str(cache_path.resolve())

  logger.info('씬 %d 오디오 생성 중... (voice: %s)', idx + 1, voice)
  try:
    await generate_audio_async(text, voice, cache_path)

    # 캐시 무결성 확인
    file_size = cache_path.stat().st_size
    if file_size < 100:
      cache_path.unlink()
      raise RuntimeError(
        f'생성된 오디오 파일이 너무 작습니다: {cache_path} ({file_size} bytes)'
      )

    logger.info('씬 %d 저장 완료: %s (%d bytes)', idx + 1, cache_path, file_size)
    return str(cache_path.resolve())

  except Exception as e:
    logger.error('씬 %d 오디오 생성 실패: %s', idx + 1, e)
    return ''


# ─────────────── 오디오 길이 조회 ──────────────────────────────────────


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


# ─────────────── 배치 처리 ─────────────────────────────────────────────


def generate_all_audio(
  script_data: list[dict],
  use_cache: bool = True,
) -> list[str]:
  """Step 3 메인 함수: 전체 씬 나레이션 오디오 생성"""
  logger.info('오디오 생성 시작 (총 %d씬)', len(script_data))

  async def _run_all() -> list[str]:
    paths: list[str] = []
    for idx, scene in enumerate(script_data):
      narration: str = scene.get('narration', '')
      if not narration.strip():
        logger.warning('씬 %d narration 없음, 건너뜀', idx + 1)
        paths.append('')
        continue
      path = await generate_audio(
        narration, idx, voice=TTS_VOICE, use_cache=use_cache
      )
      paths.append(path)
    return paths

  # 이벤트 루프 충돌 방지 (Jupyter/Streamlit 환경 대응)
  try:
    loop = asyncio.get_running_loop()
  except RuntimeError:
    loop = None

  if loop and loop.is_running():
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor() as pool:
      future = pool.submit(asyncio.run, _run_all())
      paths = future.result()
  else:
    paths = asyncio.run(_run_all())

  # 실패 씬 보고
  failed = [(i, p) for i, p in enumerate(paths) if not p]
  if failed:
    logger.warning('오디오 생성 실패 씬: %s', [i + 1 for i, _ in failed])

  logger.info('전체 오디오 생성 완료 (%d개)', len(paths))
  return paths


# ─────────────── --check 모드 ─────────────────────────────────────────


def cmd_check() -> None:
  """edge-tts 설치 및 음성 목록 확인"""
  print(f'TTS 음성: {TTS_VOICE}')

  # 단계 1: edge-tts 설치 여부 확인
  try:
    import edge_tts as _  # noqa: F401

    print('[OK] edge-tts 임포트 성공')
  except ImportError as e:
    print(f'[FAIL] edge-tts 미설치: {e}')
    return

  # 단계 2: 음성 목록 확인
  async def _check_voice() -> None:
    voices = await edge_tts.list_voices()
    ko_voices = [v for v in voices if v['Locale'].startswith('ko-')]
    print(f'[INFO] 한국어 음성 수: {len(ko_voices)}개')
    names = [v['ShortName'] for v in ko_voices]
    if TTS_VOICE in names:
      print(f'[OK] 음성 확인: {TTS_VOICE}')
    else:
      print(f'[WARN] 음성 미발견: {TTS_VOICE}')
      print(f'       사용 가능한 한국어 음성: {names}')

  # 단계 3: 실제 TTS 생성 테스트
  async def _test_generate() -> None:
    test_path = CACHE_DIR / '_check_test.mp3'
    communicate = edge_tts.Communicate(
      text='안녕하세요. 테스트입니다.', voice=TTS_VOICE
    )
    await communicate.save(str(test_path))
    size = test_path.stat().st_size
    test_path.unlink()  # 테스트 파일 즉시 삭제
    print(f'[OK] TTS 생성 테스트 성공 ({size:,} bytes)')

  try:
    asyncio.run(_check_voice())
    asyncio.run(_test_generate())
  except Exception as e:
    print(f'[FAIL] TTS 테스트 실패: {e}')


# ─────────────── CLI ───────────────────────────────────────────────────


def main() -> None:
  """명령행 인터페이스"""
  parser = argparse.ArgumentParser(
    description='Step 3: Edge-TTS로 나레이션 오디오 생성'
  )
  parser.add_argument(
    'nlp_cache',
    nargs='?',
    help='Step 1 NLP 캐시 JSON 파일 경로 (예: cache/step1/xxx_nlp.json)',
  )
  parser.add_argument(
    '--check', action='store_true', help='edge-tts 설치 및 음성 테스트'
  )
  parser.add_argument(
    '--scene', type=int, default=0, help='특정 씬만 생성 (0-based 인덱스)'
  )
  parser.add_argument(
    '--no-cache', action='store_true', help='캐시 무시하고 재생성'
  )

  args = parser.parse_args()

  if args.check:
    cmd_check()
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

  # 특정 씬만 생성
  if args.scene > 0 and args.scene <= len(script_data):
    scene = script_data[args.scene - 1]
    narration = scene.get('narration', '')
    if narration.strip():
      asyncio.run(
        generate_audio(narration, args.scene - 1, use_cache=not args.no_cache)
      )
    else:
      logger.warning('씬 %d narration 없음', args.scene)
    return

  # 전체 씬 생성
  paths = generate_all_audio(script_data, use_cache=not args.no_cache)
  for idx, path in enumerate(paths):
    if path:
      duration = get_audio_duration(path)
      print(f'씬 {idx + 1}: {path} ({duration:.2f}초)')
    else:
      print(f'씬 {idx + 1}: [실패]')


if __name__ == '__main__':
  main()
