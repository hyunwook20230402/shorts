"""
Step 2: ElevenLabs TTS로 음성 생성 및 타임스탬프(alignment) 추출
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

# .env 파일 명시적 로드
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

logger = logging.getLogger(__name__)

# ElevenLabs 환경변수
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')
ELEVENLABS_VOICE_ID_MALE = os.getenv('ELEVENLABS_VOICE_ID1', 'XZpuKnMGlnvwMXKjjtQP')
ELEVENLABS_VOICE_ID_FEMALE = os.getenv('ELEVENLABS_VOICE_ID2', 'GFjnEFNRrDZ9sqkhR3a9')
ELEVENLABS_API_URL = 'https://api.elevenlabs.io/v1'
MAX_RETRIES = 3


def get_voice_id(gender: str = 'female') -> str:
  """성별로 음성 ID 반환 (male/female)"""
  if gender == 'male':
    return ELEVENLABS_VOICE_ID_MALE
  return ELEVENLABS_VOICE_ID_FEMALE


def get_cache_path(poem_dir: Path, idx: int, suffix: str) -> Path:
  """캐시 경로 생성 (poem_id 기반, 씬 단위)"""
  return poem_dir / 'step2' / f'scene{idx:02d}{suffix}'


def get_sentence_audio_path(poem_dir: Path, scene_idx: int, sent_idx: int) -> Path:
  """문장 단위 MP3 경로 생성"""
  return poem_dir / 'step2' / f'scene{scene_idx:02d}_sent{sent_idx:02d}_audio.mp3'


def get_sentence_alignment_path(poem_dir: Path, scene_idx: int, sent_idx: int) -> Path:
  """문장 단위 alignment JSON 경로 생성"""
  return poem_dir / 'step2' / f'scene{scene_idx:02d}_sent{sent_idx:02d}_alignment.json'


def load_alignment_from_cache(alignment_path: Path) -> Optional[dict]:
  """alignment JSON 로드"""
  if not alignment_path.exists():
    return None
  try:
    with open(alignment_path, 'r', encoding='utf-8') as f:
      return json.load(f)
  except Exception as e:
    logger.warning(f'alignment 캐시 로드 실패: {alignment_path}, {e}')
    return None


def save_alignment_to_cache(alignment_path: Path, alignment_data: dict) -> None:
  """alignment JSON 저장 (step2/ 폴더 자동 생성)"""
  alignment_path.parent.mkdir(parents=True, exist_ok=True)
  with open(alignment_path, 'w', encoding='utf-8') as f:
    json.dump(alignment_data, f, indent=2, ensure_ascii=False)
  logger.info(f'alignment 저장: {alignment_path}')


def call_elevenlabs_api(text: str, voice_id: str) -> bytes:
  """
  ElevenLabs TTS API 호출 (3회 재시도 + 지수 백오프)
  반환: MP3 audio bytes
  """
  if not ELEVENLABS_API_KEY:
    raise ValueError('ELEVENLABS_API_KEY 환경변수가 설정되지 않았습니다')

  url = f'{ELEVENLABS_API_URL}/text-to-speech/{voice_id}'
  headers = {
    'xi-api-key': ELEVENLABS_API_KEY,
    'Content-Type': 'application/json',
  }
  body = {
    'text': text,
    'model_id': 'eleven_multilingual_v2',
    'voice_settings': {
      'stability': 0.5,
      'similarity_boost': 0.75,
    },
  }

  for attempt in range(MAX_RETRIES):
    try:
      response = requests.post(url, json=body, headers=headers, timeout=30)

      if response.status_code == 200:
        return response.content

      if response.status_code == 401:
        logger.error('ElevenLabs API 인증 실패 (유효하지 않은 API 키)')
        raise ValueError('ELEVENLABS_API_KEY가 유효하지 않습니다')

      if response.status_code == 429:
        logger.warning(f'ElevenLabs 비율 제한, 재시도 {attempt + 1}/{MAX_RETRIES}')
        if attempt < MAX_RETRIES - 1:
          time.sleep(2 ** attempt)
          continue
        raise RuntimeError('ElevenLabs API 비율 제한 초과')

      logger.error(f'ElevenLabs API 오류: {response.status_code} {response.text[:200]}')
      if attempt < MAX_RETRIES - 1:
        time.sleep(2 ** attempt)
        continue
      raise RuntimeError(f'ElevenLabs API 오류: {response.status_code}')

    except requests.RequestException as e:
      logger.error(f'ElevenLabs API 호출 실패: {e}, 재시도 {attempt + 1}/{MAX_RETRIES}')
      if attempt < MAX_RETRIES - 1:
        time.sleep(2 ** attempt)
        continue
      raise

  raise RuntimeError('ElevenLabs API 호출 최대 재시도 횟수 초과')


def get_audio_duration_from_mp3(mp3_path: Path) -> float:
  """MP3 파일의 실제 재생 길이(초) 측정"""
  # 시도 1: mutagen
  try:
    from mutagen.mp3 import MP3
    audio_file = MP3(str(mp3_path))
    duration = audio_file.info.length
    logger.info(f'mutagen으로 MP3 길이 측정: {duration:.2f}초')
    return duration
  except Exception:
    pass

  # 시도 2: moviepy
  try:
    from moviepy.audio.io.AudioFileClip import AudioFileClip
    clip = AudioFileClip(str(mp3_path))
    duration = clip.duration
    clip.close()
    logger.info(f'moviepy로 MP3 길이 측정: {duration:.2f}초')
    return duration
  except Exception:
    pass

  logger.warning('MP3 길이 측정 실패, fallback 사용')
  return max(1.0, 1.0)


def estimate_alignment_from_audio(audio_path: str, text: str) -> dict:
  """
  오디오 파일 길이 기반 alignment 추정 (word/sentence 레벨)
  ElevenLabs Free 버전은 with-timestamps 미지원이므로 균등 분배
  """
  import re

  total_duration = None

  # mutagen으로 측정
  try:
    from mutagen.mp3 import MP3
    audio_file = MP3(audio_path)
    total_duration = audio_file.info.length
    logger.info(f'mutagen으로 MP3 길이 측정: {total_duration:.2f}초')
  except Exception:
    pass

  # moviepy fallback
  if total_duration is None:
    try:
      from moviepy.audio.io.AudioFileClip import AudioFileClip
      audio_clip = AudioFileClip(audio_path)
      total_duration = audio_clip.duration
      audio_clip.close()
      logger.info(f'moviepy로 MP3 길이 측정: {total_duration:.2f}초')
    except Exception:
      pass

  # 최후 fallback
  if total_duration is None:
    logger.warning('모든 오디오 길이 측정 방법 실패, 텍스트 길이로 추정')
    total_duration = max(2.0, len(text) * 0.1)

  # 단어 분리
  words = text.split()
  word_duration = total_duration / max(len(words), 1)

  # 문장 분리
  sentences_raw = re.split(r'[.!?。!？]+', text)
  sentences = [s.strip() for s in sentences_raw if s.strip()]

  # word-level alignment
  word_times = []
  current_time = 0.0
  for word in words:
    word_times.append({
      'word': word,
      'start': current_time,
      'end': current_time + word_duration,
    })
    current_time += word_duration

  # sentence-level alignment
  sentence_times = []
  sent_duration = total_duration / max(len(sentences), 1)
  current_time = 0.0
  for sent in sentences:
    sentence_times.append({
      'text': sent,
      'start': current_time,
      'end': current_time + sent_duration,
    })
    current_time += sent_duration

  return {
    'total_duration': total_duration,
    'words': word_times,
    'sentences': sentence_times,
  }


def clean_tts_text(text: str) -> str:
  """TTS 전달 전 한자 병기·주석 마커·구두점 제거"""
  import re
  # 1단계: 한자 병기 제거 — 정(情) → 정, 고침상(孤枕上) → 고침상
  cleaned = re.sub(r'\([一-龥\u4e00-\u9fff\u3400-\u4dbf]+\)', '', text)
  # 2단계: 주석 마커 제거 — 벼기더시니* → 벼기더시니
  cleaned = re.sub(r'\*', '', cleaned)
  # 3단계: 나머지 구두점 제거
  cleaned = re.sub(
    r'[.,，。、·~～!！?？;；:："""\'\'()\[\]{}'
    r'…—–\-/\\@#%&|「」『』【】〔〕〈〉《》]',
    ' ', cleaned
  )
  cleaned = re.sub(r'\s+', ' ', cleaned).strip()
  return cleaned


