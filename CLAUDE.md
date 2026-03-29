# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

고전시가 원문 이미지를 입력받아 웹툰 스타일 쇼츠 영상을 자동 생성하고 유튜브에 업로드하는 파이프라인 프로젝트.

**현재 상태:** Step 0~5 완료 (OCR → NLP → 이미지 → 오디오 → 자막 → 영상), **Step 6 웹 UI 완료** (FastAPI + Streamlit), Step 7 (YouTube 업로드) 예정

## 기술 스택

- **프론트엔드:** Streamlit (`app_ui.py`) — 포트 8501
- **백엔드:** FastAPI (`main_api.py`) — 포트 8000
- **데이터베이스:** Notion API (Notion Database)
- **LLM:** gpt-4o-mini (OCR + 번역)
- **이미지 생성:** ComfyUI API (포트 8188, 웹툰 LoRA 적용)
- **TTS:** Edge-TTS (로컬) / ElevenLabs (API)
- **영상 합성:** FFmpeg + MoviePy
- **언어:** Python 3.12 (uv 패키지 관리)

## 파이프라인 구조

```
Step 0: OCR        이미지(PNG/JPG) → extracted_raw_text
Step 1: NLP        원문 번역 + 씬 분할 + Notion DB 로깅 → modern_script_data, image_prompts
Step 2: Vision     ComfyUI API → generated_image_paths (512×912, 9:16)
Step 3: Audio      TTS API → generated_audio_paths (list[str])
Step 4: Subtitle   SRT 자막 생성 → subtitle_path (str)
Step 5: Video      MoviePy → final_video_path (1080×1920, 9:16)
Step 6: Web UI     FastAPI 백엔드 + Streamlit 프론트엔드 (파이프라인 실행 UI)
Step 7: Publish    YouTube Data API v3 → Shorts 업로드 (60초 미만)
```

## 핵심 데이터 구조

**상태 관리 객체 (`task_status_dict`):**
- `task_id` (str, UUID), `current_step` (int, 0-5), `status` (pending/running/completed/failed)
- `status_message`, `error_log`, `created_at`, `updated_at`
- 각 Step 결과 경로: `ocr_text`, `nlp_cache_path`, `image_paths`, `audio_paths`, `subtitle_path`, `video_path`

**Notion Database:**
- `poem_translation_log`: 원문-현대어 쌍 저장 (파인튜닝 데이터셋)
- `task_status_log`: 파이프라인 실행 이력

**환경변수 (`.env` 필수):**
```
NOTION_API_KEY, NOTION_POEM_LOG_DB_ID, NOTION_TASK_STATUS_DB_ID
OPENAI_API_KEY, YOUTUBE_API_KEY, ELEVENLABS_API_KEY (선택)
COMFYUI_HOST=http://127.0.0.1:8188
```

## 코드 스타일

- 들여쓰기: 스페이스 2칸
- 변수명: `snake_case` (Python), `camelCase` (JS/TS)
- 함수명: 동사로 시작 (`extract_text_from_image`, `generate_image_prompt`)
- 주석: 한국어
- 타입힌트: Python 3.10+ 필수
- `logging` 모듈 사용 (`print` 금지)
- API 경로: `/api/v1/` 접두사

## 구현 규칙

- 모든 API 호출: retry 3회 + 지수 백오프 (tenacity 라이브러리)
- 중간 결과물 디스크 캐시 필수 (cache/stepN/ 디렉토리)
- 환경변수: `.env` 파일 (하드코딩 금지)
- 단일 책임 원칙: 한 함수 = 한 가지 역할

## Step 주요 결정사항

### Step 0: OCR
- HCX-005 API (NCP Clova Studio)로 고전시가 텍스트 추출
- 캐시: `cache/step0/{이미지명}_ocr.txt`

### Step 1: NLP
- gpt-4o-mini로 번역 + 씬 분할 (화자, 감정, 배경, 나레이션)
- Notion DB 자동 로깅
- 캐시: `cache/step1/{hash8}_nlp.json`
- **주의**: 캐시 경로는 `step1_nlp.get_cache_path()` 함수만 사용 (Rule 1 in bug_fixes_and_lessons.md)

