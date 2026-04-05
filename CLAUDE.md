# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

고전시가 원문 이미지 → 수묵화 스타일 정지이미지 슬라이드쇼 쇼츠 자동 생성 파이프라인 **(v2 — Dynamic Clip Generator)**.

**현재 상태:** Step 0~6 전체 구현 완료 (edge-tts + ComfyUI Flux.1-dev FP8 정지이미지 + NanumSquare 자막 + Stable Audio BGM + 13개 이중 테마 시스템 + 지배적 정서).

## 기술 스택 (v2)

- **프론트엔드:** Streamlit (`app_ui.py`, 포트 8501)
- **백엔드:** FastAPI (`main_api.py`, 포트 8000)
- **LLM:** HCX-005 (OCR + 번역 + 테마/정서 분류 + 이미지 프롬프트), gpt-4o-mini (BGM 프롬프트)
- **음성:** edge-tts (한국어, 무료 — `ko-KR-SunHiNeural`)
- **이미지:** ComfyUI Flux.1-dev FP8 정지이미지 (국풍 LoRA)
- **자막:** PIL Image 기반 자막 이미지 (NanumSquare EB + 흰색 + 검은 외곽선) → MoviePy ImageClip Burn-in
- **BGM:** Stable Audio (`stabilityai/stable-audio-open-1.0`) — 테마/정서 기반 LLM 프롬프트 생성
- **최종 합성:** MoviePy + FFmpeg (이미지+오디오+자막+BGM 슬라이드쇼)
- **데이터:** Notion API (원문-번역 로깅)
- **패키지:** Python 3.12, uv

## 파이프라인 (v2 + 이중 테마 + 지배적 정서)

```
Step 0: OCR             HCX-005로 이미지 → 텍스트 추출
Step 1: NLP             번역 + 씬 분할 + 이중 테마 분류(primary/surface) + 지배적 정서(dominant_emotion)
Step 2: 음성+타임스탬프  edge-tts로 문장별 MP3 + alignment(추정 타임스탬프) JSON
Step 3: 프레임 스케줄    문장 단위 스케줄 JSON (duration, image_prompt, audio_path)
Step 4: 정지이미지       ComfyUI Flux.1-dev FP8 (국풍 LoRA)로 문장별 PNG 생성
Step 5: BGM 생성         Stable Audio → 테마별 악기/분위기 + 지배적 정서 기반 BGM WAV
Step 6: 최종 병합        이미지+오디오+자막+BGM 슬라이드쇼 (1080×1920, 30fps)
```

**이중 테마 시스템:** 13개 고전시가 테마 (강호자연~건국송축).
- `primary_theme`: 작품의 근본 주제 (시상/메시지)
- `surface_theme`: 시각적으로 드러나는 배경/소재 (이미지 프롬프트에 사용)
- `dominant_emotion`: 지배적 정서 코드 (E1~E7, BGM/이미지 분위기에 반영)

Step 1에서 분류 후 Step 2~6 전체 반영. `notebook/theme_config.py`가 단일 소스 역할.

## 캐시 구조 (이원화)

**CLI 실행** (`cd notebook && python step*.py`):
- 캐시 경로: `notebook/cache/{poem_id}/`
- CWD가 `notebook/`이므로 상대경로 `cache/{poem_id}/`로 접근

**UI 실행** (FastAPI + Streamlit):
- 캐시 경로: `upload_cache/{poem_id}/`
- 상태 파일: `upload_cache/task_states.json` (`PersistentTaskDict`)
- 레지스트리: `upload_cache/poem_registry.json` (`PoemRegistry`)
- 업로드: `upload_cache/uploads/{task_id}_{filename}`

**공통**: 각 Step 모듈의 `get_cache_path(poem_dir)` 함수는 `poem_dir` 인자를 받으므로, CLI든 UI든 동일하게 동작.

## 핵심 데이터 구조 (v2)

**상태 관리 (`task_status_dict`):**
- JSON 파일 기반 (`upload_cache/task_states.json`), `PersistentTaskDict` 클래스로 다중 프로세스 영속화
- 주요 필드:
  - `sentence_audio_paths: list[list[str]]` — Step 2 문장별 MP3 경로 `[씬][문장]`
  - `sentence_alignment_paths: list[list[str]]` — Step 2 문장별 alignment JSON 경로
  - `sentence_schedule_path: str | None` — Step 3 문장 단위 스케줄 JSON 경로
  - `still_image_paths: list[str]` — Step 4 정지이미지 PNG 경로 (flat)
  - `bgm_path: str | None` — Step 5 BGM WAV 경로

