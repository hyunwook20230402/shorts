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

# .env 파일 명시적 로드
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

logger = logging.getLogger(__name__)

# 환경변수
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY', '')
ELEVENLABS_VOICE_ID = os.getenv('ELEVENLABS_VOICE_ID')  # 기본값
ELEVENLABS_API_URL = 'https://api.elevenlabs.io/v1'
CACHE_DIR = Path('cache/step2')
MAX_RETRIES = 3

# 환경변수 로드 로깅
if not ELEVENLABS_API_KEY:
  logger.warning(f'ELEVENLABS_API_KEY not set. env_path={env_path}')
else:
  logger.info(f'ELEVENLABS_API_KEY loaded: {ELEVENLABS_API_KEY[:20]}...')


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


def call_elevenlabs_api(narration: str, voice_id: str) -> bytes:
  """
  ElevenLabs API 호출 (Free 버전 대응)
  반환: audio_bytes

  Note: Free 버전은 with-timestamps 미지원이므로 기본 TTS만 사용
  Free 티어용 output_format 고정: mp3_44100_128
  """
  if not ELEVENLABS_API_KEY:
    raise ValueError('ELEVENLABS_API_KEY 환경변수가 설정되지 않았습니다')

  # Free 버전: 기본 TTS 엔드포인트 사용
  url = f'{ELEVENLABS_API_URL}/text-to-speech/{voice_id}'
  headers = {
    'xi-api-key': ELEVENLABS_API_KEY,
    'Content-Type': 'application/json'
  }
  body = {
    'text': narration,
    'model_id': 'eleven_multilingual_v2',
    'output_format': 'mp3_44100_128',  # Free 티어용 포맷 고정
    'voice_settings': {
      'stability': 0.5,
      'similarity_boost': 0.75
    }
  }

  for attempt in range(MAX_RETRIES):
    try:
      response = requests.post(url, json=body, headers=headers, timeout=30)
      if response.status_code == 200:
        # 직접 바이너리 응답 (JSON이 아님)
        return response.content

      elif response.status_code == 401:
        logger.error('ElevenLabs API 인증 실패 (유효하지 않은 API 키)')
        raise ValueError('ELEVENLABS_API_KEY가 유효하지 않습니다')

      elif response.status_code == 429:
        logger.warning(f'ElevenLabs API 비율 제한, 재시도 {attempt + 1}/{MAX_RETRIES}')
        if attempt < MAX_RETRIES - 1:
          import time
          time.sleep(2 ** attempt)
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


def estimate_alignment_from_audio(
  audio_path: str,
  text: str
) -> dict:
  """
  오디오 파일의 길이로부터 alignment 추정 (Free 버전용)

  단어/문장을 균등하게 분배하여 타임스탬프 생성
  (실제 음성 길이에 기반하지만 정확도는 떨어짐)
  """
  # 실제 MP3 파일 길이 측정
  total_duration = None

  # 시도 1: mutagen (MP3 메타데이터 직접 읽음)
  try:
    from mutagen.mp3 import MP3
    audio_file = MP3(audio_path)
    total_duration = audio_file.info.length
    logger.info(f'mutagen으로 MP3 길이 측정: {total_duration:.2f}초')
  except ImportError:
    logger.warning('mutagen 패키지 미설치')
  except Exception as e:
    logger.warning(f'mutagen 오디오 길이 조회 실패: {e}')

  # 시도 2: moviepy AudioFileClip (이미 설치됨)
  if total_duration is None:
    try:
      from moviepy.audio.io.AudioFileClip import AudioFileClip
      audio_clip = AudioFileClip(audio_path)
      total_duration = audio_clip.duration
      audio_clip.close()
      logger.info(f'moviepy로 MP3 길이 측정: {total_duration:.2f}초')
    except Exception as e:
      logger.warning(f'moviepy 오디오 길이 조회 실패: {e}')

  # 시도 3: wave (WAV 파일용, MP3는 실패할 가능성 높음)
  if total_duration is None:
    try:
      import wave
      with wave.open(audio_path, 'rb') as wav_file:
        frames = wav_file.getnframes()
        rate = wav_file.getframerate()
        total_duration = frames / rate
        logger.info(f'wave으로 오디오 길이 측정: {total_duration:.2f}초')
    except Exception as e:
      logger.warning(f'wave 오디오 길이 조회 실패: {e}')

  # 최후의 fallback: 텍스트 길이 추정
  if total_duration is None:
    logger.warning('모든 오디오 길이 측정 방법 실패, 텍스트 길이로 추정')
    total_duration = max(2.0, len(text) * 0.1)

  # 단어 분리
  words = text.split()
  word_duration = total_duration / max(len(words), 1)

  # 문장 분리 (마침표, 느낌표, 물음표 기준)
  import re
  sentences_raw = re.split(r'[.!?。!？]+', text)
  sentences = [s.strip() for s in sentences_raw if s.strip()]

  # word-level alignment 생성
  word_times = []
  current_time = 0.0
  for word in words:
    word_times.append({
      'word': word,
      'start': current_time,
      'end': current_time + word_duration
    })
    current_time += word_duration

  # sentence-level alignment 생성
  sentence_times = []
  sent_duration = total_duration / max(len(sentences), 1)
  current_time = 0.0
  for sent in sentences:
    sentence_times.append({
      'text': sent,
      'start': current_time,
      'end': current_time + sent_duration
    })
    current_time += sent_duration

  return {
    'total_duration': total_duration,
    'words': word_times,
    'sentences': sentence_times
  }


