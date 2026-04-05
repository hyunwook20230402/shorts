"""
Step 1: NLP — 고전시가 원문 현대어 번역 + 씬 분할 + 이미지 프롬프트 생성

입력: extracted_raw_text (str)
출력: modern_script_data (list[dict]) — 각 씬의 image_prompt는 modern_script_data[i]['image_prompt']에 저장
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
  DEFAULT_EMOTION,
  DEFAULT_THEME,
  EMOTION_CATALOG,
  THEME_CATALOG,
  THEME_IMAGE_STYLE_GUIDE,
  get_emotion_image_tone,
  get_theme_classification_prompt,
  map_scene_emotion_to_code,
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



def extract_original_lines(text: str) -> list[str]:
  """OCR 원문에서 실제 구절 행 목록 추출. 빈 줄과 '---' 구분자 제외."""
  return [ln.strip() for ln in text.splitlines() if ln.strip() and ln.strip() != '---']


translate_system_prompt = """당신은 한국 고전시가 분석가이자 웹툰 쇼츠 대본 작가입니다.
입력된 시구 1행을 분석하여 씬 1개 JSON을 출력하세요.

## 규칙
1. 반드시 씬 1개만 출력. 여러 씬 출력 금지.
2. emotion: **한국어** 핵심 감정 한 단어 (예: 비장, 쾌활, 슬픔, 고독)
3. main_focus: 이미지에 반드시 포함해야 할 구성 요소를 배열로 선택. 최소 1개, 해당하는 것 모두 선택.
   - "background": 자연경관·건축·계절·날씨 등 배경 요소가 이미지에 중요한 경우
   - "character": 인물의 행동·표정·자세가 이미지에 중요한 경우
   - "object": 특정 사물(술잔, 가야금, 칼, 깃발 등)이 이미지 주제에 중요한 경우
   - 예: 산속에서 술을 마시는 인물 → ["background","character","object"]
   - 예: 달빛 연못 풍경만 → ["background"]
4. scene_description: 분석할 행 장면의 핵심 시각 요소를 **영어** 키워드/구절로 묘사 (60토큰 이내). main_focus에 포함된 모든 요소(배경장소,계절,시간,날씨,인물 행동,표정,사물)를 포함.

## 출력 형식 (JSON만 출력, 설명 금지)
{{"original_text":"...","emotion":"...","main_focus":[...],"scene_description":"..."}}
"""

translate_user_prompt_prefix = '[분석할 시구 1행]\n{line}'

image_prompt_system_prompt = """당신은 ComfyUI 이미지 생성 전문가입니다.
한국 고전시가 웹툰 영상을 위한 씬 이미지 프롬프트를 영어로 생성하세요.

## 프롬프트 생성 규칙
1. main_focus에 포함된 모든 구성 요소를 image_prompt에 반드시 반영하세요.
   - "character" 포함: 원문에 명시된 인물의 행동·자세·표정을 묘사하세요.
   - "character" 미포함: 인물을 그리지 마세요.
   - "object" 포함: 해당 사물을 이미지의 주요 구도(전경 또는 중앙)에 배치하세요.
   - "background" 포함: 배경 장소·계절·시간·날씨를 구체적으로 묘사하세요.
   - 복수 요소 포함 시: 모든 요소가 한 장면에 자연스럽게 어우러지도록 구성하세요.

   조합별 구성 가이드:
   ["background"]              → 자연물·경관 단독 묘사
   ["character"]               → 인물 자세·표정·행동 중심
   ["object"]                  → 사물을 전경 중앙에 배치한 정물 구도
   ["background","object"]     → 사물 전경 + 배경 후경
   ["object","character"]      → 인물이 사물을 다루는 장면 (사물+인물 동작 모두)
   ["background","character"]  → 배경 후경 + 인물 중경/전경
   ["background","character","object"] → 배경+인물+사물 세 요소 모두 통합

   원문에 자연물이 여러 개 등장하면 모두 이미지에 포함하세요.
   예: "달이 그림자 내린 연못" → 달이 하늘에 떠 있고 달빛이 연못 수면에 반사된 구도.

2. 씬의 배경 장소, 계절/날씨/시간(낮,밤,새벽)를 구체적으로 묘사하세요.

