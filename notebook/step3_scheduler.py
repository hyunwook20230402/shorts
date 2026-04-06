"""
Step 3: ElevenLabs alignment → AnimateDiff BatchPromptSchedule JSON
타임스탬프 기반 동적 프레임 스케줄링
"""
import os
import json
import logging
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
    'worst quality, low quality, blurry, chinese characters, '
    'text, signature, watermark, writing, calligraphy, letters, '
    'inscription, seal, stamp, characters, glyphs, monochrome, grayscale, '
    'wine glass, beer glass, modern bottle, cocktail glass, western cup, '
    'modern clothing, suit, tie, jeans, sneakers, coat, trench coat, hoodie, '
    'winter coat, puffer jacket, modern jacket, western clothing, '
    'western architecture, modern furniture, television, phone, computer, car, electricity'
)


def get_cache_path(poem_dir: Path) -> Path:
  """캐시 경로 생성"""
  return poem_dir / 'step3' / 'schedule.json'


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



def build_sentence_schedules(
    script_data: list[dict],
    sentence_audio_paths: list[list[str]],
    sentence_alignment_paths: list[list[str]],
    poem_dir: Path,
    use_cache: bool = True,
) -> str:
    """문장 단위 스케줄 생성 (모든 문장 동적 대응)"""
    schedule_path = poem_dir / 'step3' / 'sentence_schedule.json'

    if use_cache and schedule_path.exists():
        logger.info(f'캐시 사용: {schedule_path}')
        return str(schedule_path)

    sentence_schedules = []
    from moviepy.editor import AudioFileClip

    for scene_idx, scene in enumerate(script_data):
        text = scene.get('original_text', '').strip()
        scene_audios = sentence_audio_paths[scene_idx]
        audio_path = scene_audios[0] if scene_audios else ""
        image_prompt = scene.get('image_prompt', '')

        # 오디오 길이 측정
        try:
            with AudioFileClip(audio_path) as audio:
                duration = audio.duration
        except Exception as e:
            logger.warning(f"오디오 길이 측정 실패({audio_path}): {e}")
            duration = 2.0  # fallback

        sentence_schedules.append({
            'scene_index': scene_idx,
            'sentence_index': 0,
            'text': text,
            'image_prompt': image_prompt,
            'negative_prompt': NEGATIVE_PROMPT,
            'duration': duration,
            'audio_path': audio_path,
            'pose_type': scene.get('pose_type', 'standing_single'),
            'composition': scene.get('composition', 'wide_establishing'),
            'main_focus': scene.get('main_focus', ['background']),
        })

    final_schedule = {
        'sentence_schedules': sentence_schedules,
        'total_sentences': len(sentence_schedules), # ✅ 이제 9개가 찍힘
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

# 2. NLP 데이터 로드 (자동 탐색 모드)
  nlp_path = poem_dir / 'step1' / 'nlp.json'
  if not nlp_path.exists():
    logger.error(f'✗ NLP 파일 없음: {nlp_path}')
    exit(1)

  with open(nlp_path, 'r', encoding='utf-8') as f:
    nlp_data = json.load(f)

  script_data = []

  if isinstance(nlp_data, list):
      # 경우 1: 최상위가 바로 리스트인 경우
      script_data = nlp_data
  elif isinstance(nlp_data, dict):
      # 경우 2: 'scenes', 'data', 'items' 등의 키를 사용하는 경우
      for key in ['scenes', 'data', 'items', 'script', 'modern_script_data']:
          if key in nlp_data and isinstance(nlp_data[key], list):
              script_data = nlp_data[key]
              logger.info(f"'{key}' 키에서 데이터를 찾았습니다.")
              break
      
      # 경우 3: 키 이름을 알 수 없지만 딕셔너리 안에 리스트가 하나뿐인 경우
      if not script_data:
          for value in nlp_data.values():
              if isinstance(value, list) and len(value) > 0:
                  script_data = value
                  break

  if not script_data:
      logger.error(f"✗ 데이터를 찾을 수 없습니다. JSON 구조 확인 필요: {list(nlp_data.keys())}")
      exit(1)

  logger.info(f'nlp_data 로드 성공: {len(script_data)}개 씬 발견')

# 3. Step 2 파일 로드 (1씬 1문장 체제 반영)
  sentence_audio_paths = []
  sentence_alignment_paths = []
  
  logger.info(f"검사 시작: {len(script_data)}개의 씬에 대한 파일을 찾습니다.")

  for scene_idx, scene in enumerate(script_data):
        scene_audios = []
        scene_alignments = []
        
        # 1씬=1문장이므로 sent_idx=0 고정 (step2_tts.py의 get_sentence_audio_path와 동일 경로)
        audio_path = poem_dir / 'step2' / f'scene{scene_idx:02d}_sent00_audio.mp3'
        alignment_path = poem_dir / 'step2' / f'scene{scene_idx:02d}_sent00_alignment.json'

        if audio_path.exists():
            scene_audios.append(str(audio_path))
            scene_alignments.append(str(alignment_path))
        else:
            logger.error(f'✗ 파일 누락: {audio_path}')
        
        sentence_audio_paths.append(scene_audios)
        sentence_alignment_paths.append(scene_alignments)

  # 4. Step 3 실행
  try:
    logger.info('\n스케줄 생성 실행 중...')
    schedule_path = build_sentence_schedules(
      script_data,
      sentence_audio_paths,
      sentence_alignment_paths,
      poem_dir=poem_dir,
      use_cache=True
    )
    logger.info(f'✓ 스케줄 생성 완료: {schedule_path}')
    
  except Exception as e:
    logger.error(f'✗ Step 3 실패: {e}')
