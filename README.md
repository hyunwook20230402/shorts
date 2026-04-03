# AI 쇼츠 자동 생성 파이프라인 (고전시가 → YouTube Shorts) v2

고전 한시·시조의 원문 이미지를 입력받아 **수묵화 스타일 AI 슬라이드쇼 동영상**으로 변환하는 파이프라인 프로젝트.
edge-tts 음성 + SD 1.5 정지이미지 + PIL 자막으로 씬별 영상을 자동 생성합니다.

**현재 상태:** Step 0~5 구현 완료 (OCR → NLP → TTS → 스케줄링 → 이미지 생성 → 최종 병합)

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
| **폰트** | 맑은 고딕 (Windows 기본 포함: `C:/Windows/Fonts/malgun.ttf`) |

---

## 파이프라인 구조 (v2, Step 0~5)

```
┌─────────────────────────────────────────────────────────────┐
│ Step 0: OCR (이미지 → 원문 텍스트)                           │
│ 모델: HCX-005 | 캐시: cache/{poem_id}/step0_ocr.txt        │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 1: NLP (번역 + 씬 분할 + 이미지 프롬프트)               │
│ 모델: HCX-005 + gpt-4o-mini                                │
│ 캐시: cache/{poem_id}/step1_nlp.json                       │
│ 출력: 씬별 {원문, 현대어, 나레이션, 감정, 배경, image_prompt}│
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 2: TTS + 타임스탬프 (edge-tts)                         │
│ 출력: 문장별 MP3 + alignment JSON (추정 타임스탬프)          │
│ 캐시: cache/{poem_id}/step2_scene{NN}_sent{MM}_audio.mp3   │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 3: 문장 스케줄링                                       │
│ 문장 단위 duration/image_prompt/audio_path 매핑 JSON        │
│ 캐시: cache/{poem_id}/step3_sentence_schedule.json          │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 4: 정지이미지 (ComfyUI SD 1.5)                         │
│ SD1.5 + 국풍 LoRA + IP-Adapter → 문장별 PNG 이미지          │
│ 캐시: cache/{poem_id}/step4_scene{NN}_sent{MM}_still.png   │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 5: 최종 병합 (MoviePy + FFmpeg)                        │
│ 이미지+오디오 슬라이드쇼 + PIL 자막 Burn-in                  │
│ 출력: 1080×1920, 30fps MP4                                  │
│ 캐시: cache/{poem_id}/step5_shorts.mp4                     │
└─────────────────────────────────────────────────────────────┘
```

---

## 기술 스택 (v2)

| 계층 | 기술 |
|------|------|
| **프론트엔드** | Streamlit (`app_ui.py`, 포트 8501) |
| **백엔드** | FastAPI (`main_api.py`, 포트 8000) |
| **OCR / NLP** | HCX-005 (OCR + 번역), gpt-4o-mini (이미지 프롬프트) |
| **음성 생성** | edge-tts (한국어, 무료 — `ko-KR-SunHiNeural`) |
| **이미지 생성** | ComfyUI SD 1.5 정지이미지 (국풍 LoRA + IP-Adapter) |
| **자막** | PIL Image 기반 자막 이미지 → MoviePy ImageClip Burn-in |
| **최종 합성** | MoviePy + FFmpeg (이미지+오디오 슬라이드쇼) |
| **데이터베이스** | Notion API (poem_translation_log) |
| **패키지 관리** | Python 3.12 (uv) |

---

## 캐시 디렉토리 구조 (이원화)

CLI 실행과 UI 실행의 캐시가 분리되어 있습니다.

