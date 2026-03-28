# AI 쇼츠 자동 생성 파이프라인 (고전시가 → YouTube Shorts)

고전 한시·시조의 원문 이미지를 입력받아 웹툰 스타일 AI 영상으로 변환하여 YouTube Shorts로 자동 업로드하는 파이프라인 프로젝트.

**현재 상태:** Step 0~4 완료 (OCR → NLP → 이미지 생성 → 오디오 생성 → 자막 생성), Step 5~6 구축 예정

---

## 파이프라인 구조 (Step 0~6)

```
┌─────────────────────────────────────────────────────────┐
│ Step 0: OCR (이미지 → 원문 텍스트)                      │
│ 입력: PNG/JPG | 출력: extracted_raw_text               │
└────────────────────┬────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────┐
│ Step 1: NLP (번역 + 씬 분할 + 감정 분석)                 │
│ 입력: 원문 | 출력: modern_script_data (JSON)            │
│ 결과: Notion DB (poem_translation_log) 로깅            │
└────────────────────┬────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────┐
│ Step 2: Vision (ComfyUI → 웹툰 이미지 생성)             │
│ 입력: image_prompts | 출력: PNG (512×912, 9:16)        │
└────────────────────┬────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────┐
│ Step 3: Audio (Edge-TTS → 감정 기반 음성 생성)          │
│ 입력: narration + emotion | 출력: MP3 (감정 파라미터)   │
│ 캐시: cache/step3/ (7개 MP3 파일)                      │
└────────────────────┬────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────┐
│ Step 4: Subtitle (오디오 길이 기반 SRT 자막)            │
│ 입력: MP3 + narration | 출력: SRT (자막 + 타이밍)       │
│ 캐시: cache/step4/ (SRT + audio-visual-qa 보고서)     │
└────────────────────┬────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────┐
│ Step 5: Video (MoviePy → 최종 영상 합성)               │
│ 입력: PNG + MP3 + SRT | 출력: MP4 (1080×1920, 9:16)    │
│ 제약: 60초 이내 (Shorts 규격)                          │
└────────────────────┬────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────┐
│ Step 6: Publish (YouTube Shorts 업로드)                │
│ 입력: MP4 + 제목/설명/해시태그 | 출력: URL             │
└─────────────────────────────────────────────────────────┘
```

---

## 기술 스택

| 계층 | 기술 |
|------|------|
| **LLM/Vision** | GPT-4o-mini (OCR, 번역), Claude Vision (QA) |
| **이미지 생성** | ComfyUI API (FLUX.1 Dev fp8, 웹툰 LoRA) |
| **음성 생성** | Edge-TTS (감정 기반 prosody: rate/pitch) |
| **영상 합성** | MoviePy (자막 오버레이, FFmpeg) |
| **데이터베이스** | Notion API (poem_translation_log, task_status_log) |
| **웹 프레임워크** | Streamlit (UI), FastAPI (API) |
| **패키지 관리** | Python 3.12 (uv) |
| **배포** | YouTube Data API v3 |

---

## 핵심 기술 결정사항

### Step 2: ComfyUI 이미지 생성

**검증된 노드 구조:**
- **DualCLIPLoader**: clip_l + t5xxl 동시 로드 (FLUX.1 필수)
- **EmptyFlux2LatentImage**: 해상도 2배 입력 (ComfyUI 50% 축소 보정)
  - 입력: 1024×1824 → 출력: 512×912
- **KSampler**: steps=20, cfg=3.5, sampler=euler, scheduler=karras

**성능 (로컬):**
- 모델 첫 로드: 5~7분
- 씬당 생성: 30~45초
- 폴링 대기: 1800초 max

### Step 3: Edge-TTS 감정 기반 음성

**감정별 파라미터 매핑 (EMOTION_VOICE_PARAMS):**

| 감정 | rate | pitch | 예시 |
|------|------|-------|------|
| 기쁨 | +5% | +8Hz | 밝은 톤 |
| 슬픔 | -25% | -8Hz | 차분한 톤 |
| 피곤함 | -20% | -8Hz | 무거운 톤 |
| 감탄 | -5% | +5Hz | 놀람 표현 |
| **default** | **-10%** | **-2Hz** | 시 낭송 기본 |

**중요:** Pitch 단위는 Hz (절대값) — % 단위는 음성별 편차가 큼.

### Step 4: SRT 자막 생성

**캐시 구조:**
```
cache/
├── step3/          ← MP3 파일만 (7개)
├── step4/          ← SRT + audio-visual-qa 리포트
└── step5/          ← (추후) 최종 영상
```

**자막 텍스트:** Step 1 `narration` 필드 사용 (TTS 음성과 정확히 일치)

**타이밍 계산:** `mutagen` 라이브러리로 MP3 길이 측정 → 자동 타임코드 생성

---

## 설치 및 실행

### 1. 환경 설정

```bash
# uv로 의존성 설치
uv sync

# .env 파일 생성 (필수 항목)
cat > .env << EOF
NOTION_API_KEY=xxx
NOTION_POEM_LOG_DB_ID=xxx
NOTION_TASK_STATUS_DB_ID=xxx
OPENAI_API_KEY=xxx
YOUTUBE_API_KEY=xxx
TTS_VOICE=ko-KR-SunHiNeural
COMFYUI_HOST=http://127.0.0.1:8188
EOF
```

### 2. ComfyUI 로컬 서버 준비 (필수)

