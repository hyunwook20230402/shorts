"""
Step 1: NLP — 고전시가 원문 현대어 번역 + 씬 분할 + 이미지 프롬프트 생성

입력: extracted_raw_text (str)
출력: modern_script_data (list[dict]), image_prompts (list[str])
"""

import hashlib
import json
import logging
import os
import re
import uuid
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential
from theme_config import (
  DEFAULT_THEME,
  THEME_CATALOG,
  THEME_IMAGE_STYLE_GUIDE,
)

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(
  level=logging.INFO,
  format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)


HCX005_API_URL = 'https://clovastudio.stream.ntruss.com/v1/openai/chat/completions'

webtoon_style_prefix = (
    'Korean webtoon style, manhwa art style, '
    'traditional Korean ink painting influence, '
    'cinematic composition, detailed background, '
    '9:16 vertical format, high quality illustration, '
)

NLP_CHUNK_SIZE = int(os.getenv('NLP_CHUNK_SIZE', '8'))


def chunk_ocr_text(text: str, chunk_size: int = NLP_CHUNK_SIZE) -> list[str]:
  """OCR 텍스트를 chunk_size 행씩 분할. 빈 줄 제거 후 분할."""
  lines = [ln for ln in text.splitlines() if ln.strip()]
  return ['\n'.join(lines[i:i + chunk_size]) for i in range(0, len(lines), chunk_size)]

translate_system_prompt = """당신은 한국 고전시가 번역가이자 웹툰 쇼츠 대본 작가입니다.
원문을 분석하여 문장 단위로 씬을 분할하고 JSON을 출력하세요.

## 테마 분류 (필수)
이 시의 전체 테마/주제를 다음 13개 중 하나로 선택하세요:
  A. 강호자연 — 자연 속 한가로운 삶, 풍류
  B. 연군 — 임금에 대한 그리움 (유배/파직 후)
  C. 충절/우국 — 변함없는 충성, 나라 걱정
  D. 유배 — 유배지의 한과 억울함
  E. 애정 — 남녀 간 사랑, 상사의 정
  F. 이별의 정한 — 이별의 슬픔, 기다림, 재회 기원
  G. 교훈/도학 — 유교 윤리 덕목, 교화
  H. 풍자/해학 — 사회 모순 비판, 웃음
  I. 무상/탄로 — 세월의 덧없음, 늙음 한탄
  J. 종교/신앙 — 불교 신앙, 극락왕생 기원
  K. 기행 — 여행, 풍경 감상
  L. 노동/세시풍속 — 농사, 세시풍속, 민속
  M. 건국 송축 — 건국의 위업, 송축

중첩 해소 규칙:
- 연군 vs 애정: 신하-임금이면 B, 남녀면 E
- 충절 vs 연군: 충성 의지이면 C, 임금 그리움이면 B
- 이별 vs 애정: 이별/기다림이면 F, 사랑 자체면 E
- 유배 vs 연군: 유배 고난이면 D, 임금 그리움이면 B
- 강호자연 vs 교훈: 자연미면 A, 윤리면 G

## 규칙
1. 1구절 = 1씬. 의미 완결 단위로 최대한 상세히 분할.
2. modern_text: 정확히 1개 완결 구어체 문장 (10대 톤, 2문장 혼합 금지)
3. narration: TTS 낭독용 감성 독백 톤 (도발적, 10대 구어체. 예: "한때는 나도 임금님 최애였는데, 다 부질없네.")
4. emotion: 핵심 감정 한 단어 (예: 비장, 쾌활, 슬픔, 고독)
5. main_focus: "background"/"character"/"object" 중 택 1
6. visual_elements: {background, character, object, atmosphere} 영어 키워드
7. title, author: 빈칸 없이 채울 것 (미상 가능)

## 출력 형식 (JSON만 출력, 설명 금지)
{"theme":"A~M 코드","theme_en":"영문키","title":"...","author":"...","total_scenes":N,"scenes":[{"scene_index":1,"original_text":"...","modern_text":"...","narration":"...","emotion":"...","main_focus":"...","visual_elements":{"background":"...","character":"...","object":"...","atmosphere":"..."},"image_prompt":""}]}
"""

translate_user_prompt_prefix = '다음 고전시가 원문을 분석하여 씬 분할 및 현대어 번역 JSON을 생성하세요.'

