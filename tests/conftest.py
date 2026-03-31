"""
pytest 공통 fixture 및 설정
"""

import json
import logging
from pathlib import Path
import pytest

logger = logging.getLogger(__name__)


@pytest.fixture
def nlp_cache_path():
  """Step 1 NLP 캐시 파일 자동 탐색"""
  cache_dir = Path('cache/step1')
  nlp_files = sorted(cache_dir.glob('*_nlp.json'))
  if not nlp_files:
    pytest.skip('Step 1 캐시 파일 없음')
  return nlp_files[-1]


@pytest.fixture
def nlp_data(nlp_cache_path):
  """Step 1 NLP 결과 데이터"""
  with open(nlp_cache_path, 'r', encoding='utf-8') as f:
    return json.load(f)


@pytest.fixture
def script_data(nlp_data):
  """Step 1 modern_script_data"""
  return nlp_data.get('modern_script_data', [])


@pytest.fixture
def mock_alignment_data():
  """Step 3 테스트용 mock alignment 데이터"""
  return {
    'total_duration': 5.0,
    'words': [
      {'text': '첫', 'start': 0.0, 'end': 0.5},
      {'text': '번째', 'start': 0.5, 'end': 1.0},
      {'text': '문장', 'start': 1.0, 'end': 1.5},
    ],
    'sentences': [
      {'text': '첫 번째 문장입니다', 'start': 0.0, 'end': 1.5},
    ]
  }


@pytest.fixture(scope='session')
def env_setup():
  """환경 변수 로드"""
  from dotenv import load_dotenv
  load_dotenv()
  logger.info('환경 변수 로드 완료')