```
notebook/cache/                 # CLI 실행 캐시 (cd notebook && python step*.py)
├── poem_01/                    # 시 1 캐시
│   ├── step0_ocr.txt
│   ├── step1_nlp.json
│   ├── step2_scene00_sent00_audio.mp3
│   ├── step3_sentence_schedule.json
│   ├── step4_scene00_sent00_still.png
│   └── step5_shorts.mp4
├── poem_02/                    # 시 2 캐시 (동일 구조)
└── reference/                  # IP-Adapter 참조 이미지

upload_cache/                   # UI 업로드 캐시 (FastAPI + Streamlit)
├── task_states.json            # 전체 task 상태 관리 (PersistentTaskDict)
├── poem_registry.json          # poem_id 레지스트리
├── uploads/                    # 업로드 원본 이미지
│   └── {task_id}_{filename}
├── poem_01/                    # UI에서 생성된 poem 캐시 (동일 구조)
│   ├── original.png
│   ├── step0_ocr.txt ~ step5_shorts.mp4
│   └── ...
└── poem_02/
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
OPENAI_API_KEY=xxx            # gpt-4o-mini 이미지 프롬프트
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

# 자막
SUBTITLE_FONT_PATH=C:/Windows/Fonts/malgun.ttf
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

# Step 1: NLP
uv run python step1_nlp.py cache/{poem_id}/step0_ocr.txt

# Step 2: edge-tts TTS
uv run python step2_tts.py cache/{poem_id}/step1_nlp.json

# Step 3: 문장 스케줄링
uv run python step3_scheduler.py cache/{poem_id}/step1_nlp.json

# Step 4: ComfyUI 정지이미지 생성
uv run python step4_image.py cache/{poem_id}/step3_sentence_schedule.json

# Step 5: 최종 병합
uv run python step5_video.py cache/{poem_id}/step1_nlp.json
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
| `seo-metadata-agent` | YouTube 메타데이터 생성 | Step 5 최종 영상 완성 후 |
| `pipeline-debug-agent` | 로그 분석 + 근본 원인 진단 | Step 실행 에러 발생 시 |

---

## 주요 오류 및 해결책

세부 내용은 `.claude/rules/bug_fixes_and_lessons.md` 참조.

### 오류 1: 자막 타이밍 오프셋 누락 (Section 4)
- 씬별 alignment JSON은 씬 내부 시간 기준 → 최종 병합 시 누적 오프셋 필수

### 오류 2: GPU VRAM 부족 (Section 5)
- STILL_IMAGE_STEPS 줄이기 또는 다른 GPU 프로세스 종료

### 오류 3: v1/v2 캐시 충돌 없음 (Section 6)
- `cache/step2/`: v1(PNG) vs v2(MP3+JSON) — 파일명 패턴 달라 충돌 없음
- v1 task 상태 역직렬화: Pydantic `default=[]|None` 처리

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

---

## 문서 및 플랜

- **CLAUDE.md** — Claude Code용 프로젝트 아키텍처 안내
- **.claude/rules/** — 코드 스타일, 보안, 에러 처리, Git, 캐시 규칙
- **.claude/skills/** — 자동 워크플로우 (상태 확인, 캐시 검증, ComfyUI 헬스체크 등)
- **.claude/agents/** — 서브에이전트 8개 (아트 디렉터, QA, 디버그 등)
- **.claude/rules/bug_fixes_and_lessons.md** — v2 설계 교훈 및 버그 수정 이력

---

## 다음 단계

### 현재 완료 (v2)
- [x] Step 0: OCR (HCX-005)
- [x] Step 1: NLP + 씬 분할 (HCX-005 + gpt-4o-mini)
- [x] Step 2: edge-tts TTS + alignment 타임스탬프
- [x] Step 3: 문장 단위 스케줄링
- [x] Step 4: ComfyUI SD 1.5 정지이미지 생성
- [x] Step 5: MoviePy 최종 병합 + PIL 자막 Burn-in

### Phase 2 (후속): 품질 고도화
- [ ] Step 6: YouTube Shorts 자동 업로드 (YouTube Data API v3)
- [ ] 캐릭터 일관성: IP-Adapter 참조 이미지 고도화
- [ ] 수묵화 LoRA 추가 학습 (kohya_ss)
- [ ] 씬 수 확장: 현행 → 15~20개
- [ ] 국립중앙박물관 오픈 이미지 API 연동

---

## 라이선스

MIT License
