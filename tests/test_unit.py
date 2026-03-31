"""
단위 테스트 — 외부 의존성 없이 실행 가능
"""

import os
import logging
import pytest
from dotenv import load_dotenv
from step2_tts import clean_tts_text

load_dotenv()
logger = logging.getLogger(__name__)


class TestCleanTtsText:
  """Step 2 TTS 텍스트 정제 함수 테스트"""

  def test_removes_periods(self):
    """마침표 제거"""
    text = '첫 번째 문장입니다. 두 번째 문장입니다.'
    result = clean_tts_text(text)
    assert '.' not in result
    assert '첫' in result
    assert '번째' in result

  def test_removes_commas(self):
    """쉼표 제거"""
    text = '온성은 얼마나 더 가야 하나, 우리 말이 지쳐 버렸구나.'
    result = clean_tts_text(text)
    assert ',' not in result
    assert '온성은' in result

  def test_removes_question_marks(self):
    """물음표 제거"""
    text = '무엇인가? 정말 그럴까?'
    result = clean_tts_text(text)
    assert '?' not in result
    assert '무엇인가' in result

  def test_removes_multiple_punctuation(self):
    """마침표, 쉼표, 물음표 동시 제거"""
    text = '첫 번째, 두 번째. 세 번째?'
    result = clean_tts_text(text)
    assert '.' not in result
    assert ',' not in result
    assert '?' not in result
    assert 'first' not in result  # 원문 보존 확인
    assert '첫' in result

  def test_preserves_korean_text(self):
    """한글 텍스트 보존"""
    text = '한글 텍스트 검증.'
    result = clean_tts_text(text)
    assert '한글' in result
    assert '텍스트' in result
    assert '검증' in result

  def test_empty_string(self):
    """빈 문자열 처리"""
    result = clean_tts_text('')
    assert result == ''

  def test_only_punctuation(self):
    """구두점만 있는 경우"""
    result = clean_tts_text('.,?')
    assert result == ''


class TestElevenlabsApiKey:
  """ElevenLabs API 키 존재 여부 테스트"""

  def test_api_key_loaded(self):
    """ELEVENLABS_API_KEY가 로드되었는지 확인"""
    api_key = os.getenv('ELEVENLABS_API_KEY')
    assert api_key is not None, 'ELEVENLABS_API_KEY 환경 변수가 설정되지 않음'
    assert len(api_key) > 0, 'ELEVENLABS_API_KEY가 비어 있음'

  def test_voice_id_loaded(self):
    """ELEVENLABS_VOICE_ID가 로드되었는지 확인"""
    voice_id = os.getenv('ELEVENLABS_VOICE_ID')
    assert voice_id is not None, 'ELEVENLABS_VOICE_ID 환경 변수가 설정되지 않음'
    assert len(voice_id) > 0, 'ELEVENLABS_VOICE_ID가 비어 있음'

  def test_openai_api_key_loaded(self):
    """OPENAI_API_KEY가 로드되었는지 확인"""
    api_key = os.getenv('OPENAI_API_KEY')
    assert api_key is not None, 'OPENAI_API_KEY 환경 변수가 설정되지 않음'
    assert len(api_key) > 0, 'OPENAI_API_KEY가 비어 있음'
