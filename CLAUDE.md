# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

고전시가 원문 이미지를 입력받아 웹툰 스타일 쇼츠 영상을 자동 생성하고 유튜브에 업로드하는 파이프라인 프로젝트.

**현재 상태:** Step 0~2 완료, Step 3~5 구축 진행 중

## 기술 스택

- **프론트엔드:** Streamlit (`app_ui.py`)
- **백엔드:** FastAPI (`main_api.py`)
- **데이터베이스:** Notion API (Notion Database)
- **LLM:** gpt-4o-mini (OCR + 번역)
- **이미지 생성:** ComfyUI API (포트 8188, 웹툰 LoRA 적용)
- **TTS:** Edge-TTS (로컬) / ElevenLabs (API)
- **영상 합성:** FFmpeg + MoviePy
- **언어:** Python 3.12 (uv 패키지 관리)

## 파이프라인 구조

```
Step 0: OCR       이미지(PNG/JPG) → extracted_raw_text
Step 1: NLP       원문 번역 + 씬 분할 + Notion DB 로깅 → modern_script_data, image_prompts
Step 2: Vision    ComfyUI API → generated_image_paths (512×912, 9:16)
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

## Step 2 주요 기술 결정사항 (ComfyUI)

### Workflow 노드 구조
- **DualCLIPLoader**: clip_l + t5xxl 동시 로드 (FLUX.1 필수)
- **EmptyFlux2LatentImage**: 입력 해상도 = 원하는 출력의 2배 (ComfyUI 50% 축소 보정)
- **KSampler**: steps=20, cfg=3.5, sampler=euler, scheduler=karras

### ComfyUI 서버 설정 (로컬)
- 주소: `http://127.0.0.1:8188`
- 모델: FLUX.1 Dev fp8 (17.2GB, 첫 로드 5~7분)
- 생성 시간: 씬당 30~45초
- 폴링: 1초 간격, 최대 1800초

## Git 규칙

- **커밋 전 린트 실행 필수** (ruff check)
- 커밋 메시지: 한국어
- 브랜치명: `feature/기능명` 형식
- Step 단위로 의미있는 커밋 분리

## 에이전트 구성 (`.claude/agents/`)

| 에이전트 | 역할 |
|---------|------|
| `prd-writer-shorts` | PRD 작성/업데이트 전담 |
| `prd-validator` | PRD 완성도 검증 |
| `historical-context-agent` | 고전시가 역사적 배경 조사 |
| `art-director-agent` | ComfyUI 프롬프트 최적화 |
| `seo-metadata-agent` | YouTube 업로드 메타데이터 생성 |
| `quality-assurance-agent` | 생성 이미지-대본 정합성 검증 |

## 에이전트 자동 호출 규칙 (IMPORTANT)

아래 조건에 해당하면 반드시 해당 에이전트를 먼저 호출할 것.
직접 처리하거나 일반 Explore 에이전트로 대체하지 말 것.

| 상황 | 호출할 에이전트 | 목적 |
|------|-------------|------|
| 고전시가 원문 텍스트 입력됨 | `historical-context-agent` | Step 1 NLP 전, 역사적 맥락 조사 |
| Step 2 이미지 프롬프트 생성/수정 필요 | `art-director-agent` | ComfyUI 프롬프트 최적화 |
| ComfyUI 이미지 생성 완료 | `quality-assurance-agent` | 대본-이미지 정합성 검증 + 자가 치유 루프 |
| 대본/영상 완성 후 YouTube 업로드 준비 | `seo-metadata-agent` | 메타데이터/제목/설명/해시태그 생성 |
| 새 기능/파이프라인 스텝 기획 시작 | `prd-writer-shorts` | 표준 PRD 작성 |
| PRD 작성 완료 | `prd-validator` | 완성도/명확성/실현 가능성 검증 |

## Step 2 개발 교훈 및 향후 계획

### 1차 완료 (2026-03-28)
- **목표:** 고전시가 텍스트 → 웹툰 이미지 자동 생성 (기초 파이프라인)
- **결과:** 7개 씬 PNG 생성, 해상도 512×912 (9:16)
- **주요 오류 및 해결:**
  1. CLIPLoader 단일 사용 → DualCLIPLoader로 교체 (t5xxl KeyError)
  2. 해상도 256×456 부족 → EmptyFlux2LatentImage 2배 입력 (ComfyUI 50% 축소 보정)
  3. 30분 타임아웃 → ComfyUI 프로세스 재시작 + 폴링 로직 개선

### 2차 계획 (Step 3~5 후 수행)
- **목표:** 웹툰 고품질화 (대본-이미지 정합성, 캐릭터 일관성, 컷 연결성)
- **방법:**
  1. 국립중앙박물관 오픈 이미지 API로 조선시대 풍속화 수집 (저작권 문제없음)
  2. FLUX.1 + LoRA 학습 (kohya_ss 또는 SimpleTuner)
  3. 캐릭터 Dreambooth LoRA로 외모 일관성 확보
  4. IPAdapter로 씬 간 연결성 개선 (img2img)
  5. 컷 수 확장: 7개 → 20~30개
- **자세한 로드맵:** `.claude/plans/` 참고
