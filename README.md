# AI 쇼츠 자동 생성 파이프라인 (고전시가 → YouTube Shorts) v2

고전 한시·시조의 원문 이미지를 입력받아 **수묵화 스타일 AI 동영상**으로 변환하는 파이프라인 프로젝트.
ElevenLabs TTS 타임스탬프 + AnimateDiff 동적 클립으로 씬별 영상을 자동 생성합니다.

**현재 상태:** Step 0~5 구현 완료 (OCR → NLP → TTS → 스케줄링 → 클립 생성 → 최종 병합)

---

## 파이프라인 구조 (v2, Step 0~5)

```
┌─────────────────────────────────────────────────────────────┐
│ Step 0: OCR (이미지 → 원문 텍스트)                           │
│ 모델: HCX-005 | 캐시: cache/step0/{이미지명}_ocr.txt        │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 1: NLP (번역 + 씬 분할 + 감정 분석)                     │
│ 모델: gpt-4o-mini | 캐시: cache/step1/{hash8}_nlp.json     │
│ 출력: 씬별 {원문, 현대어, 나레이션, 감정, 배경}              │
│ Notion DB (poem_translation_log) 로깅                       │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 2: TTS + 타임스탬프 (ElevenLabs)                       │
│ 출력: MP3 + alignment JSON (단어/문장 타임스탬프)            │
│ 캐시: cache/step2/{hash8}_{idx}_audio.mp3|_alignment.json  │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 3: 프레임 스케줄링 (AnimateDiff BatchPromptSchedule)   │
│ alignment × FPS(10) → 씬별 프레임-프롬프트 매핑 JSON        │
│ 캐시: cache/step3/{hash8}_schedule.json                    │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 4: 영상 클립 (ComfyUI AnimateDiff)                     │
│ SD1.5 + 국풍 LoRA → 씬별 무성 MP4 클립                      │
│ 캐시: cache/step4/{hash8}_{idx}_clip.mp4                   │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 5: 최종 병합 (MoviePy + FFmpeg)                        │
│ 클립 연결 + 타임스탬프 자막 Burn-in + MP3 싱크              │
│ 출력: 1080×1920, 30fps MP4 | 캐시: cache/step5/{hash8}_shorts.mp4 │
└─────────────────────────────────────────────────────────────┘
```

---

## 기술 스택 (v2)

| 계층 | 기술 |
|------|------|
| **프론트엔드** | Streamlit (`app_ui.py`, 포트 8501) |
| **백엔드** | FastAPI (`main_api.py`, 포트 8000) |
| **OCR / NLP** | HCX-005 (OCR), gpt-4o-mini (번역·프롬프트) |
| **음성 생성** | ElevenLabs API (타임스탬프 alignment 포함) |
| **영상 생성** | ComfyUI AnimateDiff (SD 1.5 + 국풍 LoRA) |
| **자막** | MoviePy TextClip (타임스탬프 기반 Burn-in) |
| **최종 합성** | MoviePy + FFmpeg |
| **데이터베이스** | Notion API (poem_translation_log) |
| **패키지 관리** | Python 3.12 (uv) |

---

## 핵심 기술 결정사항

### Step 2: ElevenLabs TTS + Alignment

ElevenLabs alignment JSON 구조:
```json
{
  "words": [{"word": "...", "start": 0.0, "end": 0.3}],
  "sentences": [{"text": "...", "start": 0.0, "end": 2.5}],
  "total_duration": 2.5
}
```

**자막 타이밍 계산 (누적 오프셋):**
```python
global_start = sentence.start + cumulative_time  # 씬별 오프셋 누적 필수
global_end   = sentence.end   + cumulative_time
```

### Step 3: 동적 프레임 스케줄링

- alignment × FPS(10) → 프레임별 프롬프트 할당
- gpt-4o-mini로 수묵화 키워드 생성, 공통 키워드(ink wash, monochrome 등) 자동 삽입

### Step 4: AnimateDiff VRAM 보호

RTX 4070 (8GB) 제약으로 청크 분할 렌더링:
```
총 프레임 = total_duration × FPS(10)
CHUNK_SIZE = 16 (최대 배치)
총 프레임 > 16 → 16프레임씩 분할 후 ffmpeg concat
```

추가 설정:
- `COMFYUI_MAX_WAIT = 1200`초 (SD 1.5 + LoRA는 렌더링 시간 증가)

---

## 설치 및 실행

### 1. 환경 설정

```bash
uv sync
```

