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

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(
  level=logging.INFO,
  format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)

CACHE_DIR = Path('cache/step1')
CACHE_DIR.mkdir(parents=True, exist_ok=True)

HCX005_API_URL = 'https://clovastudio.stream.ntruss.com/v1/openai/chat/completions'

# 웹툰 스타일 프롬프트 prefix (모든 씬에 동일하게 적용)
WEBTOON_STYLE_PREFIX = (
  'Korean webtoon style, manhwa art style, '
  'traditional Korean ink painting influence, '
  'cinematic composition, detailed background, '
  '9:16 vertical format, high quality illustration, '
)

# 번역 + 씬 분할 시스템 프롬프트
TRANSLATE_SYSTEM_PROMPT = """당신은 한국 고전시가 전문 번역가이자 영상 대본 작가입니다.
주어진 고전시가 원문을 분석하여 씬 단위로 분할하고, 각 씬을 현대어로 번역한 후
웹툰 영상 쇼츠용 대본 데이터를 JSON 형식으로 출력하세요.

## 씬 분할 규칙
1. 전체 시를 자연스러운 의미 단위로 최대 10씬으로 분할하세요.
2. 각 씬은 2~4행 분량이 적절합니다. 시 전체 길이에 맞게 자동 조정하세요.
3. (중략) 표지는 별도 씬으로 처리하지 말고 앞 씬 끝에 포함하세요.
4. 출처([출처] 태그)와 각주([각주] 태그)는 씬에 포함하지 마세요.

## 각 씬 데이터 규칙
- original_text: 원문 그대로 (줄바꿈 \n 보존)
- modern_text: 현대어 구어체 번역 (CRITICAL: 반드시 일상 구어체, 문어체/경어 금지. 예시 금지: "임금님께서 정사를 돌보셨습니다." 예시 허용: "임금이 정사를 돌봤어. 나라가 조용하고 평화로웠지." 마침표로 종결되는 2~4개의 완결 문장으로 구성)
- narration: TTS용 낭독 대사 (modern_text 기반, 3~5문장, 자연스러운 구어체)
- emotion: 씬의 핵심 감정 한 단어 (예: 비장, 쾌활, 슬픔, 고독, 풍류, 억울, 유머)
- background: 씬의 배경 장소/상황 설명 (한국어 2~3문장, 이미지 생성 참고용)

## 역사적 배경 컨텍스트 활용 규칙
아래 역사적 배경이 제공되면 나레이션, 배경, 감정에 반영하세요:
- narration: 당시의 구체적 지역, 시대적 환경, 어려움을 자연스럽게 반영
- background: 함경도, 조선시대 등 지명/시대를 명시적으로 포함하여 작성
- emotion: 단순 상태(감사함)가 아닌 구체적 변화와 심리 상태 포착 (예: 의문→놀람→감사)
- image_prompt: 지역의 척박한 환경, 당시 의복, 계절감을 포함하여 작성

## 출력 형식
반드시 아래 JSON 형식만 출력하세요. 마크다운 코드블록, 설명 텍스트 절대 금지.
{
  "title": "시 제목 (원문에서 추출, 없으면 빈 문자열)",
  "author": "작가명 (없으면 빈 문자열)",
  "total_scenes": 씬 수 (정수),
  "scenes": [
    {
      "scene_index": 1,
      "original_text": "...",
      "modern_text": "...",
      "narration": "...",
      "emotion": "...",
      "background": "..."
    }
  ]
}"""

TRANSLATE_USER_PROMPT_PREFIX = '다음 고전시가 원문을 분석하여 씬 분할 및 현대어 번역 JSON을 생성하세요.'

# 이미지 프롬프트 생성 시스템 프롬프트
IMAGE_PROMPT_SYSTEM_PROMPT = """당신은 ComfyUI 이미지 생성 전문가입니다.
한국 고전시가 웹툰 영상을 위한 씬 이미지 프롬프트를 영어로 생성하세요.

## 프롬프트 생성 규칙
1. 출력은 반드시 영어 프롬프트 텍스트 한 줄만 출력하세요. JSON, 설명, 마크다운 금지.
2. 씬의 배경 장소, 계절/날씨, 등장인물 행동을 구체적으로 묘사하세요.
3. 감정(emotion)을 lighting과 color tone으로 표현하세요:
   - 비장/슬픔: dark blue tones, dramatic lighting, heavy atmosphere
   - 쾌활/유머: warm golden light, bright colors, lively atmosphere
   - 고독: muted tones, sparse composition, solitary figure
   - 풍류: soft natural light, flowing composition, poetic atmosphere
   - 억울: cold gray tones, tense atmosphere, low angle
4. 조선시대 배경을 유지하세요 (의복, 건물, 자연 환경).
5. 500 토큰 이내로 작성하세요."""