def generate_sentence_audio_sync(
  sentence_text: str,
  scene_idx: int,
  sent_idx: int,
  poem_dir: Path,
  voice_id: str | None = None,
  use_cache: bool = True,
) -> tuple[Path, Path]:
  """
  문장 단위 ElevenLabs TTS 생성 (동기)
  반환: (mp3_path, alignment_path)
  """
  mp3_path = get_sentence_audio_path(poem_dir, scene_idx, sent_idx)
  alignment_path = get_sentence_alignment_path(poem_dir, scene_idx, sent_idx)

  if use_cache and mp3_path.exists() and alignment_path.exists():
    logger.info(f'캐시된 문장 오디오 사용: {mp3_path}')
    return mp3_path, alignment_path

  cleaned = clean_tts_text(sentence_text)
  if cleaned != sentence_text:
    logger.debug(f'TTS 텍스트 정제: "{sentence_text}" → "{cleaned}"')
  if not cleaned:
    logger.warning(f'Scene {scene_idx} Sent {sent_idx}: 구두점 제거 후 텍스트 없음, 원본 사용')
    cleaned = sentence_text

  if voice_id is None:
    voice_id = get_voice_id('female')
  logger.info(f'ElevenLabs TTS 생성: Scene {scene_idx}, Sent {sent_idx}')
  audio_bytes = call_elevenlabs_api(cleaned, voice_id)

  mp3_path.parent.mkdir(parents=True, exist_ok=True)
  mp3_path.write_bytes(audio_bytes)
  logger.info(f'문장 MP3 저장: {mp3_path} ({len(audio_bytes)} bytes)')

  # 실제 MP3 길이 측정
  duration = get_audio_duration_from_mp3(mp3_path)

  alignment = {
    'scene_index': scene_idx,
    'sent_index': sent_idx,
    'text': sentence_text,
    'duration': duration,
    'audio_path': str(mp3_path),
  }
  alignment_path.write_text(
    json.dumps(alignment, ensure_ascii=False, indent=2), encoding='utf-8'
  )
  logger.info(f'문장 alignment 저장: {alignment_path} ({duration:.2f}s)')

  return mp3_path, alignment_path


