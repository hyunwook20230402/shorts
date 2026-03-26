"""
Step 0: OCR — 고전시가 이미지에서 원문 텍스트 추출

입력: 이미지 파일 경로 (PNG/JPG)
출력: extracted_raw_text (str)
"""

import base64
import json
import logging
import os
import uuid
from pathlib import Path

import requests
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()

# 로거 설정
logger = logging.getLogger(__name__)
logging.basicConfig(
  level=logging.INFO,
  format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)

# 캐시 디렉토리
CACHE_DIR = Path('cache/step0')
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# HCX-005 OCR 프롬프트
OCR_SYSTEM_PROMPT = """당신은 한국 고전시가(시조, 향가, 가사, 경기체가 등) 전문 해독 AI입니다.
이미지에 인쇄된 텍스트를 있는 그대로 정확하게 전사(轉寫)하세요.

규칙:
1. 원문 텍스트만 추출하세요. 해석, 현대어 풀이, 설명을 절대 덧붙이지 마세요.
2. 고전 한글 철자(예: ㅿ, ㆁ, ㆍ 등 옛글자 포함)를 현대어로 바꾸지 말고 이미지에 보이는 글자 그대로 옮기세요.
3. 한자는 이미지에 있는 그대로 포함하세요. 임의로 괄호 설명을 추가하지 마세요.
4. ①②③ 같은 편집자 주석 기호는 제거하세요.
5. (가), (나), (중략) 같은 구조 표지는 그대로 유지하세요.
6. **이미지의 행 구조를 정확히 보존하세요.** 각 줄이 나뉘면 개행(\\n)으로 구분하세요. 절대 한 줄로 이어쓰지 마세요.
7. 작가명·출처·각주가 있으면 본문 뒤에 [출처] 태그와 [각주] 태그로 구분하세요.
   예) [출처] 구암, 『청색곡』
       [각주] * 이사가 고운 원을 파면하고...
8. 마크다운 코드블록(```)으로 감싸지 마세요.
9. 이미지에 텍스트가 없거나 읽을 수 없으면 빈 문자열을 반환하세요.
"""

OCR_USER_PROMPT = '이미지에 인쇄된 고전시가 원문 텍스트를 위 규칙에 따라 전사해주세요. 특히 이미지의 행 구조를 정확히 보존하세요.'


def encode_image_to_base64(image_path: str) -> str:
  """이미지 파일을 base64 문자열로 인코딩"""
  with open(image_path, 'rb') as f:
    return base64.b64encode(f.read()).decode('utf-8')


def get_image_media_type(image_path: str) -> str:
  """파일 확장자로 MIME 타입 반환"""
  ext = Path(image_path).suffix.lower()
  media_types = {
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.webp': 'image/webp',
    '.gif': 'image/gif',
  }
  return media_types.get(ext, 'image/jpeg')


def get_cache_path(image_path: str) -> Path:
  """이미지 경로로 캐시 파일 경로 생성"""
  image_name = Path(image_path).stem
  return CACHE_DIR / f'{image_name}_ocr.txt'


def load_from_cache(cache_path: Path) -> str | None:
  """캐시 파일이 존재하면 내용을 반환, 없으면 None"""
  if cache_path.exists():
    logger.info('캐시에서 OCR 결과 로드: %s', cache_path)
    return cache_path.read_text(encoding='utf-8')
  return None


def save_to_cache(cache_path: Path, text: str) -> None:
  """OCR 결과를 캐시 파일에 저장 (UTF-8)"""
  try:
    cache_path.write_text(text, encoding='utf-8')
    logger.info('OCR 결과 캐시 저장: %s', cache_path)
  except UnicodeEncodeError:
    # Windows cp949 폴백 처리 (드물지만)
    cache_path.write_text(text, encoding='utf-8', errors='replace')
    logger.warning('유니코드 문자가 포함되어 일부 처리됨: %s', cache_path)


