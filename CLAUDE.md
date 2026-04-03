# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

고전시가 원문 이미지 → 수묵화 스타일 정지이미지 슬라이드쇼 쇼츠 자동 생성 파이프라인 **(v2 — Dynamic Clip Generator)**.

**현재 상태:** Step 0~5 전체 구현 완료 (edge-tts + SD 1.5 정지이미지 + PIL 자막).

## 기술 스택 (v2)

- **프론트엔드:** Streamlit (`app_ui.py`, 포트 8501)
- **백엔드:** FastAPI (`main_api.py`, 포트 8000)
- **LLM:** HCX-005 (OCR + 번역), gpt-4o-mini (시각 프롬프트)
- **음성:** edge-tts (한국어, 무료 — `ko-KR-SunHiNeural`)
- **이미지:** ComfyUI SD 1.5 정지이미지 (국풍 LoRA + IP-Adapter)
- **자막:** PIL Image 기반 자막 이미지 → MoviePy ImageClip Burn-in
- **최종 합성:** MoviePy + FFmpeg (이미지+오디오 슬라이드쇼)
- **데이터:** Notion API (원문-번역 로깅)
- **패키지:** Python 3.12, uv

## 파이프라인 (v2)

```
Step 0: OCR             HCX-005로 이미지 → 텍스트 추출
Step 1: NLP             번역 + 씬 분할 (원문, 현대어, 나레이션, 감정, 배경)
Step 2: 음성+타임스탬프  edge-tts로 MP3 + alignment(추정 타임스탬프) JSON
Step 3: 프레임 스케줄    문장 단위 스케줄 JSON (duration, image_prompt, audio_path)
Step 4: 정지이미지       ComfyUI SD1.5 (국풍 LoRA + IP-Adapter)로 문장별 PNG 생성
Step 5: 최종 병합        이미지+오디오 슬라이드쇼 + 타임스탬프 자막 Burn-in (1080×1920, 30fps)
```

## 핵심 데이터 구조 (v2)

**상태 관리 (`task_status_dict`):**
- JSON 파일 기반 (`cache/task_states.json`), `PersistentTaskDict` 클래스로 다중 프로세스 영속화
- 주요 필드:
  - `sentence_audio_paths: list[list[str]]` — Step 2 문장별 MP3 경로 `[씬][문장]`
  - `sentence_alignment_paths: list[list[str]]` — Step 2 문장별 alignment JSON 경로
  - `sentence_schedule_path: str | None` — Step 3 문장 단위 스케줄 JSON 경로
  - `still_image_paths: list[str]` — Step 4 정지이미지 PNG 경로 (flat)

**환경변수 (`.env`):**
```
# API 키
NCP_CLOVA_API_KEY         # HCX-005 OCR/번역
OPENAI_API_KEY            # gpt-4o-mini 프롬프트
NOTION_API_KEY            # Notion DB 연동 (선택)

# TTS
EDGE_TTS_VOICE=ko-KR-SunHiNeural  # edge-tts 음성 (기본값)

# ComfyUI 이미지 생성
COMFYUI_HOST=http://127.0.0.1:8188
SD15_CHECKPOINT=Realistic_Vision_V5.1.safetensors
LORA_NAME=E38090E59BBDE9A38EE68F92E794BBE38091E58FABE7.G2A0.safetensors
LORA_STRENGTH=0.8
STILL_IMAGE_STEPS=30       # SD 1.5 샘플링 스텝 수
STILL_IMAGE_CFG=7.5        # CFG 스케일
COMFYUI_OUTPUT_DIR=ComfyUI/output
COMFYUI_INPUT_DIR=ComfyUI/input
COMFYUI_MAX_WAIT=1200      # 최대 대기(초)

# IP-Adapter (캐릭터 일관성, 선택)
IPADAPTER_MODEL=ip-adapter_sd15.bin
IPADAPTER_WEIGHT=0.5
CLIP_VISION_MODEL=clip_vision_h14.safetensors
REFERENCE_IMAGE_PATH=cache/reference/character.png
REFERENCE_IMAGE_PATH2=     # 두 번째 참조 이미지 (선택)

# 자막
SUBTITLE_FONT_PATH=C:/Windows/Fonts/malgun.ttf
```

## Step 주요 결정사항

**Step 0 (OCR):** HCX-005, 캐시 `cache/{poem_id}/step0_ocr.txt`

**Step 1 (NLP):** HCX-005 번역 + gpt-4o-mini 이미지 프롬프트, 캐시 `cache/{poem_id}/step1_nlp.json`

**Step 2 (edge-tts):** 문장 단위 MP3 + alignment JSON (추정 타임스탬프), 캐시 `cache/{poem_id}/step2_scene{NN}_sent{MM}_audio.mp3|_alignment.json`