IMAGE_PROMPT_USER_PROMPT_PREFIX = """씬 정보:
- 감정: {emotion}
- 배경 설명 (한국어): {background}
- 현대어 내용: {modern_text}

위 씬에 맞는 ComfyUI 이미지 프롬프트를 영어로 생성하세요. 프롬프트만 출력하고 설명은 금지."""


# ===== 캐시 함수 =====

def get_cache_key(text: str) -> str:
  """텍스트 내용으로 캐시 키 생성 (SHA-256 앞 16자)"""
  normalized = ' '.join(text.split())
  return hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:16]


def get_cache_path(text: str) -> Path:
  """캐시 파일 경로 생성"""
  cache_key = get_cache_key(text)
  return CACHE_DIR / f'{cache_key}_nlp.json'


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


def get_context_cache_path(text: str) -> Path:
  """역사적 배경 캐시 경로 생성"""
  cache_key = get_cache_key(text)
  return CACHE_DIR / f'{cache_key}_context.txt'


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


def validate_scene(raw_scene: dict, idx: int, historical_context: str = '') -> dict:
  """씬 필드 유효성 검사 + 기본값 보완"""
  modern_text = raw_scene.get('modern_text', '')
  base = {
    'scene_index': raw_scene.get('scene_index', idx + 1),
    'original_text': raw_scene.get('original_text', ''),
    'modern_text': modern_text,
    'modern_sentences': split_into_sentences(modern_text),  # 신규: 문장 분리
    'sentence_image_prompts': [],  # 신규: 문장별 이미지 프롬프트
    'narration': raw_scene.get('narration', modern_text),
    'emotion': raw_scene.get('emotion', '미정'),
    'background': raw_scene.get('background', ''),
    'image_prompt': '',  # 하위호환: 첫 문장 프롬프트로 채움
    'historical_context': historical_context,
  }
  return base


# ===== HCX-005 API 호출 =====

