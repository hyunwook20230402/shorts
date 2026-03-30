"""
Step 5: AnimateDiff 클립 연결 + ElevenLabs 타임스탬프 기반 자막 Burn-in + 최종 병합
"""

import os
import json
import logging
import hashlib
import math
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from moviepy.editor import (
  VideoFileClip,
  concatenate_videoclips,
  TextClip,
  CompositeVideoClip,
  ColorClip,
  AudioFileClip
)
from moviepy.audio.io.AudioFileClip import AudioFileClip as AudioFileClipClass
import numpy as np

load_dotenv()

logger = logging.getLogger(__name__)

# 환경변수
CACHE_DIR = Path('cache/step5')
SUBTITLE_FONT_PATH = Path(os.getenv('SUBTITLE_FONT_PATH', 'C:/Windows/Fonts/malgun.ttf'))
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
OUTPUT_FPS = 30  # 10fps → 30fps 업스케일
SUBTITLE_FONT_SIZE = 40
SUBTITLE_COLOR = 'white'
SUBTITLE_BG_COLOR = (0, 0, 0, 200)  # RGBA: 반투명 검은색


def get_cache_path(schedule_hash: str) -> Path:
  """캐시 경로 생성"""
  CACHE_DIR.mkdir(parents=True, exist_ok=True)
  return CACHE_DIR / f'{schedule_hash}_shorts.mp4'


def get_audio_duration(audio_path: str) -> float:
  """오디오 파일 길이(초) 조회"""
  try:
    audio = AudioFileClip(audio_path)
    duration = audio.duration
    audio.close()
    return duration
  except Exception as e:
    logger.error(f'오디오 길이 조회 실패: {audio_path}, {e}')
    return 0.0


def load_alignment_data(alignment_path: str) -> dict:
  """alignment JSON 로드"""
  try:
    with open(alignment_path, 'r', encoding='utf-8') as f:
      return json.load(f)
  except Exception as e:
    logger.error(f'alignment 로드 실패: {alignment_path}, {e}')
    return {'sentences': [], 'total_duration': 0}


def make_subtitle_clip_for_sentence(
  text: str,
  start_time: float,
  end_time: float,
  video_width: int = OUTPUT_WIDTH,
  video_height: int = OUTPUT_HEIGHT
) -> Optional[object]:
  """
  문장 하나의 자막 클립 생성
  반환: TextClip or None
  """
  if not text or start_time >= end_time:
    return None

  try:
    # 텍스트 클립 생성
    txt_clip = TextClip(
      txt=text,
      fontsize=SUBTITLE_FONT_SIZE,
      font=str(SUBTITLE_FONT_PATH),
      color=SUBTITLE_COLOR,
      bg_color=(0, 0, 0),  # 검은색 배경
      method='caption',
      size=(video_width - 100, None),  # 양측 여백 50px씩
      align='center'
    )

    # 자막 위치: 화면 하단 (y=video_height-200)
    txt_clip = txt_clip.set_position(
      ('center', video_height - 250)
    ).set_duration(
      end_time - start_time
    ).set_start(start_time)

    return txt_clip

  except Exception as e:
    logger.warning(f'자막 클립 생성 실패: {text[:20]}, {e}')
    return None


def concatenate_clips(
  clip_paths: list[str]
) -> VideoFileClip:
  """
  씬별 클립들을 시간순서대로 연결
  반환: 연결된 VideoClip
  """
  clips = []
  total_duration = 0

  for clip_path in clip_paths:
    try:
      clip = VideoFileClip(clip_path)
      # 10fps → 30fps 업스케일
      if clip.fps != OUTPUT_FPS:
        logger.info(f'프레임레이트 변환: {clip.fps} → {OUTPUT_FPS}')
        clip = clip.speedx(OUTPUT_FPS / (clip.fps or 10))
      clips.append(clip)
      total_duration += clip.duration
      logger.info(f'클립 로드: {clip_path} ({clip.duration:.2f}s)')
    except Exception as e:
      logger.error(f'클립 로드 실패: {clip_path}, {e}')
      raise

  if not clips:
    raise ValueError('연결할 클립이 없습니다')

  # 클립 연결
  concatenated = concatenate_videoclips(clips)
  logger.info(f'클립 연결 완료: 총 {len(clips)}개, {total_duration:.2f}s')
  return concatenated