async def generate_all_audio(
  script_data: list[dict],
  poem_dir: Path,
  use_cache: bool = True,
  gender: str = 'female',
) -> tuple[list[list[str]], list[list[str]]]:
  """
  모든 씬의 모든 문장에 대해 ElevenLabs TTS 생성
  (async 시그니처 유지 — pipeline_runner 호환)

  Args:
    gender: 'male' 또는 'female' (기본값: female)
  """
  voice_id = get_voice_id(gender)
  logger.info(f'ElevenLabs TTS 시작: gender={gender}, voice_id={voice_id}, {len(script_data)}개 씬')

  sentence_audio_paths = []
  sentence_alignment_paths = []

  for scene_idx, scene in enumerate(script_data):
    sentence_text = scene.get('original_text', '').strip()

    if not sentence_text:
      logger.warning(f'Scene {scene_idx}: original_text가 비어있습니다')
      sentence_audio_paths.append([])
      sentence_alignment_paths.append([])
      continue

    try:
      mp3_path, align_path = generate_sentence_audio_sync(
        sentence_text, scene_idx, 0, poem_dir,
        voice_id=voice_id,
        use_cache=use_cache,
      )
      sentence_audio_paths.append([str(mp3_path)])
      sentence_alignment_paths.append([str(align_path)])
    except Exception as e:
      logger.error(f'Scene {scene_idx} 오디오 생성 실패: {e}')
      raise

  logger.info(f'전체 문장 오디오 생성 완료: {sum(len(s) for s in sentence_audio_paths)}개 문장')
  return sentence_audio_paths, sentence_alignment_paths


