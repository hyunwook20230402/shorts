"""
Step 3: ElevenLabs alignment → AnimateDiff BatchPromptSchedule JSON
타임스탬프 기반 동적 프레임 스케줄링
"""

import os
import json
import logging
import math
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
import openai

load_dotenv()

logger = logging.getLogger(__name__)

# 환경변수
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
ANIMATEDIFF_FPS = int(os.getenv('ANIMATEDIFF_FPS', '10'))
CACHE_DIR = Path('cache/step3')
COMMON_KEYWORDS = (
    'multiple characters, detailed scene composition, '
    'cute character illustration, soft watercolor, guofeng style, '
    'traditional korean ink wash, gentle art style, illustration style'
)
NEGATIVE_PROMPT = (
    'worst quality, low quality, blurry, ink painting, chinese characters, '
    'text, signature, watermark, writing, calligraphy, letters, '
    'inscription, seal, stamp, characters, glyphs, monochrome, grayscale, '
    'wine glass, beer glass, modern bottle, cocktail glass, western cup, '
    'modern clothing, suit, tie, jeans, sneakers, western architecture, '
    'modern furniture, television, phone, computer, car, electricity'
)


def get_cache_path(poem_dir: Path) -> Path:
  """캐시 경로 생성"""
  return poem_dir / 'step3_schedule.json'


def load_schedule_from_cache(schedule_path: Path) -> Optional[dict]:
  """스케줄 JSON 로드"""
  if not schedule_path.exists():
    return None
  try:
    with open(schedule_path, 'r', encoding='utf-8') as f:
      return json.load(f)
  except Exception as e:
    logger.warning(f'스케줄 캐시 로드 실패: {schedule_path}, {e}')
    return None


def save_schedule_to_cache(schedule_path: Path, schedule_data: dict) -> None:
  """스케줄 JSON 저장"""
  schedule_path.parent.mkdir(parents=True, exist_ok=True)
  with open(schedule_path, 'w', encoding='utf-8') as f:
    json.dump(schedule_data, f, indent=2, ensure_ascii=False)
  logger.info(f'스케줄 저장: {schedule_path}')


def calculate_frame_index(timestamp_seconds: float, fps: int) -> int:
  """타임스탬프 → 프레임 인덱스 변환"""
  return int(math.floor(timestamp_seconds * fps))


def generate_visual_prompt(
  scene_data: dict,
  sentence_text: str,
  scene_index: int
) -> str:
  """
  LLM으로 영문 시각적 프롬프트 생성
  입력: modern_text, 배경, 감정, 나레이션 전체 → 출력: 디테일한 영문 프롬프트
  """
  if not OPENAI_API_KEY:
    # API 키 없을 때 기본 프롬프트 생성
    background = scene_data.get('background', 'ancient korean landscape')
    emotion = scene_data.get('emotion', 'serene')
    logger.warning('OPENAI_API_KEY 없음, 기본 프롬프트 사용')
    return f'{background}, {emotion}, {COMMON_KEYWORDS}'

  background = scene_data.get('background', 'ancient korean landscape')
  emotion = scene_data.get('emotion', 'serene')
  modern_text = scene_data.get('modern_text', '')
  narration = scene_data.get('narration', '')

  system_prompt = (
    'You are an expert Stable Diffusion prompt writer for traditional Korean art scenes. '
    'Always output ONLY the English prompt, no explanations or markdown. '
    'Requirements: '
    '1. Include ALL characters mentioned in the scene (if horse+trader+inspector → show all 3). '
    '2. Include ALL key objects (horse, fortress wall, liquor bottle, pipe, etc.) directly visible. '
    '3. Describe specific actions and positions of each character. '
    '4. Use 200-250 English words. '
    '5. Style: ink wash painting, guofeng, traditional Korean art.'
  )

  user_prompt = f"""조선시대 고전 시가의 장면을 Stable Diffusion 프롬프트로 만들어주세요.

현대어 번역 (핵심 — 장면의 모든 등장인물과 사물을 반드시 포함):
{modern_text}

나레이션 (화자의 심리):
{narration}

배경: {background}
감정: {emotion}

등장인물과 사물을 빠짐없이 시각화하세요:
- 장면에 언급된 모든 인물 (예: 암행어사, 소주 장사) → 각자의 위치와 행동 명시
- 장면에 언급된 사물 (예: 말, 성벽, 술병, 담뱃대) → 화면에 직접 포함
- 배경 환경 (예: 성문, 설원, 안개 낀 산) → 구체적으로 묘사

엄격 금지: 현대 사물, 서양 의복, 유리컵, wine glass, modern bottles
술은 반드시: ceramic cup, porcelain jar, traditional korean vessel
영어로만 출력, 따옴표 없이"""

  try:
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
      model='gpt-4o-mini',
      messages=[
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': user_prompt}
      ],
      temperature=0.7,
      max_tokens=350,
      timeout=10
    )
    visual_prompt = response.choices[0].message.content.strip()
    return f'{visual_prompt}, {COMMON_KEYWORDS}'
  except Exception as e:
    logger.error(f'LLM 프롬프트 생성 실패: {e}')
    return f'{background}, {emotion}, {COMMON_KEYWORDS}'


