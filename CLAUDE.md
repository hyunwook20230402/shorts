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
| `audio-visual-qa-agent` | 음성+이미지 조화 검증, Step 4 타이밍 파라미터 산출 |

## 에이전트 자동 호출 규칙 (IMPORTANT)

아래 조건에 해당하면 반드시 해당 에이전트를 먼저 호출할 것.
직접 처리하거나 일반 Explore 에이전트로 대체하지 말 것.

| 상황 | 호출할 에이전트 | 목적 |
|------|-------------|------|
| 고전시가 원문 텍스트 입력됨 | `historical-context-agent` | Step 1 NLP 전, 역사적 맥락 조사 |
| Step 2 이미지 프롬프트 생성/수정 필요 | `art-director-agent` | ComfyUI 프롬프트 최적화 |
| ComfyUI 이미지 생성 완료 | `quality-assurance-agent` | 대본-이미지 정합성 검증 + 자가 치유 루프 |
| Step 3 오디오 생성 완료 | `audio-visual-qa-agent` | 음성-이미지 조화 검증 + Step 4 타이밍 파라미터 산출 |
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
- **자세한 로드맵:** `.claude/plans/step2-quality-upgrade-roadmap.md` 참고

## ComfyUI 서버 환경 상세

### 로컬 서버 (현재 기본값)
- **주소:** `http://127.0.0.1:8188`
- **OS:** Windows 11, ComfyUI v0.18.1
- **GPU:** NVIDIA RTX 4070 Laptop (8GB VRAM, cudaMallocAsync)
- **커스텀 노드:** KJ 노드 없음 (DiffusionModelLoaderKJ, VAELoaderKJ 사용 불가)
- **모델 경로:** `flux1-dev-fp8.safetensors` (prefix 없음)
- **성능:**
  - 모델 첫 로드: 5~7분 (캐싱 후 2분)
  - 씬당 생성 시간: 30~45초
  - 최대 폴링 대기: 1800초

### 외부 서버 (선택사항)
- **주소:** `http://100.95.34.69:8188`
- **OS:** Linux, ComfyUI v0.18.1, Python 3.13
- **GPU:** NVIDIA RTX 4090
- **커스텀 노드:** KJ 노드 있음 (DiffusionModelLoaderKJ, VAELoaderKJ 사용 가능)
- **모델 경로:** `FLUX1/flux1-dev-fp8.safetensors` (FLUX1/ prefix 필요)

### 설치된 모델 (로컬 기준)
| 종류 | 파일명 | 폴더 |
|------|--------|------|
| Diffusion | flux1-dev-fp8.safetensors | diffusion_models/ |
| Diffusion | flux1-dev.safetensors | checkpoints/ |
| VAE | ae.safetensors | vae/ |
| CLIP | clip_l.safetensors | clip/ |
| T5 CLIP | t5xxl_fp8_e4m3fn.safetensors | clip/ |

## 로컬 서버 검증된 Workflow 노드 구조 (2026-03-28)

```
1. UNETLoader
   - unet_name: flux1-dev-fp8.safetensors
   - weight_dtype: fp8_e4m3fn

2. VAELoader
   - vae_name: ae.safetensors

3. DualCLIPLoader (필수: clip_l + t5xxl 동시 로드)
   - clip_name1: clip_l.safetensors
   - clip_name2: t5xxl_fp8_e4m3fn.safetensors
   - type: flux

4. CLIPTextEncodeFlux
   - clip: [3, 0]
   - clip_l: <TEXT_PROMPT>
   - t5xxl: <TEXT_PROMPT>
   - guidance: 3.5

5. EmptyFlux2LatentImage (해상도 보정: 원하는 출력의 2배 입력)
   - width: 1024 (원하는 출력 512의 2배)
   - height: 1824 (원하는 출력 912의 2배)
   - batch_size: 1

6. KSampler
   - seed: <random>
   - steps: 20
   - cfg: 3.5
   - sampler_name: euler
   - scheduler: karras
   - denoise: 1.0

7. VAEDecode
   - samples: [6, 0]
   - vae: [2, 0]

8. SaveImage
   - filename_prefix: shorts_
```

**⚠️ 주의:** 현재 로컬 ComfyUI는 입력 해상도의 50%로 출력함.
원하는 최종 해상도의 2배를 입력해야 함 (1024×1824 입력 → 512×912 출력).

## Step 2 개발 중 오류 및 해결책 (필독: 반복 금지)

### 오류 1: 서버 주소 혼동
외부 IP와 로컬을 혼동 → 테스트 결과 엉뚱함
**→ 항상 .env의 COMFYUI_HOST 값 기준으로만 판단. IP 하드코딩 금지.**

### 오류 2: /object_info 없이 파라미터 추측
허용되지 않는 값 임의 작성 → 400 Bad Request 반복
**→ 새 ComfyUI 서버 연결 시 반드시 /object_info 먼저 확인.**

### 오류 3: 모델 타입별 로더 혼동
fp8 모델인데 CheckpointLoaderSimple 사용 → 모델 목록 비어있음
**→ diffusion_models 경로면 DiffusionModelLoaderKJ (또는 UNETLoader) 사용.**

### 오류 4: CLIPTextEncodeFlux 파라미터 타입 오해
CLIP 노드 출력을 clip_l, t5xxl에 연결 → Return type mismatch
**→ clip_l과 t5xxl에 프롬프트 텍스트를 직접 입력할 것.**

