"""
시 단위(poem_id) 관리 — 이미지 해시 기반 중복 감지 및 번호 부여
"""
import json
import logging
import threading
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

POEM_REGISTRY_FILE = Path('cache/poem_registry.json')


class PoemRegistry:
  """poem_id 레지스트리 관리 — 파일 기반 + threading.Lock"""
  _lock = threading.Lock()

  def _load(self) -> dict:
    """레지스트리 JSON 로드"""
    if POEM_REGISTRY_FILE.exists():
      try:
        return json.loads(POEM_REGISTRY_FILE.read_text(encoding='utf-8'))
      except (json.JSONDecodeError, OSError):
        logger.warning(f'{POEM_REGISTRY_FILE} 로드 실패, 빈 레지스트리로 시작')
        return {}
    return {}

  def _save(self, data: dict):
    """레지스트리 JSON 저장"""
    POEM_REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    POEM_REGISTRY_FILE.write_text(
      json.dumps(data, ensure_ascii=False, indent=2, default=str),
      encoding='utf-8'
    )

  def find_or_create(self, image_hash: str, original_filename: str) -> str:
    """
    이미지 해시로 기존 poem_id 조회, 없으면 신규 생성

    Args:
      image_hash: SHA-256 이미지 파일 해시 (64자)
      original_filename: 원본 파일명

    Returns:
      poem_id: "poem_01", "poem_02" 등
    """
    with self._lock:
      data = self._load()

      # 기존 이미지 해시 조회
      for poem_id, info in data.items():
        if info.get('image_hash') == image_hash:
          logger.info(f'기존 poem 발견: {poem_id} (파일: {original_filename})')
          return poem_id

      # 신규 poem_id 생성
      existing_numbers = []
      for poem_id in data.keys():
        try:
          # "poem_01" → 01 → 1 추출
          num = int(poem_id.split('_')[1])
          existing_numbers.append(num)
        except (IndexError, ValueError):
          pass

      next_number = max(existing_numbers) + 1 if existing_numbers else 1
      new_poem_id = f'poem_{next_number:02d}'

      # 레지스트리에 신규 항목 추가
      data[new_poem_id] = {
        'image_hash': image_hash,
        'original_filename': original_filename,
        'created_at': datetime.now().isoformat()
      }
      self._save(data)

      logger.info(f'신규 poem 생성: {new_poem_id}')
      return new_poem_id

  def get_poem_dir(self, poem_id: str) -> Path:
    """poem_id로부터 캐시 폴더 경로 도출"""
    return Path(f'cache/{poem_id}')
