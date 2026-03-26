"""
Step 0: OCR — 고전시가 이미지에서 원문 텍스트 추출

입력: 이미지 파일 경로 (PNG/JPG)
출력: extracted_raw_text (str)
"""

import base64
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
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

# GPT-4o-mini OCR 프롬프트
OCR_SYSTEM_PROMPT = """당신은 한국 고전시가(시조, 향가, 가사 등) 전문 해독 AI입니다.
이미지에서 고전 한국어 텍스트를 정확하게 추출하세요.

규칙:
1. 원문 텍스트만 추출하고, 해석이나 설명을 덧붙이지 마세요.
2. 한자가 있으면 한자 그대로 포함하세요.
3. 행 구분은 줄바꿈(\\n)으로 표현하세요.
4. 이미지에 텍스트가 없거나 읽을 수 없으면 빈 문자열을 반환하세요.
"""

OCR_USER_PROMPT = '이미지에 있는 고전시가 원문 텍스트를 추출해주세요.'


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
  """OCR 결과를 캐시 파일에 저장"""
  cache_path.write_text(text, encoding='utf-8')
  logger.info('OCR 결과 캐시 저장: %s', cache_path)


@retry(
  stop=stop_after_attempt(3),
  wait=wait_exponential(multiplier=1, min=2, max=30),
  reraise=True,
)
def call_gpt4o_mini_ocr(client: OpenAI, image_base64: str, media_type: str) -> str:
  """GPT-4o-mini Vision API 호출 (retry 3회 + 지수 백오프)"""
  logger.info('GPT-4o-mini OCR API 호출 중...')

  response = client.chat.completions.create(
    model='gpt-4o-mini',
    messages=[
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
              'detail': 'high',
            },
          },
          {
            'type': 'text',
            'text': OCR_USER_PROMPT,
          },
        ],
      },
    ],
    max_tokens=1000,
    temperature=0,
  )

  extracted_text = response.choices[0].message.content or ''
  logger.info('OCR 완료. 추출된 텍스트 길이: %d자', len(extracted_text))
  return extracted_text


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

  # API 키 확인
  api_key = os.environ.get('OPENAI_API_KEY')
  if not api_key:
    raise ValueError('OPENAI_API_KEY 환경변수가 설정되지 않았습니다.')

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

    # OpenAI 클라이언트 생성
    client = OpenAI(api_key=api_key)

    # GPT-4o-mini OCR 호출
    extracted_raw_text = call_gpt4o_mini_ocr(client, image_base64, media_type)

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