```bash
# ComfyUI 실행 (별도 터미널)
cd ../ComfyUI
python main.py

# 모델 확인
ls models/diffusion_models/flux1-dev-fp8.safetensors
ls models/vae/ae.safetensors
ls models/clip/clip_l.safetensors
ls models/clip/t5xxl_fp8_e4m3fn.safetensors
```

### 3. 파이프라인 실행

**전체 파이프라인:**
```bash
uv run python main.py
```

**개별 Step 실행:**

```bash
# Step 0: OCR
uv run python step0_ocr.py image.png

# Step 1: NLP + 번역 (Notion DB 로깅)
uv run python step1_nlp.py cache/step0/extracted_raw_text.txt

# Step 2: ComfyUI 이미지 생성
uv run python step2_vision.py cache/step1/xxx_nlp.json

# Step 3: TTS 음성 생성 (감정 파라미터 적용)
uv run python step3_audio.py cache/step1/xxx_nlp.json

# Step 4: SRT 자막 생성
uv run python step4_subtitle.py cache/step1/xxx_nlp.json --audio-dir cache/step3
```

---

## 에이전트 시스템

프로젝트는 7개 전문 에이전트로 구성:

| 에이전트 | 역할 | 자동 호출 조건 |
|---------|------|-------------|
| `historical-context-agent` | 고전시가 역사적 배경 조사 | Step 1 NLP 전, 원문 입력 시 |
| `art-director-agent` | ComfyUI 프롬프트 최적화 | Step 2 이미지 프롬프트 생성 시 |
| `quality-assurance-agent` | 대본-이미지 정합성 검증 | Step 2 이미지 생성 완료 후 |
| `audio-visual-qa-agent` | 음성-이미지 조화 검증 | Step 3 오디오 생성 완료 후 |
| `seo-metadata-agent` | YouTube 메타데이터 생성 | Step 5 영상 완성 후 |
| `prd-writer-shorts` | PRD 작성/업데이트 | 새 기능 기획 시 |
| `prd-validator` | PRD 완성도 검증 | PRD 작성 완료 시 |

---

## 주요 오류 및 해결책

### 오류 1: 캐시 해시 중복 (PYTHONHASHSEED)
- **원인:** Python `hash()` 함수 사용 (매 실행마다 다른 값)
- **증상:** 7씬에 16개 MP3 파일 생성
- **해결:** `hashlib.md5(key.encode()).hexdigest()[:8]` 사용
- **확인:** `uv run python step3_audio.py` 2회 연속 실행 시 "캐시 사용:" 로그 확인

### 오류 2: 음성 단조로움 (감정 미반영)
- **원인:** TTS 파라미터 동일 (감정별 매핑 부재)
- **해결:** EMOTION_VOICE_PARAMS 딕셔너리로 감정→prosody 매핑
- **확인:** `--no-cache` 플래그로 재생성, 로그에 `rate=...% pitch=...Hz` 출력 확인

### 오류 3: 자막 타이밍 오류
- **원인:** MP3 파일명 알파벳 정렬 (씬 순서 무시)
- **해결:** 파일명 패턴 `{hash}_{idx:02d}_audio.mp3`에서 idx 추출, 정수 정렬
- **확인:** SRT 타임코드가 오디오 길이와 정확히 일치하는지 확인

---

## 개발 규칙

### 코드 스타일
- **들여쓰기:** 스페이스 2칸
- **변수명:** `snake_case` (Python), `camelCase` (JS/TS)
- **함수명:** 동사로 시작 (`extract_text`, `generate_audio`)
- **타입힌트:** Python 3.10+ 필수
- **주석:** 한국어

### Git 규칙
- **커밋 메시지:** 한국어
- **브랜치명:** `feature/기능명`, `fix/버그명`
- **린트:** 커밋 전 `ruff check` 필수

### API 호출
- **재시도:** 모든 외부 API에 3회 재시도 + 지수 백오프
- **캐싱:** 각 Step의 중간 결과물은 `cache/` 디렉터리에 저장
- **로깅:** `print()` 금지, `logging` 모듈 사용

---

## 문서 및 플랜

- **CLAUDE.md** — 프로젝트 전체 아키텍처, 기술 결정, 오류 교훈
- **.claude/agents/** — 7개 에이전트 시스템 프롬프트
- **.claude/plans/** — Step 별 로드맵 및 QA 계획
- **.claude/rules/** — 코드 스타일, 보안, 에러 처리 규칙

---

## 다음 단계

### Phase 1 (현재): 기초 파이프라인 완성
- [x] Step 0~1: OCR + NLP
- [x] Step 2: ComfyUI 이미지 생성 (웹툰 스타일)
- [x] Step 3: Edge-TTS 감정 기반 음성
- [x] Step 4: SRT 자막 생성
- [ ] Step 5: MoviePy 영상 합성
- [ ] Step 6: YouTube 자동 업로드

### Phase 2 (후속): 웹툰 고품질화
- 국립중앙박물관 오픈 이미지 API로 조선시대 풍속화 수집
- FLUX.1 + LoRA 학습 (kohya_ss, SimpleTuner)
- 캐릭터 Dreambooth LoRA (외모 일관성)
- IPAdapter로 씬 간 연결성 개선
- 컷 수 확장: 7개 → 20~30개

자세한 로드맵: `.claude/plans/step2-quality-upgrade-roadmap.md`

---

## 라이선스

MIT License

## 연락처

개발 진행 상황 및 이슈: GitHub 프로젝트 참고