@retry(
  stop=stop_after_attempt(3),
  wait=wait_exponential(multiplier=1, min=2, max=30),
  reraise=True,
)
def call_hcx005_ocr(image_base64: str, media_type: str) -> str:
  """HCX-005 OpenAI 호환 API 호출 (retry 3회 + 지수 백오프)"""
  logger.info('HCX-005 OCR API 호출 중...')

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
        'content': OCR_SYSTEM_PROMPT,
      },
      {
        'role': 'user',
        'content': [
          {
            'type': 'image_url',
            'image_url': {
              'url': f'data:{media_type};base64,{image_base64}',
            },
          },
          {
            'type': 'text',
            'text': OCR_USER_PROMPT,
          },
        ],
      },
    ],
    'max_tokens': 3000,
    'temperature': 0,
  }

  try:
    response = requests.post(
      'https://clovastudio.stream.ntruss.com/v1/openai/chat/completions',
      headers=headers,
      json=payload,
      timeout=60,
    )
    response.raise_for_status()

    result = response.json()
    extracted_text = result.get('choices', [{}])[0].get('message', {}).get('content', '')

    logger.info('OCR 완료. 추출된 텍스트 길이: %d자', len(extracted_text))
    return extracted_text

  except requests.exceptions.RequestException as e:
    logger.error('HCX-005 API 호출 실패: %s', str(e))
    try:
      error_detail = e.response.text
      logger.error('응답 본문: %s', error_detail)
    except:
      pass
    raise RuntimeError(f'HCX-005 API 호출 중 오류 발생: {str(e)}') from e


def postprocess_ocr_text(text: str) -> str:
  """OCR 결과 후처리 — 코드펜스 제거, 주석 기호 제거, 연속 빈 줄 정리"""
  import re
  # 모델이 감싸는 마크다운 코드펜스 제거
  text = re.sub(r'^```[^\n]*\n', '', text)
  text = re.sub(r'\n```$', '', text)
  text = text.strip('`').strip()
  # ①②③...⑳ 편집자 주석 기호 제거 (앞뒤 공백 포함)
  text = re.sub(r'\s*[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]\s*', ' ', text)
  # 연속 공백 정리
  text = re.sub(r'[ \t]{2,}', ' ', text)
  # 연속 빈 줄 3개 이상 → 2개로 정리
  text = re.sub(r'\n{3,}', '\n\n', text)
  return text.strip()


def extract_text_from_image(image_path: str, use_cache: bool = True) -> str:
  """
  고전시가 이미지에서 원문 텍스트 추출 (Step 0 메인 함수)

  Args:
    image_path: 이미지 파일 경로 (PNG/JPG)
    use_cache: 캐시 사용 여부 (기본값: True)

  Returns:
    extracted_raw_text: 추출된 원문 텍스트

  Raises:
    FileNotFoundError: 이미지 파일이 없을 때
    ValueError: API 키가 설정되지 않았을 때
    RuntimeError: OCR 처리 실패 시
  """
  # 이미지 파일 존재 확인
  if not Path(image_path).exists():
    raise FileNotFoundError(f'이미지 파일을 찾을 수 없습니다: {image_path}')

  # API 키 확인 (실제 호출은 call_hcx005_ocr 내부에서 검증)
  ncp_api_key = os.environ.get('NCP_CLOVA_API_KEY')
  if not ncp_api_key:
    raise ValueError('NCP_CLOVA_API_KEY 환경변수가 설정되지 않았습니다.')

  # 캐시 확인
  cache_path = get_cache_path(image_path)
  if use_cache:
    cached_text = load_from_cache(cache_path)
    if cached_text is not None:
      return cached_text

  logger.info('OCR 처리 시작: %s', image_path)

  try:
    # 이미지 인코딩
    image_base64 = encode_image_to_base64(image_path)
    media_type = get_image_media_type(image_path)

    # HCX-005 OCR 호출
    extracted_raw_text = call_hcx005_ocr(image_base64, media_type)

    # 후처리
    extracted_raw_text = postprocess_ocr_text(extracted_raw_text)

    # 캐시 저장
    if use_cache:
      save_to_cache(cache_path, extracted_raw_text)

    return extracted_raw_text

  except FileNotFoundError:
    raise
  except ValueError:
    raise
  except Exception as e:
    logger.error('OCR 처리 실패: %s', str(e))
    raise RuntimeError(f'OCR 처리 중 오류 발생: {str(e)}') from e


if __name__ == '__main__':
  import sys

  # stdout UTF-8 인코딩 명시
  if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

  if len(sys.argv) < 2:
    print('사용법: python step0_ocr.py <이미지_경로>')
    sys.exit(1)

  image_file = sys.argv[1]

  try:
    result = extract_text_from_image(image_file)
    print('\n=== 추출된 원문 텍스트 ===')
    print(result)
    print('========================\n')
  except (FileNotFoundError, ValueError, RuntimeError) as e:
    logger.error('실행 실패: %s', str(e))
    sys.exit(1)