**NLP 출력 (`step1/nlp.json`) 주요 필드:**
- `primary_theme` / `primary_theme_en` — 근본 주제 테마
- `surface_theme` / `surface_theme_en` — 시각적 배경 테마
- `dominant_emotion` / `dominant_emotion_en` — 지배적 정서 (E1~E7)
- `modern_script_data` — 씬별 데이터 배열

**환경변수 (`.env`):**
```
# API 키
NCP_CLOVA_API_KEY         # HCX-005 OCR/번역
OPENAI_API_KEY            # gpt-4o-mini BGM 프롬프트
NOTION_API_KEY            # Notion DB 연동 (선택)

# TTS
EDGE_TTS_VOICE=ko-KR-SunHiNeural  # edge-tts 음성 (기본값)

# ComfyUI 이미지 생성
COMFYUI_HOST=http://127.0.0.1:8188
COMFYUI_OUTPUT_DIR=ComfyUI/output
COMFYUI_INPUT_DIR=ComfyUI/input
COMFYUI_MAX_WAIT=1200      # 최대 대기(초)

# Flux.1-dev FP8
FLUX_UNET=flux1-dev-fp8.safetensors
FLUX_LORA_NAME=GuoFeng5-FLUX.1-Lora.safetensors
FLUX_LORA_STRENGTH=0.8
FLUX_STEPS=20
FLUX_GUIDANCE=3.5

# Stable Audio BGM
STABLE_AUDIO_MODEL=stabilityai/stable-audio-open-1.0

# 자막
SUBTITLE_FONT_PATH=%LOCALAPPDATA%/Microsoft/Windows/Fonts/NanumSquare.ttf
```

## Step 주요 결정사항

**Step 0 (OCR):** HCX-005, 캐시 `{poem_dir}/step0/ocr.txt`

**Step 1 (NLP):** HCX-005 번역 + 이중 테마/정서 분류 + HCX-005 이미지 프롬프트, 캐시 `{poem_dir}/step1/nlp.json`

**Step 2 (edge-tts):** 문장 단위 MP3 + alignment JSON, 캐시 `{poem_dir}/step2/scene{NN}_sent{MM}_audio.mp3|_alignment.json`

**Step 3 (문장 스케줄링):** 문장 단위 duration/prompt/audio_path 매핑, 캐시 `{poem_dir}/step3/sentence_schedule.json`

**Step 4 (Flux.1-dev FP8 정지이미지):** 국풍 LoRA, 캐시 `{poem_dir}/step4/scene{NN}_sent{MM}_still.png`

**Step 5 (BGM):** Stable Audio 기반 BGM 생성, 테마별 악기/분위기 + 지배적 정서 LLM 프롬프트 주입, 캐시 `{poem_dir}/step5/bgm.wav`

**Step 6 (병합):** 이미지+오디오 슬라이드쇼 + NanumSquare 자막 burn-in (흰색+검은 외곽선, 65% 위치, 어절 단위 줄바꿈) + BGM 믹싱, 캐시 `{poem_dir}/step6/shorts.mp4`

**백엔드 (API):** FastAPI ThreadPoolExecutor(max_workers=2), Streamlit `@st.fragment(run_every=2)` 폴링

## 에이전트 자동 호출 (v2)

**이 표는 Claude Code 자신에 대한 지시입니다.**
코드에서 자동 호출되는 것이 아니라, Claude Code가 아래 상황을 감지했을 때 서브에이전트로 호출해야 합니다.