# 하드코딩된 '조선시대'를 제거하고 동적 컨텍스트를 받도록 수정
image_prompt_system_prompt = """당신은 ComfyUI 이미지 생성 전문가입니다.
한국 고전시가 웹툰 영상을 위한 씬 이미지 프롬프트를 영어로 생성하세요.

## 프롬프트 생성 규칙
1. 출력은 반드시 영어 프롬프트 텍스트 한 줄만 출력하세요. (JSON, 설명, 마크다운 절대 금지)
2. 씬의 배경 장소, 계절/날씨, 등장인물 행동을 구체적으로 묘사하세요.
3. 감정(emotion)을 lighting과 color tone으로 표현하세요:
   - 비장/슬픔: dark blue tones, dramatic lighting, heavy atmosphere
   - 쾌활/유머: warm golden light, bright colors, lively atmosphere
   - 고독: muted tones, sparse composition, solitary figure
4. 제공된 역사적 배경(historical_context)을 바탕으로 해당 시대(예: 고려, 조선 등)에 맞는 의복과 건축 양식을 묘사하세요.
5. 200 토큰 이내로 작성하세요.
6. 제공된 테마 스타일 가이드(theme_style_guide)의 색감/구도 지시를 반드시 반영하세요."""

image_prompt_user_prompt_prefix = """씬 정보:
- 시대적/역사적 배경: {historical_context}
- 감정: {emotion}
- 배경 설명 (한국어): {background}
- 나레이션 (시각적 묘사): {narration}
- 테마 스타일 가이드: {theme_style_guide}

위 씬에 맞는 ComfyUI 이미지 프롬프트를 영어로 생성하세요. 프롬프트만 출력하고 설명은 금지."""


# ===== 캐시 함수 =====

def get_cache_key(text: str) -> str:
  """텍스트 내용으로 캐시 키 생성 (SHA-256 앞 16자)"""
  normalized = ' '.join(text.split())
  return hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:16]


def get_cache_path(poem_dir: Path) -> Path:
  """캐시 파일 경로 생성"""
  return poem_dir / 'step1_nlp.json'


def load_from_cache(cache_path: Path) -> dict | None:
  """캐시 파일에서 JSON 로드"""
  if cache_path.exists():
    logger.info('캐시에서 NLP 결과 로드: %s', cache_path)
    try:
      return json.loads(cache_path.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, IOError) as e:
      logger.warning('캐시 파일 읽기 실패, 재처리: %s', str(e))
      return None
  return None


def save_to_cache(cache_path: Path, data: dict) -> None:
  """JSON 캐시 저장 (UTF-8)"""
  try:
    cache_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    logger.info('NLP 결과 캐시 저장: %s', cache_path)
  except Exception as e:
    logger.error('캐시 저장 실패: %s', str(e))
    raise


def get_context_cache_path(poem_dir: Path) -> Path:
  """역사적 배경 캐시 경로 생성"""
  return poem_dir / 'step1_context.txt'


def load_context_from_cache(cache_path: Path) -> str | None:
  """역사적 배경 캐시 로드"""
  if cache_path.exists():
    logger.info('캐시에서 역사적 배경 로드: %s', cache_path)
    try:
      return cache_path.read_text(encoding='utf-8')
    except IOError as e:
      logger.warning('역사적 배경 캐시 읽기 실패: %s', str(e))
      return None
  return None


def save_context_to_cache(cache_path: Path, context: str) -> None:
  """역사적 배경 캐시 저장"""
  try:
    cache_path.write_text(context, encoding='utf-8')
    logger.info('역사적 배경 캐시 저장: %s', cache_path)
  except Exception as e:
    logger.warning('역사적 배경 캐시 저장 실패: %s', str(e))


# ===== JSON 파싱 안전 처리 =====

def strip_code_fence(text: str) -> str:
  """마크다운 코드펜스 제거"""
  text = re.sub(r'^```(?:json)?\s*\n', '', text.strip())
  text = re.sub(r'\n```\s*$', '', text)
  return text.strip()


def extract_json_block(text: str) -> str:
  """첫 { 부터 마지막 } 까지 추출"""
  start = text.find('{')
  end = text.rfind('}')
  if start == -1 or end == -1:
    raise ValueError(f'JSON 블록을 찾을 수 없습니다. 응답: {text[:200]}')
  return text[start:end + 1]