3. 감정(emotion)을 lighting과 color tone으로 표현하세요. 만약 인물이 있다면 행동/자세/표정에 반영하세요.
   - 분노/원망: cold stark lighting, sharp tense shadows, oppressive heavy clouds
   - 자긍심: warm earthy tones, steady calm lighting
   - 희망/기쁨: bright green/gold tones, warm open sunlight, lively atmosphere
   - 호소/슬픔: misty soft atmosphere, gray overcast sky
   - 고단함: muted gray-blue tones, heavy damp atmosphere
   - 비장: dramatic chiaroscuro, deep saturated tones

4. **시대 일관성 (필수)**: 모든 물건, 도구, 건축물, 의복은 반드시 한국 전근대(삼국~조선, ~1897) 양식만 허용.
   - 허용: 초가집, 기와집, 한옥, 호미, 낫, 쟁기, 삿갓, 갓, 도포, 철갑, 가야금 등 전통 물건
   - 절대 금지: 우산, 안경, 트랙터, 자동차, 유리창, 콘크리트, 전봇대, 현대 가구, 서양식 건물 등 근현대(1900년 이후) 물건
   - 비/눈 장면: 비/눈 내리는 묘사를 포함하세요. 우산(umbrella/parasol) 절대 금지.
   - 서양 문물 혼합 금지: 동서양 시대 혼합 절대 불가.

5. image_prompt는 200 토큰 이내로 작성하세요.

6. 테마 스타일 가이드(theme_style_guide)는 색감과 조명에만 참고하세요.
   - 테마 가이드의 특정 소품(예: "distant palace", "temple")을 원문에 언급이 없는데 이미지 주요 소재로 삽입하지 마세요.

7. 정서 톤(emotion_tone)은 조명과 색감에만 반영하세요.

8. 우선순위 (반드시 준수):
   ① main_focus 구성 요소 모두 반영 (원문이 곧 이미지의 주제)
   
   ② 시대 일관성 (한국 전근대 양식만)
   
   ③ 씬의 계절(봄여름가을겨울) / 날씨 / 장소(한국 전근대적 장소) / 시간(낮,밤,새벽)

   ④ 정서 톤 (조명·색감에만 반영)
   
   ⑤ 테마 스타일 가이드 (색감 힌트만, 소품 삽입 금지)

## pose_type 분류 규칙 — main_focus에 "character"가 포함된 씬에만 적용
원문의 행동 동사를 참고해 아래 중 가장 적합한 pose_type을 선택하세요:

### 구체적 동작이 있는 경우:
- prone: 엎드림/납작 엎드린 자세 (논바닥에 엎드려, 절하며 엎드림)
- kneeling: 무릎 꿇기/고개 숙여 아뢰는 자세
- sitting_scholar: 앉아서 글 읽기/사색/학문/음주
- walking_journey: 걷기/여행/유배/길을 떠나는 장면
- riding_horse: 말 타고 달리는/행군하는 장면
- dancing: 춤추는/무용하는 장면
- plowing_farming: 밭 갈기/농사짓는 장면
- boating: 배 타고 물 위에 있는 장면
- fishing_resting: 낚시/강변에 앉아 쉬는 은거 장면
- playing_instrument: 거문고/피리 등 악기 연주
- archery_martial: 활 쏘기/무예 장면

### 인원/구도 중심:
- standing_single: 한 인물이 서 있음 (홀로 바라보는 장면)
- standing_confrontation: 두 인물 이상 대립 구도 (농부 vs 관리, 신하 vs 임금)
- group_labor: 여럿이 함께 일하는 군상 (농부들, 공역)
- group_celebration: 여럿이 모인 잔치/축제/연회
- embrace_grief: 슬픔/그리움/애도/이별 동작
- gazing_distant: 먼 곳을 바라보는/조망하는 장면

### 구체적 신체 동작보다 감정 표현이 중심인 장면:
- expressive: 화자의 주장, 선언, 감정 토로, 상황 설명 등 구체적 신체 동작 없이 감정이 중심인 장면
  → 인물의 표정·몸짓·제스처로 감정을 표현하세요.
  예) "그대들의 부귀 호사 우리 농부로부터 나오나니" → 화자(농부)가 말하고 있는 장면
      "아전들은 벌써부터 조세 거둔다고 성화세" → 아전들이 독촉하고 있는 장면
      "임금을 그리워하매 눈물이 절로 난다" → 화자가 울고 있는 장면

