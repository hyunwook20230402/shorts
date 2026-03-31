# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

고전시가 원문 이미지 → 수묵화 스타일 동적 동영상 쇼츠 자동 생성 파이프라인 **(v2 — Dynamic Clip Generator)**.

**현재 상태:** Step 0~1 정상 (OCR → NLP), Step 2~5 v2 파이프라인 구현 완료 (ElevenLabs TTS + AnimateDiff).

## 기술 스택 (v2)

- **프론트엔드:** Streamlit (`app_ui.py`, 포트 8501)
- **백엔드:** FastAPI (`main_api.py`, 포트 8000)
- **LLM:** HCX-005 (OCR + 번역), gpt-4o-mini (시각 프롬프트)
- **음성:** ElevenLabs API (타임스탬프 포함)
- **영상:** ComfyUI AnimateDiff (SD 1.5 + 국풍 LoRA)
- **자막:** MoviePy TextClip (타임스탬프 기반 Burn-in)
- **최종 합성:** MoviePy + FFmpeg
- **데이터:** Notion API (원문-번역 로깅)
- **패키지:** Python 3.12, uv

## 파이프라인 (v2)

```
Step 0: OCR             HCX-005로 이미지 → 텍스트 추출
Step 1: NLP             번역 + 씬 분할 (원문, 현대어, 나레이션, 감정, 배경)
Step 2: 음성+타임스탬프 ElevenLabs로 MP3 + alignment(단어/문장 타임스탬프) JSON
Step 3: 프레임 스케줄   alignment × FPS(10) → AnimateDiff BatchPromptSchedule JSON
Step 4: 영상 클립       ComfyUI AnimateDiff (SD1.5+국풍 LoRA)로 씬별 무성 MP4 클립
Step 5: 최종 병합       클립 연결 + 타임스탬프 기반 자막 Burn-in + MP3 싱크 (1080×1920, 30fps)
```

## 핵심 데이터 구조 (v2)

**상태 관리 (`task_status_dict`):**
- JSON 파일 기반 (`cache/task_states.json`), 다중 프로세스 공유
- 신규 필드:
  - `audio_paths: list[str]` — Step 2 ElevenLabs MP3 경로
  - `tts_alignment_paths: list[str]` — Step 2 alignment JSON 경로
  - `frame_schedule_path: str | None` — Step 3 BatchPromptSchedule JSON 경로
  - `video_clip_paths: list[str]` — Step 4 AnimateDiff MP4 클립 경로

**환경변수 (`.env`):**
```
# 기존
NCP_CLOVA_API_KEY, OPENAI_API_KEY, NOTION_API_KEY
COMFYUI_HOST=http://127.0.0.1:8188

# 신규 (v2)
ELEVENLABS_API_KEY=your_key
ELEVENLABS_VOICE_ID=your_voice_id (기본: onwK4e9ZDvw9KNAVq4mQ)
SD15_CHECKPOINT=Realistic Vision v5.1.safetensors
ANIMATEDIFF_MOTION_MODULE=mm_sd_v15_v2.ckpt
LORA_NAME=【国风插画】古风.safetensors
LORA_STRENGTH=0.8
ANIMATEDIFF_FPS=10
ANIMATEDIFF_CHUNK_SIZE=16
SUBTITLE_FONT_PATH=C:/Windows/Fonts/malgun.ttf
```

## Step 주요 결정사항

**Step 0 (OCR):** HCX-005, 캐시 `cache/step0/{이미지명}_ocr.txt`

**Step 1 (NLP):** gpt-4o-mini, 캐시 `cache/step1/{hash8}_nlp.json`

**Step 2 (ElevenLabs):** alignment JSON 구조 (words, sentences, total_duration), 캐시 `cache/step2/{hash8}_{idx}_audio.mp3|_alignment.json`

**Step 3 (동적 스케줄링):** LLM으로 프롬프트 생성, 공통 키워드 자동 삽입, 캐시 `cache/step3/{hash8}_schedule.json`

**Step 4 (AnimateDiff):** CHUNK_SIZE=16 (VRAM 보호), SD1.5+LoRA, 캐시 `cache/step4/{hash8}_{idx}_clip.mp4`

**Step 5 (병합):** 타임스탬프 기반 자막, 씬 누적 오프셋 적용, 캐시 `cache/step5/{hash8}_shorts.mp4`

**Step 6 (UI):** FastAPI ThreadPoolExecutor(max_workers=2), Streamlit `@st.fragment(run_every=2)` 폴링

## 에이전트 자동 호출 (v2)

**⚠️ 중요: 이 표는 Claude Code 자신에 대한 지시입니다.**
코드에서 자동 호출되는 것이 아니라, Claude Code가 아래 상황을 감지했을 때 서브에이전트로 호출해야 합니다.

| 상황 | 에이전트 | 목적 |
|------|---------|------|
| 고전시가 원문 텍스트 입력 | `historical-context-agent` | 역사적 맥락 조사 |
| Step 2 (ElevenLabs TTS) 완료 | `audio-visual-qa-agent` | 오디오-타임스탬프 조화 검증 |
| Step 3 (스케줄) 생성 완료 | `art-director-agent` | AnimateDiff 프롬프트 최적화 |
| Step 4 (AnimateDiff 클립) 생성 완료 | `quality-assurance-agent` | 클립-대본 정합성 검증 |
| Step 5 (최종 영상) 생성 완료 | `seo-metadata-agent` | 메타데이터/제목/설명/해시태그 |

## 새로 추가된 파일 (v2)

- `step2_tts.py` — Step 2 ElevenLabs TTS + alignment JSON
- `step3_scheduler.py` — Step 3 AnimateDiff 프레임 스케줄링
- `step4_clip.py` — Step 4 AnimateDiff 클립 생성 (ComfyUI API)
- `step5_video.py` — Step 5 자막 burn-in + 최종 병합

## 참고 자료

- **v2 교훈:** `.claude/rules/bug_fixes_and_lessons.md` (Section 4~6: 타임스탐프, VRAM, 호환성)
- **코드 스타일:** `.claude/rules/code-style.md`, `naming_conventions.md`, `error_handling_logging.md`, `git-rules.md`
- **보안:** `.claude/rules/Security_Configuration.md` (하드코딩 금지, .env 사용)

---

**마지막 업데이트:** 2026-03-31 (PRD v2 구현 완료 — ElevenLabs + AnimateDiff + 동적 스케줄링)
