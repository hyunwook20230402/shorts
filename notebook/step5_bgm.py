"""
Step 5: Stable Audio BGM 생성 (순수 WAV 출력)
테마별 악기/분위기 힌트를 LLM 프롬프트에 주입하여 고전시가 특성 반영
"""

import json
import logging
import os
from pathlib import Path

import soundfile as sf
import torch
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(
  level=logging.INFO,
  format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# 환경변수
STABLE_AUDIO_MODEL = os.getenv('STABLE_AUDIO_MODEL', 'stabilityai/stable-audio-open-1.0')
BGM_SAMPLE_RATE = 44100  # Stable Audio 출력 샘플레이트
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')

DEFAULT_BGM_PROMPT = 'soft, ambient, traditional Korean music, peaceful instrumental, gayageum'


def get_cache_path(poem_dir: Path) -> Path:
  """캐시 경로: step5/bgm.wav"""
  return Path(poem_dir) / 'step5' / 'bgm.wav'


def load_nlp_data(poem_dir: Path) -> dict:
  """Step 1 NLP JSON 로드"""
  nlp_path = Path(poem_dir) / 'step1' / 'nlp.json'
  try:
    with open(nlp_path, 'r', encoding='utf-8') as f:
      return json.load(f)
  except Exception as e:
    logger.error(f'NLP 데이터 로드 실패: {nlp_path}, {e}')
    return {}


def get_total_duration(poem_dir: Path) -> float:
  """
  Step 3 sentence_schedule JSON에서 전체 영상 길이(초) 계산.
  없으면 Step 2 오디오 파일 합산으로 fallback.
  """
  schedule_path = Path(poem_dir) / 'step3' / 'sentence_schedule.json'
  if schedule_path.exists():
    try:
      with open(schedule_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
      total = sum(s.get('duration', 0.0) for s in data.get('sentence_schedules', []))
      if total > 0:
        logger.info(f'스케줄 기반 총 길이: {total:.2f}초')
        return total
    except Exception as e:
      logger.warning(f'스케줄 파싱 실패: {e}')

  # fallback: MP3 파일 길이 합산
  from moviepy.editor import AudioFileClip
  mp3_files = sorted((Path(poem_dir) / 'step2').glob('*_audio.mp3'))
  total = 0.0
  for mp3 in mp3_files:
    try:
      clip = AudioFileClip(str(mp3))
      total += clip.duration
      clip.close()
    except Exception:
      pass
  logger.info(f'오디오 합산 총 길이: {total:.2f}초')
  return max(total, 30.0)  # 최소 30초


def generate_bgm_prompt_with_llm(nlp_data: dict) -> str:
  """
  gpt-4o-mini로 씬 전체 정보 + 테마 힌트 기반 BGM 프롬프트 생성.
  theme_config.THEME_BGM_HINTS를 LLM 컨텍스트에 추가.
  """
  scenes = nlp_data.get('modern_script_data') or nlp_data.get('scenes', [])
  theme_code = nlp_data.get('primary_theme', nlp_data.get('theme', 'A'))

  # 테마 + 정서 힌트 로드
  try:
    from theme_config import get_bgm_hints, get_emotion_info, get_theme_info
    theme_hints = get_bgm_hints(theme_code)
    theme_info = get_theme_info(theme_code)
    theme_ko = theme_info.get('ko', '강호자연')
    hint_text = (
      f"테마: {theme_ko}\n"
      f"권장 악기: {theme_hints['instruments']}\n"
      f"분위기: {theme_hints['mood']}\n"
      f"템포: {theme_hints['tempo']}"
    )
    # 지배적 정서 반영
    dominant_emotion = nlp_data.get('dominant_emotion', 'E1')
    emotion_info = get_emotion_info(dominant_emotion)
    hint_text += f"\n지배적 정서: {emotion_info['ko']} ({emotion_info['desc']})"
  except Exception as e:
    logger.warning(f'테마/정서 힌트 로드 실패 ({e}), 기본값 사용')
    hint_text = '권장 악기: gayageum, daegeum\n분위기: peaceful, traditional'

  # 테마/정서 판단 근거 (작품별 고유 해석 반영)
  theme_reasoning = nlp_data.get('theme_reasoning', '')
  emotion_reasoning = nlp_data.get('emotion_reasoning', '')

  if not scenes:
    logger.warning('씬 정보 없음, fallback 사용')
    return DEFAULT_BGM_PROMPT

  # 씬 정보 수집
  emotions = [s.get('emotion', '') for s in scenes]
  scene_descriptions = [s.get('scene_description', '') for s in scenes]
  backgrounds = list({s.get('background', s.get('scene_description', '')) for s in scenes})
  original_texts = [s.get('original_text', '') for s in scenes]

  # 판단 근거 조건부 삽입 (없으면 빈 줄 방지)
  reasoning_lines = '\n'.join(filter(None, [
    f'테마 판단 근거: {theme_reasoning}' if theme_reasoning else '',
    f'정서 판단 근거: {emotion_reasoning}' if emotion_reasoning else '',
  ]))

  context = f"""다음은 한국 고전시가 쇼츠 영상의 정보입니다.

{hint_text}
{reasoning_lines}

씬 감정: {', '.join(emotions)}
장면 묘사: {', '.join(scene_descriptions)}
배경: {', '.join(backgrounds)}
원문: {' / '.join(original_texts)}

위 테마 힌트와 씬 정보를 바탕으로 Stable Audio 모델에 입력할 배경음악 프롬프트를 영어로 생성하세요.
조건:
- 테마에서 권장한 악기를 우선 사용
- 전체 영상의 감정 흐름 반영
- Stable Audio 프롬프트 형식: 쉼표로 구분된 키워드/구문
- 30단어 이내
프롬프트만 출력하세요 (설명 없이):"""

  try:
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
      model='gpt-4o-mini',
      messages=[{'role': 'user', 'content': context}],
      max_tokens=100,
      temperature=0.7,
    )
    prompt = response.choices[0].message.content.strip()
    logger.info(f'LLM 생성 BGM 프롬프트: {prompt}')
    return prompt
  except Exception as e:
    logger.warning(f'LLM 호출 실패 ({e}), fallback 사용')
    return DEFAULT_BGM_PROMPT


def generate_stable_audio(prompt: str, duration_seconds: float) -> tuple:
  """
  Stable Audio로 배경음악 생성.
  반환: (numpy 오디오 배열, 샘플레이트)
  """
  logger.info(f'Stable Audio 모델 로드: {STABLE_AUDIO_MODEL}')

  device = 'cuda' if torch.cuda.is_available() else 'cpu'
  logger.info(f'Device: {device}')

  from diffusers import StableAudioPipeline

  pipe = StableAudioPipeline.from_pretrained(
    STABLE_AUDIO_MODEL,
    torch_dtype=torch.float16,
    use_safetensors=True,
  )
  pipe = pipe.to(device)

  logger.info(f'오디오 생성 중: {prompt} ({duration_seconds:.1f}초)')

  with torch.no_grad():
    audio = pipe(
      prompt,
      audio_end_in_s=duration_seconds,
      guidance_scale=7.0,
      num_inference_steps=100,
    ).audios

  logger.info(f'오디오 생성 완료: shape={audio.shape}')
  return audio[0].cpu().float().numpy(), BGM_SAMPLE_RATE


def run_step5(poem_dir: str, use_cache: bool = True) -> str:
  """
  Main Step 5 함수 — BGM 생성 (순수 WAV 출력).
  입력: {poem_dir}/step1/nlp.json, {poem_dir}/step3/sentence_schedule.json
  출력: {poem_dir}/step5/bgm.wav
  """
  poem_dir = Path(poem_dir)
  output_path = get_cache_path(poem_dir)

  logger.info(f'Step 5 (BGM) 시작: {poem_dir}')

  # 캐시 확인
  if use_cache and output_path.exists():
    logger.info(f'캐시 사용: {output_path}')
    return str(output_path)

  # NLP 데이터 로드 (테마 확인용)
  nlp_data = load_nlp_data(poem_dir)
  theme_code = nlp_data.get('primary_theme', nlp_data.get('theme', 'A'))
  logger.info(f'테마: {theme_code}')

  # 전체 영상 길이 계산
  duration = get_total_duration(poem_dir)
  logger.info(f'BGM 목표 길이: {duration:.2f}초')

  # BGM 프롬프트 생성
  bgm_prompt = generate_bgm_prompt_with_llm(nlp_data)
  logger.info(f'BGM 프롬프트: {bgm_prompt}')

  # Stable Audio로 배경음악 생성
  bgm_np, sr = generate_stable_audio(bgm_prompt, duration)

  # WAV 저장 (채널 순서: (channels, samples) → (samples, channels))
  output_path.parent.mkdir(parents=True, exist_ok=True)
  sf.write(str(output_path), bgm_np.T, sr)
  logger.info(f'BGM WAV 저장 완료: {output_path}')

  return str(output_path)


if __name__ == '__main__':
  import sys

  if len(sys.argv) < 2:
    logger.info('사용법: python step5_bgm.py <poem_dir>')
    logger.info('예시: python step5_bgm.py cache/poem_01')
    sys.exit(1)

  poem_dir_arg = sys.argv[1]
  output = run_step5(poem_dir_arg, use_cache=False)
  logger.info(f'BGM 생성 완료: {output}')