### Step 2: ComfyUI
- **노드**: DualCLIPLoader + EmptyFlux2LatentImage (2배 해상도) + KSampler
- **모델**: FLUX.1 Dev fp8 (17.2GB, 첫 로드 5~7분)
- **로컬 기본값**: `http://127.0.0.1:8188`
- **생성 시간**: 씬당 30~45초, 폴링 1초 간격

### Step 3: TTS (Edge-TTS)
- **캐시 키**: `hashlib.md5(f'{text}|{voice}|{rate}|{pitch}'.encode()).hexdigest()[:8]`
- **주의**: Python `hash()` 금지 (PYTHONHASHSEED 의존성)
- **pitch 단위**: Hz 사용 (% 아님)

### Step 4: 자막 (SRT)
- **포맷**: SubRip, `narration` 필드 사용
- **캐시**: `cache/step4/{hash8}_subtitles.srt`
- **audio-visual-qa**: `cache/step4/audio_visual_qa_report.json` 생성

### Step 5: 영상 (MoviePy)
- **출력**: `cache/step5/{hash8}_shorts.mp4` (1080×1920, 9:16, 60초 이내)
- **타이밍**: audio-visual-qa 리포트의 `scene_durations` 배열 사용

### Step 6: Web UI
- **FastAPI** 비동기 처리: `ThreadPoolExecutor(max_workers=2)` + `asyncio.run_in_executor()`
- **Streamlit** 폴링: `@st.fragment(run_every=2)` (캐시 제거, 전체 페이지 깜빡임 방지)
- **상태 관리**: 인메모리 `task_status_dict[task_id: str]: TaskStatus`

## 에이전트 자동 호출 규칙 (IMPORTANT)

| 상황 | 에이전트 | 목적 |
|------|---------|------|
| 고전시가 원문 텍스트 입력 | `historical-context-agent` | Step 1 NLP 전 역사적 맥락 조사 |
| Step 2 이미지 프롬프트 생성/수정 | `art-director-agent` | ComfyUI 프롬프트 최적화 |
| ComfyUI 이미지 생성 완료 | `quality-assurance-agent` | 대본-이미지 정합성 검증 + 자가 치유 |
| Step 3 오디오 생성 완료 | `audio-visual-qa-agent` | 음성-이미지 조화 검증 + 타이밍 파라미터 산출 |
| Step 5 영상 생성 완료 | `seo-metadata-agent` | 메타데이터/제목/설명/해시태그 → `cache/step5/{hash8}_seo_metadata.json` |
| 새 기능/파이프라인 기획 | `prd-writer-shorts` | 표준 PRD 작성 |
| PRD 작성 완료 | `prd-validator` | 완성도/명확성/실현 가능성 검증 |

## Git 규칙

- **커밋 전 린트 실행 필수** (ruff check)
- **커밋 메시지**: 한국어
- **브랜치명**: `feature/기능명` 형식
- **계획 완료 후 자동 커밋** (plan mode 규칙)

## 주요 참고 자료

- **개발 교훈 및 버그 해결**: `.claude/rules/bug_fixes_and_lessons.md` 참고
- **코드 스타일**: `.claude/rules/code-style.md`, `.claude/rules/naming_conventions.md`
- **Step 2 품질 개선 로드맵**: `.claude/plans/step2-quality-upgrade-roadmap.md`
- **에러 처리**: `.claude/rules/error_handling_logging.md`

## 트러블슈팅

**ComfyUI 연결 실패**:
- `COMFYUI_HOST` 환경변수 확인 (기본값: `http://127.0.0.1:8188`)
- `netstat -ano | grep 8188`으로 프로세스 상태 확인

**Step 캐시 무효화**:
- 각 Step 모듈의 `get_cache_path()` 함수 사용 (Rule 1-2)
- API 라우터에서 `use_cache` 파라미터 명시적 전달 (Rule 3)

**Streamlit 폴링 이슈**:
- `@st.cache_data(ttl=N)` 금지 (부작용 야기)
- `@st.fragment(run_every=N)` 사용 (폴링 블록만 재실행)

**Step 1 NLP 결과 미표시**:
- `@st.cache_data` 제거, 매 폴링마다 실제 API 조회
- 완료 시에만 `st.rerun()` 호출

---

**마지막 업데이트**: 2026-03-30 (bug_fixes_and_lessons.md 통합, CLAUDE.md 경량화)