def add_subtitles_to_video(
  video_clip: VideoFileClip,
  alignment_paths: list[str],
  video_clip_paths: list[str]
) -> VideoFileClip:
  """
  타임스탬프 기반 자막 Burn-in
  씬별 누적 오프셋 고려
  """
  subtitle_clips = []
  cumulative_time = 0.0

  for scene_idx, (alignment_path, clip_path) in enumerate(zip(alignment_paths, video_clip_paths)):
    alignment_data = load_alignment_data(alignment_path)
    sentences = alignment_data.get('sentences', [])

    # 씬의 비디오 길이
    try:
      scene_video = VideoFileClip(clip_path)
      scene_duration = scene_video.duration
      scene_video.close()
    except Exception as e:
      logger.error(f'씬 비디오 길이 조회 실패: {clip_path}, {e}')
      scene_duration = 0

    # 씬 내 문장들의 자막 생성
    for sentence in sentences:
      sent_start = sentence.get('start', 0)
      sent_end = sentence.get('end', 0)
      sent_text = sentence.get('text', '')

      # 누적 오프셋 적용
      global_start = sent_start + cumulative_time
      global_end = sent_end + cumulative_time

      # 자막 클립 생성
      subtitle_clip = make_subtitle_clip_for_sentence(
        sent_text,
        global_start,
        global_end,
        OUTPUT_WIDTH,
        OUTPUT_HEIGHT
      )

      if subtitle_clip:
        subtitle_clips.append(subtitle_clip)
        logger.debug(f'Scene {scene_idx} 자막: "{sent_text[:30]}" ({global_start:.2f}~{global_end:.2f}s)')

    cumulative_time += scene_duration

  # 자막 클립들을 원본 비디오에 오버레이
  if subtitle_clips:
    final_video = CompositeVideoClip(
      [video_clip] + subtitle_clips
    )
    logger.info(f'자막 Burn-in 완료: {len(subtitle_clips)}개 문장')
    return final_video
  else:
    logger.warning('생성된 자막이 없습니다')
    return video_clip


def composite_video_with_audio(
  video_clip: VideoFileClip,
  audio_paths: list[str]
) -> VideoFileClip:
  """
  비디오에 오디오 합치기
  여러 MP3 파일을 순차적으로 연결하여 오디오 트랙으로 설정
  """
  if not audio_paths:
    logger.warning('오디오 파일이 없습니다')
    return video_clip

  try:
    # 오디오 파일들을 순차적으로 연결
    audio_clips = []
    for audio_path in audio_paths:
      audio = AudioFileClip(audio_path)
      audio_clips.append(audio)
      logger.info(f'오디오 로드: {audio_path} ({audio.duration:.2f}s)')

    # 오디오 연결
    combined_audio = concatenate_videoclips(audio_clips, method='chain').audio \
      if len(audio_clips) > 1 else audio_clips[0]

    # 비디오에 오디오 설정
    final_video = video_clip.set_audio(combined_audio)
    logger.info(f'오디오 싱크 완료')
    return final_video

  except Exception as e:
    logger.error(f'오디오 합치기 실패: {e}')
    return video_clip


