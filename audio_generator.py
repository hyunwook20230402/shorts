"""
Step 2: ElevenLabs TTS로 음성 생성 및 타임스탬프(alignment) 추출
"""

import os
import json
import logging
import hashlib
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
import requests

load_dotenv()

logger = logging.getLogger(__name__)

# 환경변수
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY', '')
ELEVENLABS_VOICE_ID = os.getenv('ELEVENLABS_VOICE_ID', 'onwK4e9ZDvw9KNAVq4mQ')  # 기본값
ELEVENLABS_API_URL = 'https://api.elevenlabs.io/v1'
CACHE_DIR = Path('cache/step2')
MAX_RETRIES = 3


def get_cache_path(text: str, idx: int, suffix: str) -> Path:
  """캐시 경로 생성 (MD5 기반)"""
  cache_key = hashlib.md5(text.encode()).hexdigest()[:8]
  CACHE_DIR.mkdir(parents=True, exist_ok=True)
  return CACHE_DIR / f'{cache_key}_{idx:02d}{suffix}'


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
  """alignment JSON 저장"""
  alignment_path.parent.mkdir(parents=True, exist_ok=True)
  with open(alignment_path, 'w', encoding='utf-8') as f:
    json.dump(alignment_data, f, indent=2, ensure_ascii=False)
  logger.info(f'alignment 저장: {alignment_path}')


def group_alignment_into_words(character_times: list[dict]) -> list[dict]:
  """
  character 레벨 타임스탬프 → word 레벨 그룹핑
  공백 기준으로 단어 분리
  """
  words = []
  current_word = ''
  word_start = None

  for char_data in character_times:
    char = char_data.get('char', '')
    start_ms = char_data.get('start_time_ms', 0)
    end_ms = char_data.get('end_time_ms', 0)

    if char == ' ':
      if current_word:
        words.append({
          'word': current_word,
          'start': word_start / 1000,  # ms → seconds
          'end': end_ms / 1000
        })
        current_word = ''
        word_start = None
    else:
      if word_start is None:
        word_start = start_ms
      current_word += char

  # 마지막 단어 처리
  if current_word:
    words.append({
      'word': current_word,
      'start': word_start / 1000 if word_start else 0,
      'end': character_times[-1].get('end_time_ms', 0) / 1000 if character_times else 0
    })

  return words


def group_alignment_into_sentences(words: list[dict], text: str) -> list[dict]:
  """
  word 레벨 타임스탬프 → sentence 레벨 그룹핑
  마침표/느낌표/쉼표 기준으로 분리
  """
  sentences = []
  current_text = ''
  sentence_start = None
  word_idx = 0

  for char in text:
    if sentence_start is None and word_idx < len(words):
      sentence_start = words[word_idx]['start']

    current_text += char

    if char in '。!？！?':
      if current_text.strip():
        sentence_end = words[word_idx]['end'] if word_idx < len(words) else 0
        sentences.append({
          'text': current_text.strip(),
          'start': sentence_start,
          'end': sentence_end
        })
        current_text = ''
        sentence_start = None

    if char == ' ':
      word_idx += 1

  # 남은 텍스트 처리
  if current_text.strip() and word_idx < len(words):
    sentences.append({
      'text': current_text.strip(),
      'start': sentence_start,
      'end': words[-1]['end'] if words else 0
    })

  return sentences