**Step 3 (문장 스케줄링):** 문장 단위 duration/prompt/audio_path 매핑, 캐시 `cache/{poem_id}/step3_sentence_schedule.json`

**Step 4 (SD 1.5 정지이미지):** 국풍 LoRA + IP-Adapter, 캐시 `cache/{poem_id}/step4_scene{NN}_sent{MM}_still.png`

**Step 5 (병합):** 이미지+오디오 슬라이드쇼 + PIL 자막 burn-in, 씬 누적 오프셋 적용, 캐시 `cache/{poem_id}/step5_shorts.mp4`

**백엔드 (API):** FastAPI ThreadPoolExecutor(max_workers=2), Streamlit `@st.fragment(run_every=2)` 폴링

## 에이전트 자동 호출 (v2)

**⚠️ 중요: 이 표는 Claude Code 자신에 대한 지시입니다.**
코드에서 자동 호출되는 것이 아니라, Claude Code가 아래 상황을 감지했을 때 서브에이전트로 호출해야 합니다.

| 상황 | 에이전트 | 목적 |
|------|---------|------|
| 고전시가 원문 텍스트 입력 | `historical-context-agent` | 역사적 맥락 조사 |
| Step 2 (TTS) 완료 | `audio-visual-qa-agent` | 오디오-타임스탬프 타이밍 검증 |
| Step 3 (스케줄) 생성 완료 | `art-director-agent` | 정지이미지 프롬프트 최적화 |
| Step 4 (정지이미지) 생성 완료 | `quality-assurance-agent` | 이미지-대본 정합성 검증 |
| Step 5 (최종 영상) 생성 완료 | `seo-metadata-agent` | 메타데이터/제목/설명/해시태그 |
| Step 실행 에러 발생 | `pipeline-debug-agent` | 로그 분석 + 근본 원인 진단 |

## Skills (`.claude/skills/`)

| 스킬 | 트리거 | 목적 |
|------|--------|------|
| `pipeline-status-check` | "상태 확인", "어디까지 됐어" | Step 0~5 진행도 시각화 |
| `cache-integrity-check` | Step 에러 / "캐시 확인" | 캐시 파일 무결성 검증 |
| `comfyui-health-check` | Step 4 실패 / "ComfyUI 확인" | 서버·모델 파일 점검 |
| `env-setup-validator` | "환경변수 맞아?" | .env 필수 키 검증 |
| `step-output-preview` | "결과 봐줘" | Step별 캐시 요약 출력 |

## 파일 구조

### Step 모듈 (`notebook/`)
- `step0_ocr.py` — Step 0 HCX-005 OCR
- `step1_nlp.py` — Step 1 번역 + 씬 분할 + 이미지 프롬프트
- `step2_tts.py` — Step 2 edge-tts MP3 + alignment JSON
- `step3_scheduler.py` — Step 3 문장 단위 스케줄링
- `step4_image.py` — Step 4 ComfyUI SD 1.5 정지이미지 생성
- `step5_video.py` — Step 5 이미지+오디오+자막 최종 병합

### API (`api/`)
- `pipeline_runner.py` — 파이프라인 오케스트레이션 엔진
- `poem_registry.py` — 시가 레지스트리 (poem_id 관리)
- `models.py` — Pydantic 데이터 모델 (TaskStatus 등)
- `routes/steps.py` — Step 0~5 실행 엔드포인트
- `routes/tasks.py` — 작업 상태 조회
- `routes/upload.py` — 이미지 업로드

## 참고 자료 (rules/)

| 파일 | 핵심 내용 |
|------|----------|
| `bug_fixes_and_lessons.md` | v2 교훈: 타임스탬프 오프셋, VRAM 청크, 캐시 호환성 |
| `code-style.md` | 들여쓰기 2칸, snake_case, 타입힌팅, SRP, 디스크 캐싱, get_cache_path() 의무화 |
| `naming_conventions.md` | 엄격한 snake_case, 함수명 동사 시작, FastAPI `/api/v1/` 접두사 |
| `error_handling_logging.md` | 3회 재시도 + 지수 백오프, logging 모듈, 에러 시 Notion 동기화 |
| `git-rules.md` | 한글 커밋 메시지, feature/fix 브랜치, 커밋 전 `ruff check .` |
| `Security_Configuration.md` | 하드코딩 금지, `.env` + pydantic-settings |
| `cache-management.md` | 캐시 키 패턴, poem_dir 기반 경로, PersistentTaskDict 규칙 |
| `streamlit-patterns.md` | @st.cache_data 금지, @st.fragment 폴링 패턴 |

---

**마지막 업데이트:** 2026-04-03 (v2 문서 정비 — 실제 구현 반영, Skills 추가, 파일 구조 정리)