def safe_parse_json(text: str) -> dict:
  """JSON 파싱 + 복구 (trailing comma 제거 등)"""
  cleaned = strip_code_fence(text)
  cleaned = extract_json_block(cleaned)

  try:
    return json.loads(cleaned)
  except json.JSONDecodeError as e:
    logger.warning('1차 JSON 파싱 실패, 후처리 시도: %s', str(e))
    # trailing comma 제거
    cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)
    # 제어문자 제거
    cleaned = re.sub(r'[\x00-\x1f\x7f]', ' ', cleaned)
    try:
      return json.loads(cleaned)
    except json.JSONDecodeError as e2:
      logger.error('JSON 파싱 최종 실패. 원본 응답: %s', text[:500])
      raise ValueError(f'LLM 응답 JSON 파싱 불가: {str(e2)}') from e2


def split_into_sentences(text: str) -> list[str]:
  """modern_text를 문장 단위로 분리 (마침표 기준)"""
  parts = re.split(r'(?<=[.!?])\s+', text.strip())
  return [p.strip() for p in parts if p.strip()]


def validate_scene(raw_scene: dict, idx: int) -> dict:
  """
  씬 데이터 유효성 검사 및 정규화.

  불변 조건: 1씬 = 1문장 (modern_sentences는 항상 [modern_text] 1개 원소 리스트)
  """
  modern_text = raw_scene.get('modern_text', '')

  base = {
    'scene_index': idx + 1,
    'original_text': raw_scene.get('original_text', ''),
    'modern_text': modern_text,
    'modern_sentences': [modern_text],
    'narration': raw_scene.get('narration', modern_text),
    'emotion': raw_scene.get('emotion', '미정'),
    'main_focus': raw_scene.get('main_focus', 'background'),
    'visual_elements': raw_scene.get('visual_elements', {}),
    'background': raw_scene.get('background',
      raw_scene.get('visual_elements', {}).get('background', 'traditional Korean landscape')),
    'background_weight': 1.0,
    'image_prompt': '',
  }
  return base


# ===== HCX-005 API 호출 =====

@retry(
  stop=stop_after_attempt(3),
  wait=wait_exponential(multiplier=1, min=2, max=30),
  reraise=True,
)
def fetch_historical_context(raw_text: str, poem_dir: Path) -> str:
  """HCX-005로 역사적 배경 조사 (캐시 지원)"""
  logger.info('역사적 배경 조사 시작...')

  cache_path = get_context_cache_path(poem_dir)
  cached_context = load_context_from_cache(cache_path)
  if cached_context is not None:
    return cached_context

  api_key = os.environ.get('NCP_CLOVA_API_KEY')
  if not api_key:
    logger.warning('NCP_CLOVA_API_KEY 미설정 - 역사적 배경 조사 스킵')
    return ''

  headers = {
    'Authorization': f'Bearer {api_key}',
    'Content-Type': 'application/json',
  }

  system_prompt = """당신은 한국 고전시가 역사 전문가입니다.
아래 고전시가의 작가, 창작 배경, 시대적 맥락을 200자 이내로 요약하세요.
나레이션 작성자가 참고할 수 있도록 핵심 비하인드 스토리와 역사적 팩트 위주로 작성하세요.
불확실한 정보는 '전해지기로는'으로 표시하세요.
출력은 한국어 텍스트만 (JSON, 마크다운 금지)."""

  payload = {
    'model': 'HCX-005',
    'messages': [
      {'role': 'system', 'content': system_prompt},
      {'role': 'user', 'content': f'다음 고전시가의 역사적 배경을 요약해주세요:\n\n{raw_text:500}'},
    ],
    'max_tokens': 1000,
    'temperature': 0.3,
  }

  try:
    response = requests.post(
      HCX005_API_URL,
      headers=headers,
      json=payload,
      timeout=60,
    )
    response.raise_for_status()

    result = response.json()
    context = result.get('choices', [{}])[0].get('message', {}).get('content', '')

    if context.strip():
      # 응답 길이 검증
      if len(context.strip()) < 50:
        logger.warning('역사적 배경 응답이 너무 짧습니다 (재시도 권장): %d자', len(context.strip()))
      save_context_to_cache(cache_path, context)
      logger.info('역사적 배경 조사 완료 (%d자)', len(context.strip()))
      return context

    logger.warning('역사적 배경 조사 결과가 비어있음')
    return ''

  except requests.exceptions.RequestException as e:
    logger.warning('역사적 배경 조사 API 호출 실패: %s', str(e))
    return ''