def cmd_check() -> bool:
  """ElevenLabs API 연결 확인"""
  if not ELEVENLABS_API_KEY:
    logger.error('ELEVENLABS_API_KEY 환경변수가 설정되지 않았습니다')
    return False

  try:
    test_voice_id = get_voice_id('female')
    url = f'{ELEVENLABS_API_URL}/text-to-speech/{test_voice_id}'
    headers = {
      'xi-api-key': ELEVENLABS_API_KEY,
      'Content-Type': 'application/json',
    }
    body = {
      'text': '테스트',
      'model_id': 'eleven_multilingual_v2',
      'voice_settings': {
        'stability': 0.5,
        'similarity_boost': 0.75,
      },
    }
    response = requests.post(url, json=body, headers=headers, timeout=10)
    if response.status_code == 200:
      logger.info(f'ElevenLabs API 연결 성공 (voice: {test_voice_id})')
      return True
    logger.error(f'ElevenLabs API 오류: {response.status_code} - {response.text[:100]}')
    return False
  except Exception as e:
    logger.error(f'ElevenLabs API 연결 실패: {e}')
    return False


if __name__ == '__main__':
  logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
      logging.FileHandler('step2_tts.log', encoding='utf-8'),
      logging.StreamHandler(),
    ],
  )

  logger.info('=' * 70)
  logger.info('Step 2: ElevenLabs TTS')
  logger.info('=' * 70)

  # 1. ElevenLabs 연결 확인
  if not cmd_check():
    logger.error('ElevenLabs API 연결 실패')
    exit(1)

  # 2. poem_dir + --voice 인자 처리
  import argparse
  parser = argparse.ArgumentParser(description='Step 2: ElevenLabs TTS')
  parser.add_argument('poem_dir', help='poem_dir 경로')
  parser.add_argument('--voice', choices=['male', 'female'], default='female',
                      help='음성 성별 (기본: female)')
  args = parser.parse_args()

  poem_dir = Path(args.poem_dir)
  voice_gender = args.voice
  nlp_path = poem_dir / 'step1' / 'nlp.json'

  if not nlp_path.exists():
    logger.error(f'Step 1 NLP 캐시 없음: {nlp_path}')
    exit(1)

  with open(nlp_path, 'r', encoding='utf-8') as f:
    nlp_data = json.load(f)

  script_data = nlp_data.get('modern_script_data', [])

  if not script_data:
    logger.error(f"modern_script_data 없음. JSON 키 목록: {list(nlp_data.keys())}")
    exit(1)

  logger.info(f'nlp_data 로드 성공: {len(script_data)}개 씬 발견')

  # 3. Step 2 실행
  try:
    logger.info('TTS 생성 실행 중...')

    import asyncio
    audio_paths, alignment_paths = asyncio.run(generate_all_audio(
      script_data=script_data, poem_dir=poem_dir, use_cache=True,
      gender=voice_gender,
    ))

    total_sentences = sum(len(scene_audios) for scene_audios in audio_paths)
    logger.info(f'TTS 생성 완료: {total_sentences}개 문장')
    for scene_idx, (scene_audios, scene_alignments) in enumerate(zip(audio_paths, alignment_paths)):
      logger.info(f'Scene {scene_idx}:')
      for sent_idx, (audio, alignment) in enumerate(zip(scene_audios, scene_alignments)):
        logger.info(f'  문장 {sent_idx}: {Path(audio).name}')
        logger.info(f'    Alignment: {Path(alignment).name}')

    logger.info('=' * 70)
    logger.info('Step 2 완료')
    logger.info('=' * 70)
    exit(0)

  except Exception as e:
    logger.error(f'Step 2 실패: {e}', exc_info=True)
    exit(1)
