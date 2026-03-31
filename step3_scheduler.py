"""
Step 3: ElevenLabs alignment → AnimateDiff BatchPromptSchedule JSON
타임스탬프 기반 동적 프레임 스케줄링
"""

import os
import json
import logging
import hashlib
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
COMMON_KEYWORDS = 'cute character illustration, soft watercolor, gentle art style, illustration style, character design'
NEGATIVE_PROMPT = (
    'worst quality, low quality, blurry, ink painting, chinese characters, '
    'text, signature, watermark, writing, calligraphy, letters, '
    'inscription, seal, stamp, characters, glyphs, monochrome, grayscale, '
    'wine glass, beer glass, modern bottle, cocktail glass, western cup, '
    'modern clothing, suit, tie, jeans, sneakers, western architecture, '
    'modern furniture, television, phone, computer, car, electricity'
)


def get_cache_path(script_data_hash: str) -> Path:
  """캐시 경로 생성"""
  CACHE_DIR.mkdir(parents=True, exist_ok=True)
  return CACHE_DIR / f'{script_data_hash}_schedule.json'


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
  입력: 씬 배경, 감정, 나레이션 일부 → 출력: 영문 프롬프트
  """
  if not OPENAI_API_KEY:
    # API 키 없을 때 기본 프롬프트 생성
    background = scene_data.get('background', 'ancient korean landscape')
    emotion = scene_data.get('emotion', 'serene')
    logger.warning('OPENAI_API_KEY 없음, 기본 프롬프트 사용')
    return f'{background}, {emotion}, {COMMON_KEYWORDS}'

  background = scene_data.get('background', 'ancient korean landscape')
  emotion = scene_data.get('emotion', 'serene')
  narration = scene_data.get('narration', '')[:100]  # 처음 100자만

  prompt = f"""고전 한시의 장면을 영어로 시각화하는 Stable Diffusion 프롬프트를 생성해주세요.

배경: {background}
감정: {emotion}
나레이션 (매우 중요): {narration}
텍스트: {sentence_text}

요청:
1. 나레이션의 감정과 상황을 최대한 충실하게 반영 (150~200자)
2. 수묵화 + 국풍 스타일 강조 (ink wash, traditional korean, guofeng 포함)
3. 귀여운 캐릭터 일러스트 스타일 명시 (cute character illustration, soft watercolor)
4. 구체적인 캐릭터, 감정, 동작, 배경 요소 포함
5. 씬의 분위기와 나레이션의 심리 상태를 시각적으로 표현

엄격한 제한 (반드시 지킬 것):
- 조선시대 배경이므로 현대적 사물 절대 금지 (wine glass, beer, modern bottles, glass cups 등)
- 술은 반드시 전통 도자기 잔(ceramic cup, porcelain cup, traditional korean cup)으로만 표현
- 서양 의복, 서양 건축물 금지
- 영어로만 작성, 따옴표 없이 프롬프트만 출력

예시: "In a misty village during late Joseon, a weary scholar sits in shadow, suspicion flickering in his eyes as he holds a porcelain cup of soju; traditional korean pavilion in background; artistic style: ink wash painting with cute character illustration, soft watercolor, guofeng style"
"""

  try:
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
      model='gpt-4o-mini',
      messages=[{'role': 'user', 'content': prompt}],
      temperature=0.7,
      max_tokens=100,
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
  use_cache: bool = True
) -> str:
  """
  전체 스크립트의 프레임 스케줄 빌드
  반환: schedule JSON 파일 경로
  """
  if len(script_data) != len(alignment_paths):
    raise ValueError(f'script_data({len(script_data)}) != alignment_paths({len(alignment_paths)})')

  # 캐시 키 생성 (script_data + alignment 내용 + FPS 기반)
  alignment_contents = []
  for ap in alignment_paths:
    try:
      with open(ap, 'r', encoding='utf-8') as f:
        alignment_contents.append(json.load(f).get('total_duration', 0))
    except Exception:
      alignment_contents.append(0)

  cache_key = json.dumps({
    'script': script_data,
    'durations': alignment_contents,
    'fps': ANIMATEDIFF_FPS
  }, sort_keys=True, ensure_ascii=False)
  script_hash = hashlib.md5(cache_key.encode()).hexdigest()[:8]
  schedule_path = get_cache_path(script_hash)

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

  # 1. 환경 확인
  if not cmd_check():
    logger.error('✗ 환경 확인 실패')
    exit(1)

  # 2. 최근 Step 1 NLP 파일 탐색
  nlp_files = sorted(Path('cache/step1').glob('*_nlp.json'))
  if not nlp_files:
    logger.error('✗ Step 1 NLP 캐시 없음')
    exit(1)

  nlp_path = nlp_files[-1]
  with open(nlp_path, 'r', encoding='utf-8') as f:
    nlp_data = json.load(f)

  script_data = nlp_data.get('modern_script_data', [])

  # 3. 최근 Step 2 alignment 파일 탐색
  alignment_files = sorted(Path('cache/step2').glob('*_alignment.json'))
  if not alignment_files or len(alignment_files) < len(script_data):
    logger.error(f'✗ Step 2 alignment 캐시 부족: {len(alignment_files)}/{len(script_data)}')
    exit(1)

  # 최신 alignment 파일들을 시간순으로 정렬 후 필요한 만큼만 선택
  # (각 alignment 파일이 다른 해시를 가질 수 있음)
  if len(alignment_files) < len(script_data):
    logger.error(f'✗ alignment 파일 부족: {len(alignment_files)}/{len(script_data)}')
    exit(1)

  # 최신 파일들부터 필요한 개수만큼 역순으로 정렬
  alignment_paths = [str(f) for f in sorted(alignment_files)[-len(script_data):]]
  alignment_paths = sorted(alignment_paths, key=lambda x: Path(x).stem.split('_')[1] if len(Path(x).stem.split('_')) > 1 else 0)

  logger.info(f'NLP: {len(script_data)}개 씬')
  logger.info(f'Alignment: {len(alignment_paths)}개')

  # 4. Step 3 실행
  try:
    logger.info('\n스케줄 생성 실행 중...')
    schedule_path = build_frame_schedules(script_data, alignment_paths, use_cache=True)

    logger.info(f'\n✓ 스케줄 생성 완료')
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