@retry(
  stop=stop_after_attempt(3),
  wait=wait_exponential(multiplier=1, min=2, max=30),
  reraise=True,
)
def call_hcx005_translate(text: str, historical_context: str = '') -> dict:
  """HCX-005로 번역 + 씬 분할 (JSON 응답)"""
  logger.info('HCX-005 번역 + 씬 분할 API 호출 중...')

  api_key = os.environ.get('NCP_CLOVA_API_KEY')
  if not api_key:
    raise ValueError('NCP_CLOVA_API_KEY 환경변수가 설정되지 않았습니다.')

  headers = {
    'Authorization': f'Bearer {api_key}',
    'Content-Type': 'application/json',
  }

  # 역사적 배경이 있으면 시스템 프롬프트에 추가
  system_content = translate_system_prompt
  if historical_context.strip():
    system_content += f'\n\n## 역사적 배경 참고 (나레이션/메타데이터 작성 시 활용)\n{historical_context}'

  payload = {
    'model': 'HCX-005',
    'messages': [
      {
        'role': 'system',
        'content': system_content,
      },
      {
        'role': 'user',
        'content': f'{translate_user_prompt_prefix}\n\n{text}',
      },
    ],
    'max_tokens': 4096,
    'temperature': 0.3,
  }

  try:
    response = requests.post(
      HCX005_API_URL,
      headers=headers,
      json=payload,
      timeout=60,
    )
    response.raise_for_status()

    result = response.json()
    response_text = result.get('choices', [{}])[0].get('message', {}).get('content', '')

    logger.info('HCX-005 응답 수신, JSON 파싱 중...')
    parsed = safe_parse_json(response_text)

    scenes = parsed.get('scenes', [])
    logger.info('번역 + 씬 분할 완료. 씬 수: %d', len(scenes))
    return parsed

  except requests.exceptions.RequestException as e:
    logger.error('HCX-005 API 호출 실패: %s', str(e))
    try:
      error_detail = e.response.text if hasattr(e, 'response') else ''
      if error_detail:
        logger.error('응답 본문: %s', error_detail)
    except Exception:
      pass
    raise RuntimeError(f'HCX-005 API 호출 중 오류 발생: {str(e)}') from e


@retry(
  stop=stop_after_attempt(3),
  wait=wait_exponential(multiplier=1, min=2, max=30),
  reraise=True,
)
def call_hcx005_image_prompt(scene: dict, historical_context: str, theme_code: str = DEFAULT_THEME) -> str:
  """HCX-005로 씬별 이미지 프롬프트 생성 (역사적 배경 + 테마 스타일 가이드 동적 주입)"""
  logger.info('이미지 프롬프트 생성 중: 씬 %d (테마: %s)', scene['scene_index'], theme_code)

  api_key = os.environ.get('NCP_CLOVA_API_KEY')
  if not api_key:
    raise ValueError('NCP_CLOVA_API_KEY 환경변수가 설정되지 않았습니다.')

  style_guide = THEME_IMAGE_STYLE_GUIDE.get(theme_code, '')

  user_prompt = image_prompt_user_prompt_prefix.format(
    historical_context=historical_context,
    emotion=scene['emotion'],
    background=scene['background'],
    narration=scene.get('narration', scene.get('modern_text', '')),
    theme_style_guide=style_guide,
  )

  headers = {
    'Authorization': f'Bearer {api_key}',
    'Content-Type': 'application/json',
  }

  payload = {
    'model': 'HCX-005',
    'messages': [
      {
        'role': 'system',
        'content': image_prompt_system_prompt,
      },
      {
        'role': 'user',
        'content': user_prompt,
      },
    ],
    'max_tokens': 300,
    'temperature': 0.5,
  }

  try:
    response = requests.post(
      HCX005_API_URL,
      headers=headers,
      json=payload,
      timeout=60,
    )
    response.raise_for_status()

    result = response.json()
    prompt = result.get('choices', [{}])[0].get('message', {}).get('content', '').strip()

    logger.info('씬 %d 이미지 프롬프트 생성 완료 (%d자)', scene['scene_index'], len(prompt))
    return prompt

  except requests.exceptions.RequestException as e:
    logger.error('이미지 프롬프트 생성 실패 (씬 %d): %s', scene['scene_index'], str(e))
    raise RuntimeError(f'이미지 프롬프트 생성 중 오류: {str(e)}') from e