`.env` 파일 생성:
```env
# 기존
NCP_CLOVA_API_KEY=xxx
OPENAI_API_KEY=xxx
NOTION_API_KEY=xxx
COMFYUI_HOST=http://127.0.0.1:8188

# v2 신규
ELEVENLABS_API_KEY=xxx
ELEVENLABS_VOICE_ID=onwK4e9ZDvw9KNAVq4mQ
SD15_CHECKPOINT=Realistic Vision v5.1.safetensors
ANIMATEDIFF_MOTION_MODULE=mm_sd_v15_v2.ckpt
LORA_NAME=【国风插画】古风.safetensors
LORA_STRENGTH=0.8
ANIMATEDIFF_FPS=10
ANIMATEDIFF_CHUNK_SIZE=16
SUBTITLE_FONT_PATH=C:/Windows/Fonts/malgun.ttf
```

### 2. ComfyUI 서버 준비 (필수)

```bash
# 별도 터미널에서 실행
cd ../ComfyUI
python main.py

# 필요 모델 확인
ls models/checkpoints/   # SD 1.5 체크포인트
ls models/animatediff_models/  # AnimateDiff 모션 모듈
ls models/loras/         # 국풍 LoRA
```

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
# Step 0: OCR
uv run python step0_ocr.py image.png

# Step 1: NLP
uv run python step1_nlp.py cache/step0/xxx_ocr.txt

# Step 2: ElevenLabs TTS
uv run python step2_tts.py cache/step1/xxx_nlp.json

# Step 3: 프레임 스케줄링
uv run python step3_scheduler.py cache/step1/xxx_nlp.json

# Step 4: AnimateDiff 클립 생성
uv run python step4_clip.py cache/step3/xxx_schedule.json

# Step 5: 최종 병합
uv run python step5_video.py cache/step1/xxx_nlp.json
```

---

## 에이전트 시스템

Claude Code가 아래 상황을 감지하면 해당 서브에이전트를 호출합니다.

| 에이전트 | 역할 | 자동 호출 조건 |
|---------|------|-------------|
| `historical-context-agent` | 고전시가 역사적 배경 조사 | 원문 텍스트 입력 시 |
| `art-director-agent` | AnimateDiff 프롬프트 최적화 | Step 3 스케줄 생성 완료 후 |
| `quality-assurance-agent` | 클립-대본 정합성 검증 | Step 4 클립 생성 완료 후 |
| `audio-visual-qa-agent` | 오디오-타임스탬프 조화 검증 | Step 2 TTS 완료 후 |
| `seo-metadata-agent` | YouTube 메타데이터 생성 | Step 5 최종 영상 완성 후 |

---

## 주요 오류 및 해결책

세부 내용은 `.claude/rules/bug_fixes_and_lessons.md` 참조.

### 오류 1: 자막 타이밍 오프셋 누락 (Section 4)
- 씬별 alignment JSON은 씬 내부 시간 기준 → 최종 병합 시 누적 오프셋 필수

### 오류 2: AnimateDiff VRAM 부족 (Section 5)
- CHUNK_SIZE=16 초과 시 OOM → 청크 분할 후 ffmpeg concat

### 오류 3: v1/v2 캐시 충돌 없음 (Section 6)
- `cache/step2/`: v1(PNG) vs v2(MP3+JSON) — 파일명 패턴 달라 충돌 없음
- v1 task 상태 역직렬화: Pydantic `default=[]|None` 처리

---

## 개발 규칙

세부 규칙은 `.claude/rules/` 디렉터리를 참조하세요.

| 파일 | 내용 |
|------|------|
| `code-style.md` | 들여쓰기, snake_case, 타입힌팅 |
| `naming_conventions.md` | 변수/함수명, FastAPI 라우팅 규칙 |
| `error_handling_logging.md` | 재시도 정책, logging, 상태 관리 |
| `git-rules.md` | 커밋 메시지, 브랜치명, 린트 |
| `Security_Configuration.md` | 하드코딩 금지, .env 사용 |

---

## 문서 및 플랜

- **CLAUDE.md** — Claude Code용 프로젝트 아키텍처 안내
- **.claude/rules/** — 코드 스타일, 보안, 에러 처리, Git 규칙
- **.claude/rules/bug_fixes_and_lessons.md** — v2 설계 교훈 및 버그 수정 이력

---

## 다음 단계

### 현재 완료 (v2)
- [x] Step 0: OCR (HCX-005)
- [x] Step 1: NLP + 씬 분할 (gpt-4o-mini)
- [x] Step 2: ElevenLabs TTS + alignment 타임스탬프
- [x] Step 3: AnimateDiff 프레임 스케줄링
- [x] Step 4: ComfyUI AnimateDiff 클립 생성
- [x] Step 5: MoviePy 최종 병합 + 자막 Burn-in

### Phase 2 (후속): 품질 고도화
- [ ] Step 6: YouTube Shorts 자동 업로드 (YouTube Data API v3)
- [ ] 캐릭터 일관성: AnimateDiff IP-Adapter 적용
- [ ] 수묵화 LoRA 추가 학습 (kohya_ss)
- [ ] 씬 수 확장: 현행 → 15~20개
- [ ] 국립중앙박물관 오픈 이미지 API 연동

---

## 라이선스

MIT License
