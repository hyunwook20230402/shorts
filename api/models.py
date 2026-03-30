from datetime import datetime
from enum import Enum
from pydantic import BaseModel


class StepStatusEnum(str, Enum):
  """작업 상태"""
  pending = 'pending'
  running = 'running'
  completed = 'completed'
  failed = 'failed'


class TaskStatus(BaseModel):
  """파이프라인 작업 상태"""
  task_id: str
  current_step: int  # 0~5
  status: StepStatusEnum
  status_message: str
  error_log: dict[str, str]
  created_at: datetime
  updated_at: datetime

  # 각 Step 결과 경로
  uploaded_image_path: str | None = None
  ocr_text: str | None = None
  nlp_cache_path: str | None = None
  image_paths: list[str] = []  # v2에서 미사용 (하위호환성 유지)
  audio_paths: list[str] = []  # Step 2: ElevenLabs MP3 경로
  tts_alignment_paths: list[str] = []  # Step 2: alignment JSON 경로 (신규)
  frame_schedule_path: str | None = None  # Step 3: BatchPromptSchedule JSON 경로 (신규)
  still_image_paths: list[str] = []  # Step 4-A: ComfyUI 정지 이미지 PNG 경로 (신규 I2V)
  video_clip_paths: list[str] = []  # Step 4-B: Ken Burns MP4 클립 경로 (신규)
  subtitle_path: str | None = None  # v2에서 미사용 (타임스탬프 기반 교체)
  video_path: str | None = None


class UploadResponse(BaseModel):
  """이미지 업로드 응답"""
  task_id: str
  image_path: str
  status: str = 'uploaded'


class PipelineRunRequest(BaseModel):
  """파이프라인 실행 요청"""
  task_id: str
  start_step: int = 0
  end_step: int = 5


class StepRequest(BaseModel):
  """단독 Step 실행 요청"""
  task_id: str
  use_cache: bool = True
  invalidate_downstream: bool = False
