# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

고전시가 원문 이미지 → 웹툰 스타일 쇼츠 영상 자동 생성 파이프라인.

**현재 상태:** Step 0~1 정상 (OCR → NLP), Step 2~5 구현 완료, Step 6 웹 UI 완료 (FastAPI + Streamlit), Step 7 예정.

## 기술 스택

- **프론트엔드:** Streamlit (`app_ui.py`, 포트 8501)
- **백엔드:** FastAPI (`main_api.py`, 포트 8000)
- **LLM:** HCX-005 (OCR + 번역), gpt-4o-mini (이미지 프롬프트)
- **이미지:** ComfyUI API (포트 8188, FLUX.1 Dev)
- **음성:** Edge-TTS (로컬)
- **영상:** MoviePy + FFmpeg
- **데이터:** Notion API (원문-번역 로깅)
- **패키지:** Python 3.12, uv

## 파이프라인

```
Step 0: OCR      HCX-005로 이미지 → 텍스트 추출
Step 1: NLP      번역 + 씬 분할 (원문, 현대어, 나레이션, 감정, 배경)
Step 2: 이미지   ComfyUI FLUX로 씬당 이미지 생성 (512×912)
Step 3: 오디오   Edge-TTS로 나레이션 음성 생성
Step 4: 자막     SRT 자막 생성
Step 5: 영상     MoviePy로 이미지+오디오+자막 합성 (1080×1920)
Step 6: UI       FastAPI 백엔드 + Streamlit 프론트엔드
Step 7: 업로드   YouTube Data API v3로 Shorts 업로드
```

## 핵심 데이터 구조

**상태 관리 (`task_status_dict`):**
- JSON 파일 기반 (`cache/task_states.json`), 다중 프로세스 공유
- `task_id`, `current_step`, `status`, `status_message`, `error_log`
- 각 Step 결과: `ocr_text`, `nlp_cache_path`, `image_paths`, `audio_paths`, `subtitle_path`, `video_path`

**환경변수 (`.env`):**
```
NCP_CLOVA_API_KEY, OPENAI_API_KEY, NOTION_API_KEY
COMFYUI_HOST=http://127.0.0.1:8188 (기본값)
```

## Step 주요 결정사항

**Step 0 (OCR):** HCX-005로 고전시가 텍스트 추출, 캐시는 `cache/step0/{이미지명}_ocr.txt`

**Step 1 (NLP):** gpt-4o-mini로 번역+씬분할, 캐시는 `cache/step1/{hash8}_nlp.json` (항상 저장, `use_cache` 무관)

**Step 2 (이미지):** ComfyUI FLUX로 512×912 이미지 생성 (씬당 30~45초)

**Step 3 (음성):** Edge-TTS로 나레이션 음성 생성, 캐시 키는 MD5(`text|voice|rate|pitch`)

**Step 4 (자막):** SRT 형식, `cache/step4/{hash8}_subtitles.srt`, audio-visual-qa 리포트 생성

**Step 5 (영상):** MoviePy로 합성, 1080×1920, qa 리포트의 `scene_durations` 사용

**Step 6 (UI):** FastAPI는 ThreadPoolExecutor(max_workers=2) + asyncio, Streamlit는 `@st.fragment(run_every=2)` 폴링

## 에이전트 자동 호출

| 상황 | 에이전트 | 목적 |
|------|---------|------|
| 고전시가 원문 텍스트 입력 | `historical-context-agent` | 역사적 맥락 조사 |
| Step 2 프롬프트 생성/수정 | `art-director-agent` | ComfyUI 프롬프트 최적화 |
| 이미지 생성 완료 | `quality-assurance-agent` | 대본-이미지 검증 + 자가 치유 |
| 오디오 생성 완료 | `audio-visual-qa-agent` | 음성-이미지 조화 검증 |
| 영상 생성 완료 | `seo-metadata-agent` | 메타데이터/제목/설명/해시태그 생성 |

## 참고 자료

- **개발 교훈:** `.claude/rules/bug_fixes_and_lessons.md` (캐시 일관성, Streamlit 폴링 패턴)
- **코드 스타일:** `.claude/rules/code-style.md`, `naming_conventions.md`, `error_handling_logging.md`, `git-rules.md`
- **보안:** `.claude/rules/Security_Configuration.md` (하드코딩 금지, .env 사용)

---

**마지막 업데이트:** 2026-03-30 (Step 0~1 버그 수정 완료, 불필요 파일 정리, CLAUDE.md 경량화)