def call_elevenlabs_api(narration: str, voice_id: str) -> tuple[bytes, dict]:
  """
  ElevenLabs API 호출 (타임스탬프 포함)
  반환: (audio_bytes, alignment_dict)
  """
  if not ELEVENLABS_API_KEY:
    raise ValueError('ELEVENLABS_API_KEY 환경변수가 설정되지 않았습니다')

  url = f'{ELEVENLABS_API_URL}/text-to-speech/{voice_id}/with-timestamps'
  headers = {
    'xi-api-key': ELEVENLABS_API_KEY,
    'Content-Type': 'application/json'
  }
  body = {
    'text': narration,
    'model_id': 'eleven_multilingual_v2',
    'voice_settings': {
      'stability': 0.5,
      'similarity_boost': 0.75
    }
  }

  for attempt in range(MAX_RETRIES):
    try:
      response = requests.post(url, json=body, headers=headers, timeout=30)
      if response.status_code == 200:
        data = response.json()
        # audio_base64 → bytes로 변환
        import base64
        audio_bytes = base64.b64decode(data['audio_base64'])

        # alignment 추출 및 단어/문장 그룹핑
        character_times = data.get('alignment', {}).get('characters', [])
        words = group_alignment_into_words(character_times)
        sentences = group_alignment_into_sentences(words, narration)

        alignment_dict = {
          'words': words,
          'sentences': sentences,
          'total_duration': character_times[-1].get('end_time_ms', 0) / 1000 if character_times else 0
        }

        return audio_bytes, alignment_dict

      elif response.status_code == 401:
        logger.error('ElevenLabs API 인증 실패 (유효하지 않은 API 키)')
        raise ValueError('ELEVENLABS_API_KEY가 유효하지 않습니다')

      elif response.status_code == 429:
        logger.warning(f'ElevenLabs API 비율 제한, 재시도 {attempt + 1}/{MAX_RETRIES}')
        if attempt < MAX_RETRIES - 1:
          import time
          time.sleep(2 ** attempt)  # 지수 백오프
          continue
        raise RuntimeError('ElevenLabs API 비율 제한 초과')

      else:
        logger.error(f'ElevenLabs API 오류: {response.status_code} {response.text}')
        if attempt < MAX_RETRIES - 1:
          import time
          time.sleep(2 ** attempt)
          continue
        raise RuntimeError(f'ElevenLabs API 오류: {response.status_code}')

    except requests.RequestException as e:
      logger.error(f'ElevenLabs API 호출 실패: {e}, 재시도 {attempt + 1}/{MAX_RETRIES}')
      if attempt < MAX_RETRIES - 1:
        import time
        time.sleep(2 ** attempt)
        continue
      raise

  raise RuntimeError('ElevenLabs API 호출 최대 재시도 횟수 초과')


def generate_audio_with_alignment(
  narration: str,
  scene_index: int,
  voice_id: str = ELEVENLABS_VOICE_ID,
  use_cache: bool = True
) -> tuple[Path, Path]:
  """
  씬별 오디오 생성 (MP3 + alignment JSON)
  반환: (mp3_path, alignment_path)
  """
  mp3_path = get_cache_path(narration, scene_index, '_audio.mp3')
  alignment_path = get_cache_path(narration, scene_index, '_alignment.json')

  # 캐시 확인
  if use_cache and mp3_path.exists() and alignment_path.exists():
    logger.info(f'캐시된 오디오 사용: {mp3_path}')
    return mp3_path, alignment_path

  # API 호출
  logger.info(f'ElevenLabs 오디오 생성: Scene {scene_index}')
  audio_bytes, alignment_dict = call_elevenlabs_api(narration, voice_id)

  # MP3 저장
  mp3_path.parent.mkdir(parents=True, exist_ok=True)
  with open(mp3_path, 'wb') as f:
    f.write(audio_bytes)
  logger.info(f'MP3 저장: {mp3_path}')

  # alignment JSON 저장
  alignment_dict['scene_index'] = scene_index
  alignment_dict['audio_path'] = str(mp3_path)
  save_alignment_to_cache(alignment_path, alignment_dict)

  return mp3_path, alignment_path


def generate_all_audio(
  script_data: list[dict],
  use_cache: bool = True
) -> tuple[list[str], list[str]]:
  """
  전체 씬의 오디오 생성
  반환: (audio_paths, alignment_paths)
  """
  audio_paths = []
  alignment_paths = []

  for idx, scene in enumerate(script_data):
    narration = scene.get('narration', '')
    if not narration:
      logger.warning(f'Scene {idx}: 나레이션이 없습니다')
      continue

    try:
      mp3_path, alignment_path = generate_audio_with_alignment(
        narration,
        idx,
        use_cache=use_cache
      )
      audio_paths.append(str(mp3_path))
      alignment_paths.append(str(alignment_path))
    except Exception as e:
      logger.error(f'Scene {idx} 오디오 생성 실패: {e}')
      raise

  logger.info(f'전체 오디오 생성 완료: {len(audio_paths)}개 씬')
  return audio_paths, alignment_paths


def cmd_check() -> bool:
  """ElevenLabs API 연결 확인"""
  if not ELEVENLABS_API_KEY:
    logger.error('ELEVENLABS_API_KEY 환경변수가 설정되지 않았습니다')
    return False

  try:
    # API 연결 테스트 (voices 조회)
    url = f'{ELEVENLABS_API_URL}/voices'
    headers = {'xi-api-key': ELEVENLABS_API_KEY}
    response = requests.get(url, headers=headers, timeout=5)

    if response.status_code == 200:
      logger.info('✓ ElevenLabs API 연결 성공')
      return True
    else:
      logger.error(f'✗ ElevenLabs API 오류: {response.status_code}')
      return False
  except Exception as e:
    logger.error(f'✗ ElevenLabs API 연결 실패: {e}')
    return False


if __name__ == '__main__':
  logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
  )

  # 테스트
  if cmd_check():
    print('ElevenLabs API 연결 확인 완료')
  else:
    print('ElevenLabs API 연결 실패')