# ===== Notion API 연동 =====

def _get_notion_client() -> tuple:
  """Notion 클라이언트 생성. 키 없으면 (None, False) 반환"""
  api_key = os.environ.get('NOTION_API_KEY')
  if not api_key:
    logger.warning('NOTION_API_KEY가 설정되지 않아 Notion 로깅을 건너뜁니다.')
    return None, False

  try:
    from notion_client import Client
    return Client(auth=api_key), True
  except ImportError:
    logger.warning('notion_client 라이브러리 미설치, Notion 로깅 건너뜀')
    return None, False


def log_to_notion_poem(
  original: str,
  modern_scenes: list,
  task_id: str,
) -> None:
  """Notion poem_translation_log DB에 번역 결과 기록"""
  client, available = _get_notion_client()
  if not available:
    return

  db_id = os.environ.get('NOTION_POEM_LOG_DB_ID')
  if not db_id:
    logger.warning('NOTION_POEM_LOG_DB_ID가 설정되지 않아 poem 로그를 건너뜁니다.')
    return

  try:
    # 씬 전체 현대어를 합쳐서 하나의 레코드로 저장
    modern_combined = '\n\n'.join(s['modern_text'] for s in modern_scenes)

    client.pages.create(
      parent={'database_id': db_id},
      properties={
        'original_archaic_text': {
          'title': [{'text': {'content': original[:2000]}}],
        },
        'translated_modern_text': {
          'rich_text': [{'text': {'content': modern_combined[:2000]}}],
        },
        'task_id': {
          'rich_text': [{'text': {'content': task_id}}],
        },
        'created_at': {
          'date': {'start': datetime.utcnow().isoformat()},
        },
      },
    )
    logger.info('Notion poem_translation_log 기록 완료 (task_id: %s)', task_id)
  except Exception as e:
    logger.warning('Notion poem 로그 기록 실패 (무시): %s', str(e))


def update_notion_task_status(
  task_id: str,
  step: int,
  message: str,
  status: str = 'in_progress',
) -> None:
  """Notion task_status_log DB 업데이트"""
  client, available = _get_notion_client()
  if not available:
    return

  db_id = os.environ.get('NOTION_TASK_STATUS_DB_ID')
  if not db_id:
    logger.warning('NOTION_TASK_STATUS_DB_ID가 설정되지 않아 task status 업데이트를 건너뜁니다.')
    return

  try:
    client.pages.create(
      parent={'database_id': db_id},
      properties={
        'task_id': {
          'title': [{'text': {'content': task_id}}],
        },
        'current_step': {
          'number': step,
        },
        'status_message': {
          'rich_text': [{'text': {'content': message[:2000]}}],
        },
        'created_at': {
          'date': {'start': datetime.utcnow().isoformat()},
        },
      },
    )
    logger.info('Notion task_status_log 업데이트 완료 (task_id: %s, step: %d)', task_id, step)
  except Exception as e:
    logger.warning('Notion task status 업데이트 실패 (무시): %s', str(e))


# ===== Step 1 메인 함수 =====

