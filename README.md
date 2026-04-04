# AI 쇼츠 자동 생성 파이프라인 (고전시가 → YouTube Shorts) v2

고전 한시·시조의 원문 이미지를 입력받아 **수묵화 스타일 AI 슬라이드쇼 동영상**으로 변환하는 파이프라인 프로젝트.
edge-tts 음성 + ComfyUI SD 1.5 정지이미지 + NanumSquare 자막 + Stable Audio BGM으로 씬별 영상을 자동 생성합니다.

**현재 상태:** Step 0~6 구현 완료 (OCR → NLP → TTS → 스케줄링 → 이미지 생성 → BGM → 최종 병합)

---

## 시스템 요구사항

| 항목 | 요구 |
|------|------|
| **OS** | Windows 11 (Windows 10 가능) |
| **Python** | 3.12+ |
| **GPU** | NVIDIA RTX 4070 (8GB VRAM) 이상 권장 |
| **패키지 매니저** | [uv](https://docs.astral.sh/uv/) 설치 필요 |
| **ComfyUI** | 별도 설치 필요 (SD 1.5 + 국풍 LoRA) |
| **FFmpeg** | 시스템 PATH에 등록 필요 |
| **폰트** | 나눔스퀘어 ExtraBold (`%LOCALAPPDATA%/Microsoft/Windows/Fonts/NanumSquare.ttf`) |

---

## 파이프라인 구조 (v2, Step 0~6)

```
┌─────────────────────────────────────────────────────────────┐
│ Step 0: OCR (이미지 → 원문 텍스트)                           │
│ 모델: HCX-005 | 캐시: {poem_dir}/step0/ocr.txt             │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 1: NLP (번역 + 씬 분할 + 이중 테마/정서 분류)           │
│ 모델: HCX-005 (번역+프롬프트), gpt-4o-mini (BGM)            │
│ 캐시: {poem_dir}/step1/nlp.json                             │
│ 출력: primary/surface_theme, dominant_emotion,               │
│       씬별 {원문, 현대어, 나레이션, 감정, 배경, image_prompt} │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 2: TTS + 타임스탬프 (edge-tts)                         │
│ 출력: 문장별 MP3 + alignment JSON (추정 타임스탬프)          │
│ 캐시: {poem_dir}/step2/scene{NN}_sent{MM}_audio.mp3        │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 3: 문장 스케줄링                                       │
│ 문장 단위 duration/image_prompt/audio_path 매핑 JSON        │
│ 캐시: {poem_dir}/step3/sentence_schedule.json               │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 4: 정지이미지 (ComfyUI SD 1.5)                         │
│ SD 1.5 + 국풍 LoRA + IP-Adapter → 문장별 PNG 이미지         │
│ 캐시: {poem_dir}/step4/scene{NN}_sent{MM}_still.png        │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 5: BGM 생성 (Stable Audio)                             │
│ 테마별 악기/분위기 + 지배적 정서 → LLM BGM 프롬프트 → WAV   │
│ 캐시: {poem_dir}/step5/bgm.wav                              │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 6: 최종 병합 (MoviePy + FFmpeg)                        │
│ 이미지+오디오 슬라이드쇼 + NanumSquare 자막 + BGM 믹싱      │
│ 출력: 1080×1920, 30fps MP4                                  │
│ 캐시: {poem_dir}/step6/shorts.mp4                           │
└─────────────────────────────────────────────────────────────┘
```

---

## 기술 스택 (v2)

| 계층 | 기술 |
|------|------|
| **프론트엔드** | Streamlit (`app_ui.py`, 포트 8501) |
| **백엔드** | FastAPI (`main_api.py`, 포트 8000) |
| **OCR / NLP** | HCX-005 (OCR + 번역 + 테마/정서 분류 + 이미지 프롬프트) |
| **BGM 프롬프트** | gpt-4o-mini (테마/정서 기반 Stable Audio 프롬프트) |
| **음성 생성** | edge-tts (한국어, 무료 — `ko-KR-SunHiNeural`) |
| **이미지 생성** | ComfyUI SD 1.5 정지이미지 (국풍 LoRA + IP-Adapter) |
| **BGM 생성** | Stable Audio (`stabilityai/stable-audio-open-1.0`) |
| **자막** | PIL Image 기반 (NanumSquare EB, 흰색+검은 외곽선, 65% 위치) |
| **최종 합성** | MoviePy + FFmpeg (이미지+오디오+자막+BGM 슬라이드쇼) |
| **데이터베이스** | Notion API (poem_translation_log) |
| **패키지 관리** | Python 3.12 (uv) |

---

## 이중 테마 + 정서 시스템

Step 1에서 고전시가의 테마와 정서를 자동 분류하여 전체 파이프라인에 반영합니다.

**13개 테마 (A~M):** 강호자연, 충의지사, 연군지정, 이별상사, 세월무상, 풍류지락, 유배한탄, 전쟁비가, 교훈풍자, 민중생활, 탈속은둔, 여성규방, 건국송축

**7개 정서 (E1~E7):** 비장, 달관, 그리움, 흥취, 한탄, 경외, 풍자

**적용 범위:**
- `primary_theme` → BGM 악기/분위기, 전체 톤
- `surface_theme` → 이미지 프롬프트 배경/소재
- `dominant_emotion` → BGM 정서 힌트, 이미지 분위기

설정 파일: `notebook/theme_config.py` (단일 소스)

---

## 캐시 디렉토리 구조 (이원화)

CLI 실행과 UI 실행의 캐시가 분리되어 있습니다.

```
notebook/cache/                 # CLI 실행 캐시 (cd notebook && python step*.py)
├── poem_01/                    # 시 1 캐시
│   ├── step0/ocr.txt
│   ├── step1/nlp.json
│   ├── step2/scene00_sent00_audio.mp3
│   ├── step3/sentence_schedule.json
│   ├── step4/scene00_sent00_still.png
│   ├── step5/bgm.wav
│   └── step6/shorts.mp4
├── poem_02/                    # 시 2 캐시 (동일 구조)
└── reference/                  # IP-Adapter 참조 이미지

upload_cache/                   # UI 업로드 캐시 (FastAPI + Streamlit)
├── task_states.json            # 전체 task 상태 관리 (PersistentTaskDict)
├── poem_registry.json          # poem_id 레지스트리
├── uploads/                    # 업로드 원본 이미지
│   └── {task_id}_{filename}
└── poem_01/                    # UI에서 생성된 poem 캐시 (동일 구조)
```

---

## 설치 및 실행

### 1. 환경 설정

```bash
uv sync
```

`notebook/.env` 파일 생성:
```env
# API 키
NCP_CLOVA_API_KEY=xxx        # HCX-005 OCR/번역
OPENAI_API_KEY=xxx            # gpt-4o-mini BGM 프롬프트
NOTION_API_KEY=xxx            # Notion DB 연동 (선택)

# TTS
EDGE_TTS_VOICE=ko-KR-SunHiNeural  # edge-tts 음성 (기본값)

# ComfyUI 이미지 생성
COMFYUI_HOST=http://127.0.0.1:8188
SD15_CHECKPOINT=Realistic_Vision_V5.1.safetensors
LORA_NAME=E38090E59BBDE9A38EE68F92E794BBE38091E58FABE7.G2A0.safetensors
LORA_STRENGTH=0.8
STILL_IMAGE_STEPS=30
STILL_IMAGE_CFG=7.5
COMFYUI_OUTPUT_DIR=ComfyUI/output
COMFYUI_INPUT_DIR=ComfyUI/input
COMFYUI_MAX_WAIT=1200

# IP-Adapter (캐릭터 일관성, 선택)
IPADAPTER_MODEL=ip-adapter_sd15.bin
IPADAPTER_WEIGHT=0.5
CLIP_VISION_MODEL=clip_vision_h14.safetensors
REFERENCE_IMAGE_PATH=cache/reference/character.png

# Stable Audio BGM
STABLE_AUDIO_MODEL=stabilityai/stable-audio-open-1.0

# 자막 (나눔스퀘어 ExtraBold 필요)
SUBTITLE_FONT_PATH=%LOCALAPPDATA%/Microsoft/Windows/Fonts/NanumSquare.ttf
```

### 2. ComfyUI 서버 준비 (필수)

```bash
# 별도 터미널에서 실행
cd ../ComfyUI
python main.py

# 필요 모델 확인
ls models/checkpoints/   # SD 1.5 체크포인트
ls models/loras/         # 국풍 LoRA
```

**IP-Adapter 사용 시 추가 모델:**
- `models/ipadapter/ip-adapter_sd15.bin`
- `models/clip_vision/clip_vision_h14.safetensors`
- 참조 이미지: `cache/reference/character.png`

### 3. 서버 실행

```bash
# FastAPI 백엔드 + Streamlit UI 동시 실행
start_server.bat

# 또는 개별 실행
uv run uvicorn main_api:app --port 8000
uv run streamlit run app_ui.py
```

### 4. 개별 Step CLI 실행

```bash
cd notebook

# Step 0: OCR
uv run python step0_ocr.py image.png

# Step 1: NLP (이중 테마 + 정서 분류 포함)
uv run python step1_nlp.py cache/{poem_id}

# Step 2: edge-tts TTS
uv run python step2_tts.py cache/{poem_id}

# Step 3: 문장 스케줄링
uv run python step3_scheduler.py cache/{poem_id}

# Step 4: ComfyUI 정지이미지 생성
uv run python step4_image.py cache/{poem_id}

# Step 5: Stable Audio BGM 생성
uv run python step5_bgm.py cache/{poem_id}

# Step 6: 최종 병합 (이미지+오디오+자막+BGM)
uv run python step6_video.py cache/{poem_id}
```

---

## 에이전트 시스템

Claude Code가 아래 상황을 감지하면 해당 서브에이전트를 호출합니다.

| 에이전트 | 역할 | 자동 호출 조건 |
|---------|------|-------------|
| `historical-context-agent` | 고전시가 역사적 배경 조사 | 원문 텍스트 입력 시 |
| `audio-visual-qa-agent` | 오디오-타임스탬프 타이밍 검증 | Step 2 TTS 완료 후 |
| `art-director-agent` | 정지이미지 프롬프트 최적화 | Step 3 스케줄 생성 완료 후 |
| `quality-assurance-agent` | 이미지-대본 정합성 검증 | Step 4 이미지 생성 완료 후 |
| `bgm-verification-agent` | BGM 품질/길이/테마 검증 | Step 5 BGM 생성 완료 후 |
| `video-verification-agent` | 영상 스펙/오디오/자막 검증 | Step 6 최종 영상 완성 후 |
| `seo-metadata-agent` | YouTube 메타데이터 생성 | Step 6 최종 영상 완성 후 |
| `pipeline-debug-agent` | 로그 분석 + 근본 원인 진단 | Step 실행 에러 발생 시 |

---

## 주요 오류 및 해결책

세부 내용은 `.claude/rules/bug_fixes_and_lessons.md` 참조.

### 오류 1: 자막 타이밍 오프셋 누락 (Section 4)
- 씬별 alignment JSON은 씬 내부 시간 기준 → 최종 병합 시 누적 오프셋 필수

### 오류 2: GPU VRAM 부족 (Section 5)
- STILL_IMAGE_STEPS 줄이기 또는 다른 GPU 프로세스 종료

### 오류 3: BGM 볼륨 조절 (MoviePy)
- `multiply_volume()` 아닌 `volumex()` 사용 필수
- `subclipped()` 아닌 `subclip()` 사용 필수

---

## 개발 규칙

세부 규칙은 `.claude/rules/` 디렉터리를 참조하세요.

| 파일 | 내용 |
|------|------|
| `code-style.md` | 들여쓰기, snake_case, 타입힌팅, get_cache_path() 의무화 |
| `naming_conventions.md` | 변수/함수명, FastAPI 라우팅 규칙 |
| `error_handling_logging.md` | 재시도 정책, logging, 상태 관리 |
| `git-rules.md` | 커밋 메시지, 브랜치명, `ruff check .` |
| `Security_Configuration.md` | 하드코딩 금지, .env 사용 |
| `cache-management.md` | 캐시 경로 규칙, poem_dir 기반 |
| `streamlit-patterns.md` | 폴링 패턴, @st.cache_data 금지 |
| `cache-field-checklist.md` | JSON 필드 추가 시 E2E 검증 필수 |

---

## 문서 및 플랜

- **CLAUDE.md** — Claude Code용 프로젝트 아키텍처 안내
- **.claude/rules/** — 코드 스타일, 보안, 에러 처리, Git, 캐시 규칙
- **.claude/skills/** — 자동 워크플로우 (상태 확인, 캐시 검증, ComfyUI 헬스체크 등)
- **.claude/agents/** — 서브에이전트 9개 (아트 디렉터, QA, BGM 검증, 영상 검증, 디버그 등)
- **.claude/rules/bug_fixes_and_lessons.md** — v2 설계 교훈 및 버그 수정 이력

---

## 다음 단계

### 현재 완료 (v2)
- [x] Step 0: OCR (HCX-005)
- [x] Step 1: NLP + 씬 분할 + 이중 테마/정서 분류 (HCX-005)
- [x] Step 2: edge-tts TTS + alignment 타임스탬프
- [x] Step 3: 문장 단위 스케줄링
- [x] Step 4: ComfyUI SD 1.5 정지이미지 생성
- [x] Step 5: Stable Audio BGM 생성 (테마/정서 기반)
- [x] Step 6: MoviePy 최종 병합 + NanumSquare 자막 + BGM 믹싱

### Phase 2 (후속): 품질 고도화
- [ ] Flux.1-dev FP8 + GuoFeng5 LoRA 이미지 모델 전환 (Step 4)
- [ ] YouTube Shorts 자동 업로드 (YouTube Data API v3)
- [ ] 캐릭터 일관성: IP-Adapter 참조 이미지 고도화
- [ ] 수묵화 LoRA 추가 학습 (kohya_ss)
- [ ] 씬 수 확장: 현행 → 15~20개
- [ ] 국립중앙박물관 오픈 이미지 API 연동

---

## 라이선스

MIT License
