"""
Step 0: OCR — 고전시가 이미지에서 원문 텍스트 추출

입력: 이미지 파일 경로 (PNG/JPG)
출력: extracted_raw_text (str), poem_id (str)
"""

import base64
import logging
import os
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


# HCX-005 OCR 프롬프트
OCR_SYSTEM_PROMPT = """당신은 한국 고전시가 전문 해독 AI입니다. 이미지의 텍스트를 있는 그대로 전사하세요.

규칙:
1. 원문만 추출. 해석/풀이/설명 금지.
2. ①②③, ㉠㉡㉢ 등 편집자 기호와 (가)(나)(중략) 등 구조 표지 모두 제거.
3. 행 구조 정확히 보존. 각 줄을 개행(\\n)으로 구분. 한 줄로 이어쓰기 절대 금지.
4. 출처/각주는 [출처], [각주] 태그로 구분.
5. 코드블록(```) 금지.
6. 2컬럼 레이아웃: 한자/이두 전용 컬럼 무시, 한국어 컬럼만 위→아래 순서로 추출.
7. 행 내 한자 병기 시 한국어만 추출.
"""

OCR_USER_PROMPT = '이미지의 고전시가 원문을 위 규칙대로 전사하세요.'


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


def get_cache_path(poem_dir: Path) -> Path:
  """poem_dir을 기반으로 캐시 파일 경로 생성"""
  return poem_dir / 'step0' / 'ocr.txt'


def load_from_cache(cache_path: Path) -> str | None:
  """캐시 파일이 존재하면 내용을 반환, 없으면 None"""
  if cache_path.exists():
    logger.info('캐시에서 OCR 결과 로드: %s', cache_path)
    return cache_path.read_text(encoding='utf-8')
  return None


def save_to_cache(cache_path: Path, text: str) -> None:
  """OCR 결과를 캐시 파일에 저장 (UTF-8)"""
  try:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
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
    except Exception:
      pass
    raise RuntimeError(f'HCX-005 API 호출 중 오류 발생: {str(e)}') from e


def postprocess_ocr_text(text: str) -> str:
  """OCR 결과 후처리 — 코드펜스 제거, 주석 기호 제거, 구조 표지 제거, 연속 빈 줄 정리"""
  import re
  # 마크다운 코드펜스 제거
  text = re.sub(r'^```[^\n]*\n', '', text)
  text = re.sub(r'\n```$', '', text)
  text = text.strip('`').strip()
  # 숫자 원문자(①~⑳) + 한글 원문자(㉠~㉩) 편집자 기호 제거
  text = re.sub(r'\s*[\u2460-\u2473\u3260-\u3269]\s*', ' ', text)
  # (가)(나)(다) 등 단일 한글 괄호 표지 제거
  text = re.sub(r'\([가-힣]\)', '', text)
  # (중략), (후략), (전략) 등 구조 표지 제거
  text = re.sub(r'\([가-힣]{2,4}\)', '', text)
  # 각주 줄 제거: *단어: 설명 형태 (행 첫 문자가 *)
  text = re.sub(r'^\*[^:\n]+:[^\n]*$', '', text, flags=re.MULTILINE)
  # [출처], [각주] 태그 줄 제거
  text = re.sub(r'^\[(?:출처|각주)\][^\n]*$', '', text, flags=re.MULTILINE)
  # 연속 공백 정리
  text = re.sub(r'[ \t]{2,}', ' ', text)
  # 연속 빈 줄 3개 이상 → 2개로 정리
  text = re.sub(r'\n{3,}', '\n\n', text)
  return text.strip()