def generate_audio_with_alignment(
  narration: str,
  scene_index: int,
  voice_id: str = ELEVENLABS_VOICE_ID,
  use_cache: bool = True
) -> tuple[Path, Path]:
  """
  씬별 오디오 생성 (MP3 + alignment JSON)
  반환: (mp3_path, alignment_path)

  Free 버전: 기본 TTS + 추정 alignment
  """
  mp3_path = get_cache_path(narration, scene_index, '_audio.mp3')
  alignment_path = get_cache_path(narration, scene_index, '_alignment.json')

  # 캐시 확인
  if use_cache and mp3_path.exists() and alignment_path.exists():
    logger.info(f'캐시된 오디오 사용: {mp3_path}')
    return mp3_path, alignment_path

  # API 호출
  logger.info(f'ElevenLabs 오디오 생성: Scene {scene_index}')
  audio_bytes = call_elevenlabs_api(narration, voice_id)

  # MP3 저장
  mp3_path.parent.mkdir(parents=True, exist_ok=True)
  with open(mp3_path, 'wb') as f:
    f.write(audio_bytes)
  logger.info(f'MP3 저장: {mp3_path}')

  # alignment 추정 및 저장
  alignment_dict = estimate_alignment_from_audio(str(mp3_path), narration)
  alignment_dict['scene_index'] = scene_index
  alignment_dict['audio_path'] = str(mp3_path)
  alignment_dict['note'] = 'Free 버전: 추정된 타임스탬프 (정확도 낮음)'

  save_alignment_to_cache(alignment_path, alignment_dict)

  return mp3_path, alignment_path


def clean_tts_text(text: str) -> str:
  """TTS 전달 전 구두점 제거 (마침표, 쉼표, 물결 등 음성 불필요 기호)"""
  import re
  # 음성으로 읽힐 필요 없는 구두점 제거
  cleaned = re.sub(r'[.,，。、·~～!！?？;；:："""\'\'()\[\]{}]', ' ', text)
  # 연속 공백 정리
  cleaned = re.sub(r'\s+', ' ', cleaned).strip()
  return cleaned


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
    text_content = scene.get('modern_text', '')
    if not text_content:
      logger.warning(f'Scene {idx}: modern_text가 없습니다')
      continue

    # 구두점 제거 후 TTS에 전달
    cleaned_text = clean_tts_text(text_content)
    if not cleaned_text:
      logger.warning(f'Scene {idx}: 구두점 제거 후 텍스트가 없습니다')
      continue

    try:
      mp3_path, alignment_path = generate_audio_with_alignment(
        cleaned_text,
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
  """ElevenLabs API 연결 확인 (TTS 엔드포인트 테스트)"""
  if not ELEVENLABS_API_KEY:
    logger.error('ELEVENLABS_API_KEY 환경변수가 설정되지 않았습니다')
    return False

  if not ELEVENLABS_VOICE_ID:
    logger.error('ELEVENLABS_VOICE_ID 환경변수가 설정되지 않았습니다')
    return False

  try:
    # API 연결 테스트 (TTS 호출)
    url = f'{ELEVENLABS_API_URL}/text-to-speech/{ELEVENLABS_VOICE_ID}'
    headers = {
      'xi-api-key': ELEVENLABS_API_KEY,
      'Content-Type': 'application/json'
    }
    body = {
      'text': '테스트',
      'model_id': 'eleven_multilingual_v2',
      'output_format': 'mp3_44100_128'
    }
    response = requests.post(url, json=body, headers=headers, timeout=10)

    if response.status_code == 200:
      logger.info('✓ ElevenLabs API 연결 성공')
      return True
    else:
      logger.error(f'✗ ElevenLabs API 오류: {response.status_code} - {response.text[:100]}')
      return False
  except Exception as e:
    logger.error(f'✗ ElevenLabs API 연결 실패: {e}')
    return False


if __name__ == '__main__':
  logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
      logging.FileHandler('step2_tts.log', encoding='utf-8'),
      logging.StreamHandler()
    ]
  )

  logger.info('=' * 70)
  logger.info('Step 2: ElevenLabs TTS 테스트')
  logger.info('=' * 70)

  # 1. ElevenLabs API 확인
  if not cmd_check():
    logger.error('✗ ElevenLabs API 연결 실패')
    exit(1)

  # 2. 최근 Step 1 NLP 파일 탐색
  nlp_files = sorted(Path('cache/step1').glob('*_nlp.json'))
  if not nlp_files:
    logger.error('✗ Step 1 NLP 캐시 없음')
    exit(1)

  nlp_path = nlp_files[-1]
  with open(nlp_path, 'r', encoding='utf-8') as f:
    nlp_data = json.load(f)

  script_data = nlp_data.get('modern_script_data', [])
  logger.info(f'NLP 데이터: {len(script_data)}개 씬')

  # 3. Step 2 실행
  try:
    logger.info('\nTTS 생성 실행 중...')
    audio_paths, alignment_paths = generate_all_audio(script_data, use_cache=True)

    logger.info(f'\n✓ TTS 생성 완료: {len(audio_paths)}개')
    for i, (audio, alignment) in enumerate(zip(audio_paths, alignment_paths)):
      logger.info(f'\nScene {i}:')
      logger.info(f'  Audio: {Path(audio).name}')
      logger.info(f'  Alignment: {Path(alignment).name}')

    logger.info('\n' + '=' * 70)
    logger.info('✓ Step 2 테스트 완료')
    logger.info('=' * 70)
    exit(0)

  except Exception as e:
    logger.error(f'\n✗ Step 2 실패: {e}', exc_info=True)
    exit(1)