def build_prompt_schedule_for_scene(
  scene_data: dict,
  alignment_data: dict,
  scene_index: int,
  fps: int = ANIMATEDIFF_FPS
) -> dict:
  """
  씬별 프롬프트 스케줄 빌드
  alignment.sentences → 프레임별 프롬프트 매핑
  """
  sentences = alignment_data.get('sentences', [])
  total_duration = alignment_data.get('total_duration', 0)
  total_frames = int(math.ceil(total_duration * fps))

  prompt_schedule = {}

  if not sentences:
    # 문장이 없으면 전체 씬에 단일 프롬프트 적용
    prompt = generate_visual_prompt(scene_data, '', scene_index)
    prompt_schedule['0'] = prompt
    return {
      'scene_index': scene_index,
      'total_frames': total_frames,
      'prompt_schedule': prompt_schedule,
      'negative_prompt': NEGATIVE_PROMPT
    }

  # 문장별 프롬프트 생성 및 프레임 인덱스 계산
  for sent_idx, sentence in enumerate(sentences):
    sent_start = sentence.get('start', 0)
    sent_text = sentence.get('text', '')
    frame_idx = calculate_frame_index(sent_start, fps)

    # LLM으로 프롬프트 생성
    prompt = generate_visual_prompt(scene_data, sent_text, scene_index)
    prompt_schedule[str(frame_idx)] = prompt

  return {
    'scene_index': scene_index,
    'total_frames': total_frames,
    'prompt_schedule': prompt_schedule,
    'negative_prompt': NEGATIVE_PROMPT
  }


def build_frame_schedules(
  script_data: list[dict],
  alignment_paths: list[str],
  poem_dir: Path,
  use_cache: bool = True
) -> str:
  """
  전체 스크립트의 프레임 스케줄 빌드
  반환: schedule JSON 파일 경로
  """
  if len(script_data) != len(alignment_paths):
    raise ValueError(f'script_data({len(script_data)}) != alignment_paths({len(alignment_paths)})')

  schedule_path = get_cache_path(poem_dir)

  # 캐시 확인
  if use_cache and schedule_path.exists():
    logger.info(f'캐시된 스케줄 사용: {schedule_path}')
    return str(schedule_path)

  logger.info('프레임 스케줄 빌드 중...')

  scene_schedules = []

  for scene_idx, (scene_data, alignment_file) in enumerate(zip(script_data, alignment_paths)):
    # alignment JSON 로드
    try:
      with open(alignment_file, 'r', encoding='utf-8') as f:
        alignment_data = json.load(f)
    except Exception as e:
      logger.error(f'alignment 로드 실패: {alignment_file}, {e}')
      raise

    # 씬별 스케줄 빌드
    scene_schedule = build_prompt_schedule_for_scene(
      scene_data,
      alignment_data,
      scene_idx
    )
    scene_schedules.append(scene_schedule)

    logger.info(f'Scene {scene_idx}: {scene_schedule["total_frames"]} frames, '
                f'{len(scene_schedule["prompt_schedule"])} transitions')

  # 최종 스케줄 저장
  final_schedule = {'scene_schedules': scene_schedules}
  save_schedule_to_cache(schedule_path, final_schedule)

  logger.info(f'전체 스케줄 빌드 완료: {len(scene_schedules)}개 씬')
  return str(schedule_path)


def build_sentence_schedules(
  script_data: list[dict],
  sentence_audio_paths: list[list[str]],
  sentence_alignment_paths: list[list[str]],
  poem_dir: Path,
  use_cache: bool = True,
) -> str:
  """
  문장 단위 스케줄 생성

  입력:
    script_data: modern_sentences, sentence_image_prompts 포함
    sentence_audio_paths: [씬][문장] MP3 경로
    sentence_alignment_paths: [씬][문장] alignment JSON 경로

  출력:
    sentence_schedule.json: {sentence_schedules: [{scene_index, sent_index, text, image_prompt, duration, audio_path}]}
  """
  schedule_path = poem_dir / 'step3_sentence_schedule.json'

  if use_cache and schedule_path.exists():
    logger.info(f'캐시된 문장 스케줄 사용: {schedule_path}')
    return str(schedule_path)

  sentence_schedules = []

  for scene_idx, scene in enumerate(script_data):
    sentences = scene.get('modern_sentences', [])
    sentence_prompts = scene.get('sentence_image_prompts', [])
    audio_paths_for_scene = sentence_audio_paths[scene_idx] if scene_idx < len(sentence_audio_paths) else []
    align_paths_for_scene = sentence_alignment_paths[scene_idx] if scene_idx < len(sentence_alignment_paths) else []

    for sent_idx, sentence_text in enumerate(sentences):
      if sent_idx >= len(align_paths_for_scene):
        logger.warning(f'Scene {scene_idx} Sent {sent_idx}: alignment 경로 없음')
        continue

      # alignment JSON 로드
      try:
        alignment_data = json.loads(
          Path(align_paths_for_scene[sent_idx]).read_text(encoding='utf-8')
        )
      except Exception as e:
        logger.error(f'alignment 로드 실패: {align_paths_for_scene[sent_idx]}, {e}')
        raise

      duration = alignment_data.get('duration', 1.0)
      image_prompt = (
        sentence_prompts[sent_idx]
        if sent_idx < len(sentence_prompts)
        else scene.get('image_prompt', '')
      )

      sentence_schedules.append({
        'scene_index': scene_idx,
        'sent_index': sent_idx,
        'text': sentence_text,
        'image_prompt': image_prompt,
        'negative_prompt': NEGATIVE_PROMPT,
        'duration': duration,
        'audio_path': audio_paths_for_scene[sent_idx] if sent_idx < len(audio_paths_for_scene) else '',
      })

  final_schedule = {
    'sentence_schedules': sentence_schedules,
    'total_sentences': len(sentence_schedules),
    'common_negative_prompt': NEGATIVE_PROMPT,
  }

  schedule_path.parent.mkdir(parents=True, exist_ok=True)
  schedule_path.write_text(
    json.dumps(final_schedule, ensure_ascii=False, indent=2), encoding='utf-8'
  )
  logger.info(f'문장 스케줄 저장: {schedule_path} ({len(sentence_schedules)}개 문장)')

  return str(schedule_path)