## 출력 형식 (엄격히 준수)
- 줄1: 영어 프롬프트 텍스트만 출력. 라벨(예: "Image Prompt:", "[image_prompt]") 절대 금지.
- 줄2 (main_focus에 "character" 포함 시에만): pose_type: [위 목록 중 1개]
- main_focus에 "character"가 없으면 pose_type 출력 금지.
- 출력 예시:
  A solitary pine cone rests on autumn ground, fallen leaves surrounding it under cool gray overcast sky.
  (인물 없으므로 pose_type 줄 없음)"""

image_prompt_user_prompt_prefix = """씬 정보:
- 원문 (이미지의 핵심 주제): {original_text}
- 감정: {emotion}
- 장면 묘사 (배경/인물/사물 영어 키워드): {scene_description}
- 구성 요소 (복수 가능): {main_focus_str}
  (포함된 모든 요소를 이미지에 자연스럽게 통합하세요)
- 테마 색감 가이드 (시 전체 색감/조명 참고용): {theme_style_guide}
- 지배적 정서 톤 (시 전체 조명/색감에만 참고로 반영): {emotion_tone}

위 출력 형식에 따라 생성하세요."""


# ===== 캐시 함수 =====

def get_cache_key(text: str) -> str:
  """텍스트 내용으로 캐시 키 생성 (SHA-256 앞 16자)"""
  normalized = ' '.join(text.split())
  return hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:16]


def get_cache_path(poem_dir: Path) -> Path:
  """캐시 파일 경로 생성"""
  return poem_dir / 'step1' / 'nlp.json'


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
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    logger.info('NLP 결과 캐시 저장: %s', cache_path)
  except Exception as e:
    logger.error('캐시 저장 실패: %s', str(e))
    raise




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


def try_recover_truncated_json(text: str) -> dict | None:
  """잘린 JSON에서 마지막 완전한 scene 객체까지 복구"""
  # 마지막 완전한 } 위치부터 역방향으로 시도
  pos = len(text)
  while pos > 0:
    pos = text.rfind('}', 0, pos)
    if pos == -1:
      break
    candidate = text[:pos + 1]
    # scenes 배열과 루트 객체 닫기
    candidate = re.sub(r',?\s*$', '', candidate) + ']}'
    try:
      result = json.loads(candidate)
      if result.get('scenes'):
        logger.info('잘린 JSON 복구 성공: %d개 씬', len(result['scenes']))
        return result
    except json.JSONDecodeError:
      pass
  return None


def safe_parse_json(text: str) -> dict:
  """JSON 파싱 + 복구 (trailing comma 제거, 잘린 JSON 복구)"""
  cleaned = strip_code_fence(text)
  # LLM이 {{...}} 이중 중괄호로 출력하는 경우 단일 중괄호로 변환
  cleaned = cleaned.replace('{{', '{').replace('}}', '}')
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
      # 잘린 JSON 복구 시도
      logger.warning('잘린 JSON 복구 시도...')
      recovered = try_recover_truncated_json(cleaned)
      if recovered:
        return recovered
      logger.error('JSON 파싱 최종 실패. 원본 응답: %s', text[:500])
      raise ValueError(f'LLM 응답 JSON 파싱 불가: {str(e2)}') from e2






def validate_scene(raw_scene: dict, idx: int) -> dict:
  """
  씬 데이터 유효성 검사 및 정규화.

  불변 조건: 1씬 = 1행 = 1문장 (original_text가 원래 1행이므로 자동 보장)
  """
  # main_focus: 리스트 보장 + 구버전 문자열 캐시 호환
  raw_focus = raw_scene.get('main_focus', ['background'])
  if isinstance(raw_focus, str):
    raw_focus = [raw_focus]
  valid_focuses = {'background', 'character', 'object'}
  main_focus = [f for f in raw_focus if f in valid_focuses] or ['background']

  base = {
    'scene_index': idx + 1,
    'original_text': raw_scene.get('original_text', ''),
    'emotion': raw_scene.get('emotion', '미정'),
    'main_focus': main_focus,
    'scene_description': raw_scene.get('scene_description', 'traditional Korean landscape'),
    'image_prompt': '',
    'pose_type': '',  # 인물 없는 씬은 빈 문자열 유지
  }
  return base


# ===== HCX-005 API 호출 =====

@retry(
  stop=stop_after_attempt(3),
  wait=wait_exponential(multiplier=1, min=2, max=30),
  reraise=True,
)
def call_hcx005_analyze_line(line: str) -> dict:
  """HCX-005로 시구 1행 → 씬 dict 1개 분석 (emotion, main_focus, scene_description 추출)"""
  logger.info('HCX-005 행 분석 호출: %s', line[:30])

  api_key = os.environ.get('NCP_CLOVA_API_KEY')
  if not api_key:
    raise ValueError('NCP_CLOVA_API_KEY 환경변수가 설정되지 않았습니다.')

  user_content = translate_user_prompt_prefix.format(line=line)

  headers = {
    'Authorization': f'Bearer {api_key}',
    'Content-Type': 'application/json',
  }

  payload = {
    'model': 'HCX-005',
    'messages': [
      {'role': 'system', 'content': translate_system_prompt},
      {'role': 'user', 'content': user_content},
    ],
    'max_tokens': 512,
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
    logger.info('HCX-005 행 분석 응답 수신, JSON 파싱 중...')
    parsed = safe_parse_json(response_text)
    parsed['original_text'] = line  # 원문 행 강제 보장
    return parsed

  except requests.exceptions.RequestException as e:
    logger.error('HCX-005 행 분석 API 호출 실패: %s', str(e))
    try:
      error_detail = e.response.text if hasattr(e, 'response') else ''
      if error_detail:
        logger.error('응답 본문: %s', error_detail)
    except Exception:
      pass
    raise RuntimeError(f'HCX-005 행 분석 중 오류 발생: {str(e)}') from e


@retry(
  stop=stop_after_attempt(3),
  wait=wait_exponential(multiplier=1, min=2, max=30),
  reraise=True,
)
def call_hcx005_classify_theme(raw_text: str) -> dict:
  """HCX-005로 테마/정서 분류 (Step 1_1). OCR 원문 전체 입력, 1회 호출."""
  logger.info('HCX-005 테마/정서 분류 API 호출 중 (Step 1_1)...')

  api_key = os.environ.get('NCP_CLOVA_API_KEY')
  if not api_key:
    raise ValueError('NCP_CLOVA_API_KEY 환경변수가 설정되지 않았습니다.')

  headers = {
    'Authorization': f'Bearer {api_key}',
    'Content-Type': 'application/json',
  }

  payload = {
    'model': 'HCX-005',
    'messages': [
      {
        'role': 'system',
        'content': get_theme_classification_prompt(),
      },
      {
        'role': 'user',
        'content': (
          f'다음 고전시가 원문의 테마와 지배적 정서를 분류하세요.\n\n{raw_text}\n\n'
          '또한 이 시의 제목과 작자를 JSON에 "title"과 "author" 필드로 포함하세요. 미상이면 "미상"으로 작성.'
        ),
      },
    ],
    'max_tokens': 512,
    'temperature': 0.1,
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
    parsed = safe_parse_json(response_text)

    logger.info(
      '테마/정서 분류 완료: primary=%s, surface=%s, emotion=%s',
      parsed.get('primary_theme', '?'),
      parsed.get('surface_theme', '?'),
      parsed.get('dominant_emotion', '?'),
    )
    return parsed

  except requests.exceptions.RequestException as e:
    logger.error('HCX-005 테마 분류 API 호출 실패: %s', str(e))
    raise RuntimeError(f'HCX-005 테마 분류 중 오류 발생: {str(e)}') from e


VALID_POSE_TYPES = {
  'prone', 'kneeling', 'standing_single', 'standing_confrontation',
  'group_labor', 'group_celebration', 'sitting_scholar',
  'walking_journey', 'embrace_grief', 'gazing_distant',
  'riding_horse', 'dancing', 'plowing_farming', 'boating',
  'fishing_resting', 'playing_instrument', 'archery_martial',
  'expressive',
}


@retry(
  stop=stop_after_attempt(3),
  wait=wait_exponential(multiplier=1, min=2, max=30),
  reraise=True,
)
def call_hcx005_image_prompt(
  scene: dict,
  theme_code: str = DEFAULT_THEME,
  emotion_code: str = DEFAULT_EMOTION,
) -> tuple[str, str]:
  """HCX-005로 씬별 이미지 프롬프트 + pose_type 동시 생성.
  반환: (prompt_text, pose_type)
  """
  logger.info('이미지 프롬프트 생성 중: 씬 %d (테마: %s, 정서: %s)', scene['scene_index'], theme_code, emotion_code)

  api_key = os.environ.get('NCP_CLOVA_API_KEY')
  if not api_key:
    raise ValueError('NCP_CLOVA_API_KEY 환경변수가 설정되지 않았습니다.')

  style_guide = THEME_IMAGE_STYLE_GUIDE.get(theme_code, '')
  emotion_tone = get_emotion_image_tone(emotion_code)

  # main_focus 리스트 → 문자열 변환 (구버전 문자열 캐시 호환)
  main_focus_val = scene.get('main_focus', ['background'])
  if isinstance(main_focus_val, list):
    main_focus_str = ', '.join(main_focus_val)
  else:
    main_focus_str = main_focus_val

  user_prompt = image_prompt_user_prompt_prefix.format(
    original_text=scene.get('original_text', ''),
    emotion=scene['emotion'],
    scene_description=scene.get('scene_description', 'traditional Korean landscape'),
    main_focus_str=main_focus_str,
    theme_style_guide=style_guide,
    emotion_tone=emotion_tone,
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
    raw = result.get('choices', [{}])[0].get('message', {}).get('content', '').strip()

    # 줄 파싱 + pose_type 오염 방어
    # "character" 미포함 씬은 LLM이 pose_type 줄을 출력하지 않으므로 기본값 빈 문자열
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    pose_type = ''  # 기본값: 인물 없는 씬은 빈 문자열
    prompt_lines = []
    # LLM이 붙이는 라벨 패턴 제거: "[Image Prompt]:", "[image_prompt]", "Image Prompt:" 등
    label_pattern = re.compile(r'^\[?image[_ ]prompt\]?:?\s*', re.IGNORECASE)
    for line in lines:
      line = label_pattern.sub('', line)  # 라벨 제거
      m = re.search(r'pose[_ ]type:?\s*(\w+)', line, re.IGNORECASE)
      if m:
        candidate = m.group(1).strip()
        if candidate in VALID_POSE_TYPES:
          pose_type = candidate
        else:
          logger.warning('알 수 없는 pose_type: %s, 기본값 사용', candidate)
        # pose_type 부분을 프롬프트에서 제거 (대/소문자, 공백, 마침표 모두 처리)
        cleaned = re.sub(r',?\s*pose[_ ]type:?\s*\w+\.?', '', line, flags=re.IGNORECASE).strip().rstrip(',').strip()
        if cleaned:
          prompt_lines.append(cleaned)
      else:
        prompt_lines.append(line)
    prompt_text = prompt_lines[0] if prompt_lines else ''

    logger.info('씬 %d 프롬프트 생성 완료 (%d자, pose=%s)', scene['scene_index'], len(prompt_text), pose_type)
    return prompt_text, pose_type

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
    # 씬 전체 원문을 합쳐서 하나의 레코드로 저장
    modern_combined = '\n\n'.join(s['original_text'] for s in modern_scenes)

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
    (modern_script_data, image_prompts) — image_prompts는 modern_script_data[i]['image_prompt'] 목록
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
      # 오래된 캐시 호환: primary_theme/dominant_emotion 없으면 보충 후 재저장
      needs_save = False
      if 'primary_theme' not in cached:
        old_theme = cached.get('theme', DEFAULT_THEME)
        cached['primary_theme'] = old_theme
        cached['primary_theme_en'] = THEME_CATALOG.get(old_theme, THEME_CATALOG[DEFAULT_THEME])['en']
        cached['surface_theme'] = old_theme
        cached['surface_theme_en'] = cached['primary_theme_en']
        needs_save = True
        logger.info('캐시에 primary/surface_theme 필드 보충: %s', old_theme)
      if 'dominant_emotion' not in cached:
        cached['dominant_emotion'] = DEFAULT_EMOTION
        cached['dominant_emotion_en'] = EMOTION_CATALOG[DEFAULT_EMOTION]['en']
        needs_save = True
        logger.info('캐시에 dominant_emotion 필드 보충: %s', DEFAULT_EMOTION)
      if needs_save:
        save_to_cache(cache_path, cached)
      logger.info('캐시된 결과 반환')
      script_data = cached['modern_script_data']
      prompts = [s.get('image_prompt', '') for s in script_data]
      return script_data, prompts

  # 3. Notion: 파이프라인 시작 상태 업데이트
  update_notion_task_status(task_id, step=1, message='NLP 처리 시작', status='in_progress')

  try:
    # --- Step 1_1: HCX-005 테마/정서 분류 (원문 전체, 1회) ---
    logger.info('Step 1_1: 테마/정서 분류 시작')
    theme_result = call_hcx005_classify_theme(extracted_raw_text)

    theme_reasoning = theme_result.get('theme_reasoning', '')
    emotion_reasoning = theme_result.get('emotion_reasoning', '')
    if theme_reasoning:
      logger.info('테마 판단 근거: %s', theme_reasoning)
    if emotion_reasoning:
      logger.info('정서 판단 근거: %s', emotion_reasoning)

    primary_theme = DEFAULT_THEME
    surface_theme = DEFAULT_THEME
    primary_theme_en = THEME_CATALOG[DEFAULT_THEME]['en']
    surface_theme_en = THEME_CATALOG[DEFAULT_THEME]['en']
    dominant_emotion = DEFAULT_EMOTION
    dominant_emotion_en = EMOTION_CATALOG[DEFAULT_EMOTION]['en']

    raw_primary = theme_result.get('primary_theme', DEFAULT_THEME)
    raw_surface = theme_result.get('surface_theme', raw_primary)
    if raw_primary in THEME_CATALOG:
      primary_theme = raw_primary
      primary_theme_en = THEME_CATALOG[primary_theme]['en']
    else:
      logger.warning('알 수 없는 primary_theme 코드: %s, fallback: %s', raw_primary, DEFAULT_THEME)
    if raw_surface in THEME_CATALOG:
      surface_theme = raw_surface
      surface_theme_en = THEME_CATALOG[surface_theme]['en']
    else:
      logger.warning('알 수 없는 surface_theme 코드: %s, fallback: primary', raw_surface)
      surface_theme = primary_theme
      surface_theme_en = primary_theme_en
    raw_emo = theme_result.get('dominant_emotion', DEFAULT_EMOTION)
    if raw_emo in EMOTION_CATALOG:
      dominant_emotion = raw_emo
      dominant_emotion_en = EMOTION_CATALOG[raw_emo]['en']
    else:
      logger.warning('알 수 없는 dominant_emotion 코드: %s, fallback: %s', raw_emo, DEFAULT_EMOTION)

    logger.info(
      'Step 1_1 완료: primary=%s(%s), surface=%s(%s), emotion=%s',
      primary_theme, THEME_CATALOG[primary_theme]['ko'],
      surface_theme, THEME_CATALOG[surface_theme]['ko'],
      dominant_emotion,
    )

    # title/author: Step 1_1 테마 분류 응답에서 추출
    title = theme_result.get('title', '미상')
    author = theme_result.get('author', '미상')

    # --- Step 1_2: HCX-005 분석 (행별 개별 호출, 1행=1씬 보장) ---
    original_lines = extract_original_lines(extracted_raw_text)
    logger.info('Step 1_2: %d행 개별 분석 시작', len(original_lines))
    raw_scenes = []
    for line_idx, line in enumerate(original_lines):
      logger.info('행 %d/%d 분석 중: %s', line_idx + 1, len(original_lines), line[:20])
      scene_dict = call_hcx005_analyze_line(line)
      scene_dict['scene_index'] = line_idx + 1
      raw_scenes.append(scene_dict)
    logger.info('Step 1_2 완료: %d씬', len(raw_scenes))

    validated_scenes = [validate_scene(s, i) for i, s in enumerate(raw_scenes)]

# 7. 각 씬(문장)의 이미지 프롬프트 생성
    for i, scene in enumerate(validated_scenes):
        # ✅ 체크 1: 루프의 인덱스(i)를 사용하여 강제로 순차적인 씬 번호 부여
        current_scene_idx = i + 1
        logger.info(f'이미지 프롬프트 생성 중: 씬 {current_scene_idx}/{len(validated_scenes)}')
        
        sentence_scene_ctx = {
            'scene_index': current_scene_idx,
            'original_text': scene.get('original_text', ''),
            'emotion': scene.get('emotion', 'serene'),
            'scene_description': scene.get('scene_description', 'traditional Korean landscape'),
            'main_focus': scene.get('main_focus', 'background'),
        }
        
        try:
            # 씬별 감정 → 정서 코드 매핑 (dominant_emotion은 fallback)
            scene_emotion = scene.get('emotion', '')
            scene_emotion_code = map_scene_emotion_to_code(scene_emotion, dominant_emotion)
            # LLM 호출하여 영문 프롬프트 + pose_type 동시 생성
            prompt_text, pose_type = call_hcx005_image_prompt(sentence_scene_ctx, surface_theme, scene_emotion_code)
            final_prompt = f"{prompt_text}, {webtoon_style_prefix.rstrip(', ')}"
        except Exception as e:
            logger.warning(f"씬 {current_scene_idx} 프롬프트 생성 실패, fallback 적용: {e}")
            curr_emotion = scene.get('emotion', 'serene')
            final_prompt = f"({curr_emotion} mood:1.3), Korean traditional scene, {webtoon_style_prefix.rstrip(', ')}"
            pose_type = 'standing_single'

        # 1씬 1문장 원칙에 따라 데이터 구조 확정
        scene['scene_index'] = current_scene_idx
        scene['image_prompt'] = final_prompt
        scene['pose_type'] = pose_type

    # 8. 데이터 통합 및 단일 캐시 파일 저장 (Step 2~6 연결용)
    modern_script_data = validated_scenes

    save_to_cache(cache_path, {
        'theme_reasoning': theme_reasoning,
        'emotion_reasoning': emotion_reasoning,
        'surface_theme': surface_theme,
        'surface_theme_en': surface_theme_en,
        'primary_theme': primary_theme,
        'primary_theme_en': primary_theme_en,
        'dominant_emotion': dominant_emotion,
        'dominant_emotion_en': dominant_emotion_en,
        'modern_script_data': modern_script_data,
        'title': title,
        'author': author,
    })

    # 10. Notion: 기록 및 상태 업데이트
    log_to_notion_poem(extracted_raw_text, modern_script_data, task_id)
    update_notion_task_status(
        task_id, step=1,
        message=f'NLP 처리 완료 ({len(modern_script_data)}씬)',
        status='completed',
    )

    logger.info('Step 1 NLP 완료. 씬 수: %d, 파일 저장: %s', len(modern_script_data), cache_path)
    prompts = [s.get('image_prompt', '') for s in modern_script_data]
    return modern_script_data, prompts

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
      # poem_dir/step0/ocr.txt에서 OCR 텍스트 로드
      ocr_file = poem_dir / 'step0' / 'ocr.txt'
      if ocr_file.exists():
        input_text = ocr_file.read_text(encoding='utf-8')
        poem_id = poem_dir.name  # "poem_01", "poem_02" 등
        logger.info(f'poem_dir에서 OCR 텍스트 로드: {ocr_file} (poem_id: {poem_id})')
      else:
        logger.error('Step 0 캐시 파일 없음: %s', ocr_file)
        logger.error('힌트: Step 0 실행 시 같은 poem_dir을 사용했는지 확인하세요.')
        logger.error('  예: python step0_ocr.py 이미지.png "cache/poem_01"')
        logger.error('  예: python step1_nlp.py "cache/poem_01"')
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
    print('\n=== 이미지 프롬프트 샘플 ===')
    if prompts:
      print(f'씬 1: {prompts[0][:120]}...')
    print('========================\n')
  except (ValueError, RuntimeError) as e:
    logger.error('실행 실패: %s', str(e))
    sys.exit(1)