def extract_text_from_images(image_paths: list[str], poem_dir: Path, use_cache: bool = True) -> str:
  """
  고전시가 이미지(N장)에서 원문 텍스트 추출 — Step 0 메인 함수.
  이미지를 순서대로 OCR하여 텍스트를 이어붙인다.

  Args:
    image_paths: 이미지 파일 경로 리스트 (PNG/JPG), 순서 중요
    poem_dir: 캐시 및 아티팩트 저장 폴더
    use_cache: 캐시 사용 여부 (기본값: True)

  Returns:
    extracted_raw_text: 병합된 원문 텍스트
  """
  if not image_paths:
    raise ValueError('이미지 경로 리스트가 비어있습니다.')

  # 이미지 파일 존재 확인
  for img in image_paths:
    if not Path(img).exists():
      raise FileNotFoundError(f'이미지 파일을 찾을 수 없습니다: {img}')

  # API 키 확인
  ncp_api_key = os.environ.get('NCP_CLOVA_API_KEY')
  if not ncp_api_key:
    raise ValueError('NCP_CLOVA_API_KEY 환경변수가 설정되지 않았습니다.')

  # poem_dir 생성
  poem_dir = Path(poem_dir)
  poem_dir.mkdir(parents=True, exist_ok=True)

  # 캐시 확인
  cache_path = get_cache_path(poem_dir)
  if use_cache:
    cached_text = load_from_cache(cache_path)
    if cached_text is not None:
      return cached_text

  logger.info('OCR 처리 시작: %d장', len(image_paths))

  try:
    texts = []
    for idx, image_path in enumerate(image_paths):
      logger.info('이미지 %d/%d OCR 중: %s', idx + 1, len(image_paths), image_path)
      image_base64 = encode_image_to_base64(image_path)
      media_type = get_image_media_type(image_path)
      raw = call_hcx005_ocr(image_base64, media_type)
      texts.append(postprocess_ocr_text(raw))

    # 여러 장이면 빈 줄로 구분하여 병합
    extracted_raw_text = '\n\n'.join(texts)

    # 캐시 저장 (use_cache 여부와 무관하게 항상 저장)
    save_to_cache(cache_path, extracted_raw_text)

    logger.info('OCR 완료. 총 텍스트 길이: %d자', len(extracted_raw_text))
    return extracted_raw_text

  except Exception as e:
    logger.error('OCR 처리 실패: %s', str(e))
    raise RuntimeError(f'OCR 처리 중 오류 발생: {str(e)}') from e


def extract_text_from_image(image_path: str, poem_dir: Path, use_cache: bool = True) -> str:
  """하위호환 래퍼 — 단일 이미지. extract_text_from_images 로 위임."""
  return extract_text_from_images([image_path], poem_dir, use_cache=use_cache)


if __name__ == '__main__':
  import sys

  # stdout UTF-8 인코딩 명시
  if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

  if len(sys.argv) < 2:
    print('사용법: python step0_ocr.py <이미지1> [이미지2 ...] [poem_dir]')
    print('  예 (1장): python step0_ocr.py 북새곡.png "cache/poem_01"')
    print('  예 (2장): python step0_ocr.py 관동1.png 관동2.png "cache/poem_01"')
    print('  poem_dir 생략 시: cache/{첫번째이미지파일명} 자동 사용')
    sys.exit(1)

  # 마지막 인자가 이미지 확장자가 아니면 poem_dir로 간주
  IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
  args = sys.argv[1:]
  if args and Path(args[-1]).suffix.lower() not in IMAGE_EXTS:
    poem_directory = args[-1]
    image_files = args[:-1]
  else:
    image_files = args
    poem_directory = f"cache/{Path(image_files[0]).stem}"
    logger.info('poem_dir 자동 설정: %s', poem_directory)

  if not image_files:
    print('오류: 이미지 파일을 하나 이상 지정하세요.')
    sys.exit(1)

  try:
    result_text = extract_text_from_images(image_files, poem_directory)
    print('\n=== 추출된 원문 텍스트 ===')
    print(result_text)
    print('========================\n')
  except (FileNotFoundError, ValueError, RuntimeError) as e:
    logger.error('실행 실패: %s', str(e))
    sys.exit(1)