### 오류 5: VAEDecode에 MODEL 타입 연결
DiffusionModelLoaderKJ 출력을 VAEDecode.vae에 연결 → 타입 불일치
**→ VAELoader를 별도로 추가해서 VAE 로드 후 연결.**

### 오류 6: Python 타입으로 enum 파라미터 전달
`sage_attention: False` (bool) → ComfyUI API는 문자열만 허용
**→ 문자열 값 사용: 'disabled', 'fp8_e4m3fn', 'default', 'main_device', 'flux' 등.**

### 오류 7: 서버 환경별 노드 차이 미확인
로컬에는 KJ 노드 없음 → 외부 서버 workflow를 로컬에서 실행 시도
**→ 서버 전환 시 /object_info로 노드 존재 여부 먼저 확인. 로컬/외부 별도 workflow 유지.**

### 오류 8: 가짜 API 200 응답 (30분 낭비)
서버가 200 응답하지만 작업 처리 안 함 → 1800초 타임아웃 후에야 에러 발생
**→ 제출 후 2분 안에 GPU 사용량 증가 없으면 즉시 ComfyUI 프로세스 확인. `netstat -ano | grep 8188`으로 PID 확인. comfyui.log 검토.**

### 오류 9: DualCLIPLoader 누락
CLIPLoader('clip_l.safetensors')만 사용 → CLIPTextEncodeFlux에서 t5xxl 토큰화 불가
**→ DualCLIPLoader(clip_l + t5xxl, type='flux')로 통합 로드. .env에 COMFYUI_CLIP2 추가.**

### 오류 10: 모델 로드 진행 상황 미공유
10분 넘게 걸리는데 진행 상황 알 수 없음 → 사용자 혼란
**→ 제출 직후 예상 시간 안내. 30초마다 경과 시간 출력. GPU 사용량으로 단계 파악.**

### 오류 11: 테스트 파일 남발
디버깅 중 임시 파일 21개 생성 → 코드베이스 오염
**→ 디버깅 코드는 기존 파일에 --check 플래그로 통합. 임시 파일 즉시 삭제.**

## Step 3 주요 기술 결정사항 (TTS)

### 캐시 키 설계
- **결정론적 해시 필수**: `hashlib.md5(f'{text}|{voice}|{rate}|{pitch}'.encode()).hexdigest()[:8]`
- Python `hash()` 내장 함수 사용 금지 (PYTHONHASHSEED 의존성으로 캐시 무효화 버그 발생, 실제로 7씬에 16개 파일 누적)
- 파라미터(rate/pitch) 변경 시 자동으로 캐시 미스 발생하여 재생성됨

### 감정별 TTS 파라미터 (EMOTION_VOICE_PARAMS)
- Step 1 NLP의 `emotion` 필드값을 그대로 키로 사용 (테이블 EMOTION_VOICE_PARAMS 참조: step3_audio.py line 47-60)
- pitch 단위: **Hz** (% 단위는 음성별 결과 편차 큼, Hz가 예측 가능)
  - 예: `pitch="-5Hz"`는 절대 오프셋, `pitch="-5%"`는 상대 배율
- `default` 키: 매핑 미정의 감정값에 대한 폴백, 시 낭송 기본 느낌 (`rate=-10%, pitch=-2Hz`)
- 감정별 파라미터:
  - 긍정(기쁨/감탄): rate 약간 빠르거나 정상, pitch 높음
  - 부정(슬픔/피곤함): rate 느림, pitch 낮음
  - 중립(사색적/회상): rate 느림, pitch 정상~낮음

### edge-tts Communicate API 사용
- `edge_tts.Communicate(text, voice, rate, pitch)` — SSML 불필요, 파라미터 직접 전달
- 지원 음성 3종: ko-KR-SunHiNeural(여), ko-KR-InJoonNeural(남), ko-KR-HyunsuMultilingualNeural(남)
- 감정 스타일 API 미지원 (무료 제한, Azure TTS 유료 API는 SSML style 파라미터 지원)
- prosody 파라미터(rate/pitch)로 감정 표현 대체 → 시 낭송 느낌 연출 가능

### Step 3 → Step 4 인터페이스
- `generate_all_audio()` 반환값: `list[str]` (오디오 경로 목록, 실패 씬은 빈 문자열)
- `audio-visual-qa-agent`가 산출한 `scene_durations` (초 단위) → Step 4 MoviePy에 전달
- 전체 오디오 합산: Shorts 60초 제한 (현재 7씬 평균 54초, 안전 범위)

## Step 3 개발 중 오류 및 해결책 (필독: 반복 금지)

### 오류 1: Python hash() 함수로 캐시 키 생성
PYTHONHASHSEED 랜덤 시드 의존 → 실행마다 다른 해시 → 캐시 무효화 → 7씬에 16개 파일 생성
**→ hashlib.md5(text.encode()).hexdigest()[:8] 사용. hash() 내장 함수 절대 금지.**
**확인**: `uv run python step3_audio.py cache/step1/xxx_nlp.json` 연속 2회 실행 시 "캐시 사용:" 로그 확인

### 오류 2: pitch 파라미터 단위 혼용
`pitch="-5%"` 형식은 음성마다 결과 편차가 큼 → 감정 표현 일관성 부족
**→ Hz 단위 사용: `pitch="-5Hz"`. edge-tts는 두 형식 모두 허용하지만 Hz가 예측 가능.**
**예시**: ko-KR-SunHiNeural 기준 `-5Hz` 낮춤 + `rate=-10%` 느림 = 슬픔 표현