@retry(
  stop=stop_after_attempt(3),
  wait=wait_exponential(multiplier=1, min=2, max=30),
  reraise=True,
)
def fetch_historical_context(raw_text: str) -> str:
  """HCX-005로 역사적 배경 조사 (캐시 지원)"""
  logger.info('역사적 배경 조사 시작...')

  cache_path = get_context_cache_path(raw_text)
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
      {'role': 'user', 'content': f'다음 고전시가의 역사적 배경을 요약해주세요:\n\n{raw_text}'},
    ],
    'max_tokens': 500,
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
  system_content = TRANSLATE_SYSTEM_PROMPT
  if historical_context.strip():
    system_content += f'\n\n## 역사적 배경 참고 (나레이션 작성 시 활용)\n{historical_context}'

  payload = {
    'model': 'HCX-005',
    'messages': [
      {
        'role': 'system',
        'content': system_content,
      },
      {
        'role': 'user',
        'content': f'{TRANSLATE_USER_PROMPT_PREFIX}\n\n{text}',
      },
    ],
    'max_tokens': 4000,
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
def call_hcx005_image_prompt(scene: dict) -> str:
  """HCX-005로 씬별 이미지 프롬프트 생성 (영문)"""
  logger.info('이미지 프롬프트 생성 중: 씬 %d', scene['scene_index'])

  api_key = os.environ.get('NCP_CLOVA_API_KEY')
  if not api_key:
    raise ValueError('NCP_CLOVA_API_KEY 환경변수가 설정되지 않았습니다.')

  # modern_text 앞 100자만 사용
  modern_text_summary = scene['modern_text'][:100]

  user_prompt = IMAGE_PROMPT_USER_PROMPT_PREFIX.format(
    emotion=scene['emotion'],
    background=scene['background'],
    modern_text_summary=modern_text_summary,
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
        'content': IMAGE_PROMPT_SYSTEM_PROMPT,
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
  task_id: str | None = None,
  use_cache: bool = True,
) -> tuple:
  """
  Step 1 NLP 메인 함수

  Args:
    extracted_raw_text: Step 0에서 나온 고전시가 원문
    task_id: 파이프라인 작업 ID (없으면 UUID 자동 생성)
    use_cache: 캐시 사용 여부

  Returns:
    (modern_script_data, image_prompts)
  """
  # 1. task_id 보장
  if not task_id:
    task_id = str(uuid.uuid4())
    logger.info('task_id 자동 생성: %s', task_id)

  # 2. 캐시 확인
  cache_path = get_cache_path(extracted_raw_text)
  if use_cache:
    cached = load_from_cache(cache_path)
    if cached is not None:
      logger.info('캐시된 결과 반환')
      return cached['modern_script_data'], cached['image_prompts']

  # 3. Notion: 파이프라인 시작 상태 업데이트
  update_notion_task_status(task_id, step=1, message='NLP 처리 시작', status='in_progress')

  try:
    # 4. 역사적 배경 조사 (선택)
    logger.info('역사적 배경 조사 시작')
    historical_context = fetch_historical_context(extracted_raw_text)

    # 5. HCX-005: 번역 + 씬 분할 (역사적 배경 주입)
    logger.info('번역 + 씬 분할 시작')
    translation_result = call_hcx005_translate(extracted_raw_text, historical_context)
    raw_scenes = translation_result.get('scenes', [])
    logger.info('씬 분할 완료: %d씬', len(raw_scenes))

    # 6. 씬 유효성 검사 (historical_context 주입)
    validated_scenes = [
      validate_scene(s, i, historical_context)
      for i, s in enumerate(raw_scenes)
    ]

    # 7. 각 씬의 문장별 이미지 프롬프트 생성
    image_prompts: list = []
    for i, scene in enumerate(validated_scenes):
      logger.info('문장별 이미지 프롬프트 생성 중: 씬 %d/%d (%d문장)', i + 1, len(validated_scenes), len(scene['modern_sentences']))
      sentence_prompts = []
      for sent_idx, sentence_text in enumerate(scene['modern_sentences']):
        # 씬 감정/배경 + 문장 텍스트를 조합하여 프롬프트 생성
        sentence_scene_ctx = {
          'emotion': scene['emotion'],
          'background': scene['background'],
          'modern_text': sentence_text,
        }
        try:
          prompt = call_hcx005_image_prompt(sentence_scene_ctx)
          final_prompt = f'{WEBTOON_STYLE_PREFIX}{prompt}'
        except Exception as e:
          logger.warning('씬 %d 문장 %d 프롬프트 생성 실패: %s', i + 1, sent_idx + 1, str(e))
          final_prompt = f'{WEBTOON_STYLE_PREFIX}Korean traditional scene, {scene["emotion"]} mood, historical atmosphere'
        sentence_prompts.append(final_prompt)
      scene['sentence_image_prompts'] = sentence_prompts
      # 하위호환성: 첫 문장 프롬프트를 scene['image_prompt']에도 유지
      scene['image_prompt'] = sentence_prompts[0] if sentence_prompts else ''
      image_prompts.append(scene['image_prompt'])

    modern_script_data = validated_scenes

    # 8. 캐시 저장 (use_cache 여부와 무관하게 항상 저장 — 하위 단계에서 파일 필요)
    save_to_cache(cache_path, {
      'modern_script_data': modern_script_data,
      'image_prompts': image_prompts,
    })

    # 9. Notion: poem_translation_log 기록
    log_to_notion_poem(extracted_raw_text, modern_script_data, task_id)

    # 10. Notion: 완료 상태 업데이트
    update_notion_task_status(
      task_id, step=1,
      message=f'NLP 처리 완료 ({len(modern_script_data)}씬)',
      status='completed',
    )

    logger.info('Step 1 NLP 완료. 씬 수: %d', len(modern_script_data))
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

  if len(sys.argv) < 2:
    # 인자 없으면 step0 캐시 파일 자동 사용
    cache_dir = Path('cache/step0')
    txt_files = list(cache_dir.glob('*_ocr.txt'))
    if not txt_files:
      print('사용법: python step1_nlp.py <원문텍스트_또는_파일경로>')
      sys.exit(1)
    input_text = txt_files[0].read_text(encoding='utf-8')
    logger.info('Step 0 캐시에서 텍스트 자동 로드: %s', txt_files[0])
  else:
    # 파일 경로가 주어지면 파일 읽기, 아니면 직접 텍스트로 처리
    arg = sys.argv[1]
    if Path(arg).exists():
      input_text = Path(arg).read_text(encoding='utf-8')
      logger.info('파일에서 텍스트 로드: %s', arg)
    else:
      input_text = arg

  try:
    script_data, prompts = process_nlp(input_text)
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