def process_nlp(
  extracted_raw_text: str,
  poem_dir: Path,
  task_id: str | None = None,
  use_cache: bool = True,
) -> tuple:
  """
  Step 1 NLP 메인 함수

  Args:
    extracted_raw_text: Step 0에서 나온 고전시가 원문
    poem_dir: 캐시 및 아티팩트 저장 폴더
    task_id: 파이프라인 작업 ID (없으면 UUID 자동 생성)
    use_cache: 캐시 사용 여부

  Returns:
    (modern_script_data, image_prompts)
  """
  # poem_dir 생성
  poem_dir = Path(poem_dir)
  poem_dir.mkdir(parents=True, exist_ok=True)

  # 1. task_id 보장
  if not task_id:
    task_id = str(uuid.uuid4())
    logger.info('task_id 자동 생성: %s', task_id)

  # 2. 캐시 확인
  cache_path = get_cache_path(poem_dir)
  if use_cache:
    cached = load_from_cache(cache_path)
    if cached is not None:
      # 오래된 캐시 호환: theme 필드 없으면 기본값 보충 후 재저장
      if 'theme' not in cached or 'theme_en' not in cached:
        cached['theme'] = cached.get('theme', DEFAULT_THEME)
        cached['theme_en'] = cached.get('theme_en', THEME_CATALOG[DEFAULT_THEME]['en'])
        save_to_cache(cache_path, cached)
        logger.info('캐시에 theme 필드 보충 완료: %s', cached['theme'])
      logger.info('캐시된 결과 반환')
      return cached['modern_script_data'], cached['image_prompts']

  # 3. Notion: 파이프라인 시작 상태 업데이트
  update_notion_task_status(task_id, step=1, message='NLP 처리 시작', status='in_progress')

  try:
    # 4. 역사적 배경 조사 (선택)
    logger.info('역사적 배경 조사 시작')
    historical_context = fetch_historical_context(extracted_raw_text, poem_dir)

    # 5. HCX-005: 번역 + 씬 분할 (청크 단위 처리)
    logger.info('번역 + 씬 분할 시작')
    chunks = chunk_ocr_text(extracted_raw_text)
    logger.info('OCR 텍스트를 %d개 청크로 분할 (청크당 최대 %d행)', len(chunks), NLP_CHUNK_SIZE)
    raw_scenes, title, author = [], '', ''
    theme, theme_en = DEFAULT_THEME, THEME_CATALOG[DEFAULT_THEME]['en']
    for chunk_idx, chunk in enumerate(chunks):
      logger.info('청크 %d/%d 번역 중 (%d행)', chunk_idx + 1, len(chunks), len(chunk.splitlines()))
      result = call_hcx005_translate(chunk, historical_context)
      raw_scenes.extend(result.get('scenes', []))
      if chunk_idx == 0:
        title = result.get('title', '')
        author = result.get('author', '')
        # 테마 추출 (첫 청크에서만)
        raw_theme = result.get('theme', DEFAULT_THEME)
        if raw_theme in THEME_CATALOG:
          theme = raw_theme
          theme_en = THEME_CATALOG[theme]['en']
        else:
          logger.warning('알 수 없는 테마 코드: %s, fallback: %s', raw_theme, DEFAULT_THEME)
      logger.info('청크 %d 완료, 누적 씬: %d', chunk_idx + 1, len(raw_scenes))
    logger.info('씬 분할 완료: %d씬, 테마: %s (%s)', len(raw_scenes), theme, THEME_CATALOG[theme]['ko'])

    # 6. 씬 유효성 검사
    validated_scenes = [
      validate_scene(s, i)
      for i, s in enumerate(raw_scenes)
    ]

# 7. 각 씬(문장)의 이미지 프롬프트 생성
    image_prompts = []
    for i, scene in enumerate(validated_scenes):
        # ✅ 체크 1: 루프의 인덱스(i)를 사용하여 강제로 순차적인 씬 번호 부여
        current_scene_idx = i + 1
        logger.info(f'이미지 프롬프트 생성 중: 씬 {current_scene_idx}/{len(validated_scenes)}')
        
        # ✅ 체크 2: 모든 필드를 .get()으로 안전하게 가져옴
        sentence_text = scene.get('modern_text', '')
        
        sentence_scene_ctx = {
            'scene_index': current_scene_idx,
            'emotion': scene.get('emotion', 'serene'),
            'background': scene.get('background', 'ancient Korean scenery'),
            'narration': scene.get('narration', sentence_text),
            'modern_text': sentence_text,
            'main_focus': scene.get('main_focus', 'background'),
            'visual_elements': scene.get('visual_elements', {})
        }
        
        try:
            # LLM 호출하여 영문 프롬프트 생성
            prompt = call_hcx005_image_prompt(sentence_scene_ctx, historical_context, theme)
            final_prompt = f"{prompt}, {webtoon_style_prefix.rstrip(', ')}"
        except Exception as e:
            logger.warning(f"씬 {current_scene_idx} 프롬프트 생성 실패, fallback 적용: {e}")
            # 예외 시에도 감정 데이터를 안전하게 가져옴
            curr_emotion = scene.get('emotion', 'serene')
            final_prompt = f"({curr_emotion} mood:1.3), Korean traditional scene, {webtoon_style_prefix.rstrip(', ')}"

        # 1씬 1문장 원칙에 따라 데이터 구조 확정
        scene['scene_index'] = current_scene_idx
        scene['image_prompt'] = final_prompt
        image_prompts.append(final_prompt)

    # 8. 데이터 통합 및 단일 캐시 파일 저장 (Step 2~6 연결용)
    modern_script_data = validated_scenes

    save_to_cache(cache_path, {
        'theme': theme,
        'theme_en': theme_en,
        'modern_script_data': modern_script_data,
        'image_prompts': image_prompts,
        'title': title,
        'author': author,
        'historical_context': historical_context,
    })

    # 10. Notion: 기록 및 상태 업데이트
    log_to_notion_poem(extracted_raw_text, modern_script_data, task_id)
    update_notion_task_status(
        task_id, step=1,
        message=f'NLP 처리 완료 ({len(modern_script_data)}씬)',
        status='completed',
    )

    logger.info('Step 1 NLP 완료. 씬 수: %d, 파일 저장: %s', len(modern_script_data), cache_path)
    return modern_script_data, image_prompts

  except Exception as e:
    logger.error('Step 1 NLP 처리 실패: %s', str(e))
    update_notion_task_status(task_id, step=1, message=f'오류: {str(e)}', status='failed')
    raise RuntimeError(f'NLP 처리 중 오류 발생: {str(e)}') from e