| 상황 | 에이전트 | 목적 |
|------|---------|------|
| 고전시가 원문 텍스트 입력 | `historical-context-agent` | 역사적 맥락 조사 |
| Step 0 (OCR) 완료 | `ocr-validation-agent` | OCR 결과 완전성·정확성 검증 |
| Step 1 (NLP) 완료 | `nlp-validation-agent` | 씬 분할·테마·정서·번역·프롬프트 품질 검증 |
| Step 2 (TTS) 완료 | `audio-visual-qa-agent` | 오디오-타임스탬프 타이밍 검증 |
| Step 3 (스케줄) 생성 완료 | `art-director-agent` | 정지이미지 프롬프트 최적화 |
| Step 4 (정지이미지) 생성 완료 | `quality-assurance-agent` | 이미지-대본 정합성 검증 |
| Step 5 (BGM) 생성 완료 | `bgm-verification-agent` | BGM 품질/길이/테마 검증 |
| Step 6 (최종 영상) 생성 완료 | `video-verification-agent` | 영상 스펙/오디오/자막 검증 |
| Step 6 (최종 영상) 생성 완료 | `seo-metadata-agent` | 메타데이터/제목/설명/해시태그 |
| Step 실행 에러 발생 | `pipeline-debug-agent` | 로그 분석 + 근본 원인 진단 |

## Skills (`.claude/skills/`)

| 스킬 | 트리거 | 목적 |
|------|--------|------|
| `pipeline-status-check` | "상태 확인", "어디까지 됐어" | Step 0~6 진행도 시각화 |
| `cache-integrity-check` | Step 에러 / "캐시 확인" | 캐시 파일 무결성 검증 |
| `comfyui-health-check` | Step 4 실패 / "ComfyUI 확인" | 서버/모델 파일 점검 |
| `env-setup-validator` | "환경변수 맞아?" | .env 필수 키 검증 |
| `step-output-preview` | "결과 봐줘" | Step별 캐시 요약 출력 |

## 파일 구조

### Step 모듈 (`notebook/`)
- `step0_ocr.py` — Step 0 HCX-005 OCR
- `step1_nlp.py` — Step 1 번역 + 씬 분할 + 이중 테마/정서 분류 + 이미지 프롬프트
- `step2_tts.py` — Step 2 edge-tts MP3 + alignment JSON
- `step3_scheduler.py` — Step 3 문장 단위 스케줄링
- `step4_image.py` — Step 4 ComfyUI Flux.1-dev FP8 정지이미지 생성
- `step5_bgm.py` — Step 5 Stable Audio BGM 생성 (테마/정서 기반 WAV)
- `step6_video.py` — Step 6 이미지+오디오+자막+BGM 최종 병합
- `theme_config.py` — 13개 테마 + 7개 정서 설정 단일 소스

### API (`api/`)
- `pipeline_runner.py` — 파이프라인 오케스트레이션 엔진
- `poem_registry.py` — 시가 레지스트리 (poem_id 관리)
- `models.py` — Pydantic 데이터 모델 (TaskStatus 등)
- `routes/steps.py` — Step 0~6 실행 엔드포인트
- `routes/tasks.py` — 작업 상태 조회
- `routes/upload.py` — 이미지 업로드
- `routes/files.py` — 캐시 파일 서빙 (poem_id 기반)

## 참고 자료 (rules/)

| 파일 | 핵심 내용 |
|------|----------|
| `data-flow.md` | nlp.json 필드 → Step 2~6 영향 지도 (표·다이어그램) |
| `bug_fixes_and_lessons.md` | v2 교훈: 타임스탬프 오프셋, VRAM 청크, 캐시 호환성 |
| `code-style.md` | 들여쓰기 2칸, snake_case, 타입힌팅, SRP, get_cache_path() 의무화 |
| `naming_conventions.md` | 엄격한 snake_case, 함수명 동사 시작, FastAPI `/api/v1/` 접두사 |
| `error_handling_logging.md` | 3회 재시도 + 지수 백오프, logging 모듈, 에러 시 Notion 동기화 |
| `git-rules.md` | 한글 커밋 메시지, feature/fix 브랜치, 커밋 전 `ruff check .` |
| `Security_Configuration.md` | 하드코딩 금지, `.env` + pydantic-settings |
| `cache-management.md` | 캐시 이원화 (CLI: notebook/cache, UI: upload_cache), poem_dir 기반 |
| `streamlit-patterns.md` | @st.cache_data 금지, @st.fragment 폴링 패턴 |

---

**마지막 업데이트:** 2026-04-05 (Flux.1-dev FP8 전환 + SD1.5/ControlNet/IP-Adapter 제거 + pose_type 18종 확장)