def resize_video_to_shorts_format(
  video_clip: VideoFileClip,
  target_width: int = OUTPUT_WIDTH,
  target_height: int = OUTPUT_HEIGHT
) -> VideoFileClip:
  """
  비디오를 쇼츠 형식으로 리사이즈 (1080×1920)
  """
  current_width, current_height = video_clip.size

  if (current_width, current_height) == (target_width, target_height):
    logger.info(f'이미 쇼츠 형식: {target_width}×{target_height}')
    return video_clip

  logger.info(f'비디오 리사이즈: {current_width}×{current_height} → {target_width}×{target_height}')

  # 가로세로 비율 유지하며 리사이즈
  aspect_ratio = current_width / current_height
  target_aspect = target_width / target_height

  if aspect_ratio > target_aspect:
    # 현재 비디오가 더 넓음: 높이 기준으로 조정
    new_height = target_height
    new_width = int(new_height * aspect_ratio)
  else:
    # 현재 비디오가 더 좁음: 너비 기준으로 조정
    new_width = target_width
    new_height = int(new_width / aspect_ratio)

  resized = video_clip.resize((new_width, new_height))

  # 검은색 배경으로 센터링
  background = ColorClip(
    size=(target_width, target_height),
    color=(0, 0, 0)
  ).set_duration(resized.duration)

  # 비디오를 중앙에 배치
  offset_x = (target_width - new_width) // 2
  offset_y = (target_height - new_height) // 2

  final_clip = CompositeVideoClip(
    [background, resized.set_position((offset_x, offset_y))]
  ).set_fps(OUTPUT_FPS)

  logger.info(f'리사이즈 완료')
  return final_clip


def compose_final_video(
  video_clip_paths: list[str],
  audio_paths: list[str],
  alignment_paths: list[str],
  use_cache: bool = True
) -> str:
  """
  최종 영상 합성:
  1. 클립 연결
  2. 자막 Burn-in
  3. 오디오 싱크
  4. 쇼츠 형식 리사이즈 (1080×1920)
  5. MP4 저장

  반환: 최종 영상 파일 경로
  """
  # 캐시 키 생성
  cache_key = hashlib.md5(
    json.dumps({
      'clips': sorted(video_clip_paths),
      'audio': sorted(audio_paths),
      'alignment': sorted(alignment_paths)
    }, sort_keys=True).encode()
  ).hexdigest()[:8]

  output_path = get_cache_path(cache_key)

  # 캐시 확인
  if use_cache and output_path.exists():
    logger.info(f'캐시된 영상 사용: {output_path}')
    return str(output_path)

  logger.info('최종 영상 합성 중...')

  try:
    # 1. 클립 연결
    video = concatenate_clips(video_clip_paths)
    logger.info(f'클립 연결 완료: {video.duration:.2f}s')

    # 2. 자막 Burn-in
    video = add_subtitles_to_video(video, alignment_paths, video_clip_paths)
    logger.info(f'자막 추가 완료')

    # 3. 오디오 싱크
    video = composite_video_with_audio(video, audio_paths)
    logger.info(f'오디오 싱크 완료')

    # 4. 쇼츠 형식 리사이즈
    video = resize_video_to_shorts_format(video)
    logger.info(f'쇼츠 형식 변환 완료')

    # 5. 최종 저장
    output_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f'최종 영상 저장 중: {output_path}')

    video.write_videofile(
      str(output_path),
      fps=OUTPUT_FPS,
      codec='libx264',
      audio_codec='aac',
      verbose=False,
      logger=None  # 진행률 로그 억제
    )

    logger.info(f'✓ 최종 영상 저장 완료: {output_path}')
    video.close()

    return str(output_path)

  except Exception as e:
    logger.error(f'최종 영상 합성 실패: {e}')
    raise


def cmd_check() -> bool:
  """환경 확인"""
  checks = []

  # 폰트 파일 확인
  if SUBTITLE_FONT_PATH.exists():
    logger.info(f'✓ 자막 폰트 존재: {SUBTITLE_FONT_PATH}')
    checks.append(True)
  else:
    logger.warning(f'⚠ 자막 폰트 없음: {SUBTITLE_FONT_PATH} (기본값 사용)')
    checks.append(True)  # 경고지만 계속 진행 가능

  # MoviePy 확인
  try:
    import moviepy
    logger.info(f'✓ MoviePy 설치됨')
    checks.append(True)
  except ImportError:
    logger.error(f'✗ MoviePy 설치 필요')
    checks.append(False)

  return all(checks)


if __name__ == '__main__':
  logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
  )

  if cmd_check():
    print('영상 처리 환경 준비 완료')
  else:
    print('환경 확인 실패')