# ===== CLI 실행 =====

if __name__ == '__main__':
  import sys

  # stdout UTF-8 인코딩 명시
  if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

  poem_id = "default_poem"

  if len(sys.argv) < 2:
    # 인자 없으면 step0 캐시 파일 자동 사용
    cache_dir = Path('cache/step0')
    txt_files = list(cache_dir.glob('*_ocr.txt'))
    if not txt_files:
      print('사용법: python step1_nlp.py <원문텍스트_또는_파일경로>')
      sys.exit(1)
    
    txt_path = txt_files[0]
    input_text = txt_path.read_text(encoding='utf-8')
    poem_id = txt_path.stem.replace('_ocr', '') 
    logger.info(f'Step 0 캐시에서 텍스트 자동 로드: {txt_path} (poem_id: {poem_id})')
  else:
    # 인자가 poem_dir 폴더 경로인 경우
    arg = sys.argv[1]
    poem_dir = Path(arg)

    if poem_dir.is_dir():
      # poem_dir/step0_ocr.txt에서 OCR 텍스트 로드
      ocr_file = poem_dir / 'step0_ocr.txt'
      if ocr_file.exists():
        input_text = ocr_file.read_text(encoding='utf-8')
        poem_id = poem_dir.name  # "poem_01", "poem_02" 등
        logger.info(f'poem_dir에서 OCR 텍스트 로드: {ocr_file} (poem_id: {poem_id})')
      else:
        logger.error(f'Step 0 캐시 파일 없음: {ocr_file}')
        sys.exit(1)
    else:
      # 파일 경로가 주어진 경우
      txt_path = poem_dir
      if txt_path.exists() and txt_path.is_file():
        input_text = txt_path.read_text(encoding='utf-8')
        poem_id = txt_path.stem.replace('_ocr', '')
        logger.info(f'파일에서 텍스트 로드: {arg} (poem_id: {poem_id})')
      else:
        # 직접 텍스트로 처리
        input_text = arg
        poem_id = f"text_{hashlib.md5(arg.encode()).hexdigest()[:8]}"
  
  try:
    script_data, prompts = process_nlp(input_text, poem_dir)
    print(f'\n=== NLP 처리 결과: {len(script_data)}씬 ===')
    for scene in script_data:
      print(f"\n[씬 {scene['scene_index']}] 감정: {scene['emotion']}")
      print(f"원문: {scene['original_text'][:60]}...")
      print(f"현대어: {scene['modern_text'][:60]}...")
      print(f"나레이션: {scene['narration'][:80]}...")
    print('\n=== 이미지 프롬프트 샘플 ===')
    if prompts:
      print(f'씬 1: {prompts[0][:120]}...')
    print('========================\n')
  except (ValueError, RuntimeError) as e:
    logger.error('실행 실패: %s', str(e))
    sys.exit(1)


