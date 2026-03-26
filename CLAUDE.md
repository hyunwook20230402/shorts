# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

고전시가 원문 이미지를 입력받아 웹툰 스타일 쇼츠 영상을 자동 생성하고 유튜브에 업로드하는 파이프라인 프로젝트.

**현재 상태:** 설계 단계 (구현 코드 없음, PRD 작성 중)

## 기술 스택

- **프론트엔드:** Streamlit (`app_ui.py`)
- **백엔드:** FastAPI (`main_api.py`)
- **데이터베이스:** Notion API (Notion Database)
- **LLM:** gpt-4o-mini (OCR + 번역)
- **이미지 생성:** ComfyUI API (포트 8188, 웹툰 LoRA 적용)
- **TTS:** Edge-TTS (로컬) / ElevenLabs (API)
- **영상 합성:** FFmpeg + MoviePy
- **언어:** Python 3.11

## 파이프라인 구조

```
Step 0: OCR       이미지(PNG/JPG) → extracted_raw_text
Step 1: NLP       원문 번역 + 씬 분할 + Notion DB 로깅 → modern_script_data, image_prompts
Step 2: Vision    ComfyUI API → generated_image_paths (512×910)
Step 3: Audio     TTS API → generated_audio_paths
Step 4: Video     MoviePy → final_video_path (1080×1920, 9:16)
Step 5: Publish   YouTube Data API v3 → Shorts 업로드 (60초 미만)
```

## 핵심 데이터 구조

**상태 관리 객체 (`task_status_dict`):**
- `task_id` (str, UUID)
- `current_step` (int, 0-5)
- `status_message` (str)
- `is_completed` (bool)
- `error_log` (dict)

**Notion Database:**
- `poem_translation_log`: `original_archaic_text`(X) + `translated_modern_text`(y) 쌍 저장 → 파인튜닝 데이터셋
- `task_status_log`: 파이프라인 실행 이력

**환경변수 (`.env` 필수):**
```
NOTION_API_KEY
NOTION_POEM_LOG_DB_ID
NOTION_TASK_STATUS_DB_ID
OPENAI_API_KEY
YOUTUBE_API_KEY
ELEVENLABS_API_KEY  # 선택
```

## 코드 스타일

- 들여쓰기: 스페이스 2칸
- 변수명: `camelCase` (JS/TS) / `snake_case` (Python - 파이프라인 데이터 변수)
- 함수명: 동사로 시작 (`extract_text_from_image`, `generate_image_prompt`)
- 주석: 한국어
- Python 타입힌트 필수 (3.10+ 문법)
- `logging` 모듈 사용 (`print` 금지)
- API 경로: `/api/v1/` 접두사

## 구현 규칙

- 모든 API 호출: retry 3회 + 지수 백오프
- 중간 결과물 디스크 캐시 필수
- 환경변수: `.env` 파일 (하드코딩 금지)
- 단일 책임 원칙: 한 함수 = 한 가지 역할

## Git 규칙

- **커밋 전 린트 실행 필수**
- 커밋 메시지: 한국어
- 브랜치명: `feature/기능명` 형식

## 에이전트 구성 (`.claude/agents/`)

| 에이전트 | 역할 |
|---------|------|
| `prd-writer-shorts` | PRD 작성/업데이트 전담 |
| `prd-validator` | PRD 완성도 검증 |
| `historical-context-agent` | 고전시가 역사적 배경 조사 |
| `art-director-agent` | ComfyUI 프롬프트 최적화 |
| `seo-metadata-agent` | YouTube 업로드 메타데이터 생성 |
| `quality-assurance-agent` | 생성 이미지-대본 정합성 검증 |

PRD 관련 작업 시 항상 `prd-writer-shorts` 에이전트를 사용할 것.