def cmd_check() -> bool:
  """프레임 스케줄링 환경 확인"""
  checks = []

  # OPENAI_API_KEY 확인 (선택사항)
  if OPENAI_API_KEY:
    try:
      client = openai.OpenAI(api_key=OPENAI_API_KEY)
      client.models.list()
      logger.info('✓ OpenAI API 연결 성공')
      checks.append(True)
    except Exception as e:
      logger.warning(f'✗ OpenAI API 연결 실패 (기본 프롬프트 사용): {e}')
      checks.append(True)  # 실패해도 계속 진행 가능
  else:
    logger.info('⚠ OPENAI_API_KEY 없음 (기본 프롬프트 사용)')
    checks.append(True)

  # FPS 설정 확인
  logger.info(f'✓ AnimateDiff FPS: {ANIMATEDIFF_FPS}')
  checks.append(True)

  return all(checks)


if __name__ == '__main__':
  import sys

  logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
      logging.FileHandler('step3_scheduler.log', encoding='utf-8'),
      logging.StreamHandler()
    ]
  )

  logger.info('=' * 70)
  logger.info('Step 3: 프레임 스케줄 생성 테스트')
  logger.info('=' * 70)

  # 파라미터 파싱
  if len(sys.argv) < 2:
    logger.error('✗ 사용법: python step3_scheduler.py <poem_dir>')
    exit(1)

  poem_dir = Path(sys.argv[1])

  # 1. 환경 확인
  if not cmd_check():
    logger.error('✗ 환경 확인 실패')
    exit(1)

  # 2. NLP 데이터 로드
  nlp_path = poem_dir / 'step1_nlp.json'
  if not nlp_path.exists():
    logger.error(f'✗ NLP 파일 없음: {nlp_path}')
    exit(1)

  with open(nlp_path, 'r', encoding='utf-8') as f:
    nlp_data = json.load(f)

  script_data = nlp_data.get('modern_script_data', [])

  # 3. alignment 파일 로드
  alignment_paths = []
  for scene_idx in range(len(script_data)):
    for sent_idx in range(len(script_data[scene_idx].get('modern_sentences', []))):
      alignment_path = poem_dir / f'step2_scene{scene_idx:02d}_sent{sent_idx:02d}_alignment.json'
      if not alignment_path.exists():
        logger.error(f'✗ Alignment 파일 없음: {alignment_path}')
        exit(1)
      alignment_paths.append(str(alignment_path))

  logger.info(f'NLP: {len(script_data)}개 씬')
  logger.info(f'Alignment: {len(alignment_paths)}개')

  # 4. Step 3 실행
  try:
    logger.info('\n스케줄 생성 실행 중...')
    schedule_path = build_frame_schedules(script_data, alignment_paths, poem_dir=poem_dir, use_cache=True)

    logger.info('\n✓ 스케줄 생성 완료')
    logger.info(f'  파일: {Path(schedule_path).name}')

    with open(schedule_path, 'r', encoding='utf-8') as f:
      schedule_data = json.load(f)
    schedules = schedule_data.get('scene_schedules', [])
    for s in schedules:
      scene_idx = s['scene_index']
      total_frames = s['total_frames']
      duration = total_frames / 10
      logger.info(f'  Scene {scene_idx}: {total_frames} frames ({duration:.1f}초)')

    logger.info('\n' + '=' * 70)
    logger.info('✓ Step 3 테스트 완료')
    logger.info('=' * 70)
    exit(0)

  except Exception as e:
    logger.error(f'\n✗ Step 3 실패: {e}', exc_info=True)
    exit(1)
