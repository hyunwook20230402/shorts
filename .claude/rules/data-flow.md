# nlp.json 필드 → 파이프라인 영향 지도

## nlp.json 구조

```
nlp.json
├── primary_theme          이면 테마 코드 (예: "A")
├── primary_theme_en
├── surface_theme          표면 테마 코드 (예: "B")
├── surface_theme_en
├── dominant_emotion       지배 정서 코드 (예: "E1")
├── dominant_emotion_en
└── modern_script_data[]   씬 배열
    ├── original_text      원문 행 (TTS 음성 텍스트 + 자막 텍스트로 직접 사용)
    ├── emotion            씬별 감정 (한국어 단어)
    ├── main_focus         background / character / object
    ├── scene_description  장면 묘사 (영어 키워드)
    ├── image_prompt       Step 1 이미지 LLM 출력 (최종 ComfyUI 프롬프트)
    └── pose_type          Step 1 이미지 LLM 출력 (image_prompt 구도 가이드, 18종)
```

---

## 필드별 Step 영향 표

| 필드 | 생성 | Step 2 TTS | Step 3 Schedule | Step 4 이미지 | Step 5 BGM | Step 6 영상 |
|------|------|:---:|:---:|:---:|:---:|:---:|
| `original_text` | 분석 LLM | **음성 텍스트** | text 저장 | image_prompt 재료 | **원문 컨텍스트** | **자막 텍스트** |
| `emotion` (씬별) | 분석 LLM | — | — | image_prompt 재료 (조명/색감) | — | — |
| `main_focus` | 분석 LLM | — | — | pose_type 선택 가이드 | — | — |
| `scene_description` | 분석 LLM | — | — | image_prompt 재료 (장면 묘사) | — | — |
| `image_prompt` | 이미지 LLM | — | **스케줄 저장** | **ComfyUI 프롬프트** | — | — |
| `pose_type` | 이미지 LLM | — | **스케줄 저장** | **image_prompt 구도 가이드 (간접)** | — | — |
| `primary_theme` | 테마 LLM | **TTS 속도/피치** | — | — | **BGM 악기/분위기/템포** | **TTS:BGM 볼륨비** |
| `surface_theme` | 테마 LLM | — | — | **LoRA강도/CFG + 색감 키워드** | — | **자막 색상/크기** |
| `dominant_emotion` | 테마 LLM | — | — | emotion_tone → image_prompt 재료 | **정서 힌트 → GPT BGM 프롬프트** | — |
| `theme_reasoning` | 테마 LLM | — | — | — | **테마 판단 근거 → GPT BGM 프롬프트** | — |
| `emotion_reasoning` | 테마 LLM | — | — | — | **정서 판단 근거 → GPT BGM 프롬프트** | — |

---

## Step별 소비 필드 요약

```
Step 2 (TTS)
  original_text        → 음성 텍스트 (직접)
  primary_theme        → TTS 속도/피치 파라미터

Step 3 (Schedule)
  original_text        → 자막 text 필드
  image_prompt         → 스케줄 저장 → Step 4에 전달
  pose_type            → 스케줄 저장 → Step 4에 전달

Step 4 (이미지)
  image_prompt         → ComfyUI Flux 양성 프롬프트
  surface_theme        → 색감 키워드 append (nlp.json 직접 읽음)

Step 5 (BGM)
  primary_theme        → 악기/분위기/템포 힌트 → GPT BGM 프롬프트
  dominant_emotion     → 정서 힌트 → GPT BGM 프롬프트
  theme_reasoning      → 테마 판단 근거 (작품별 해석) → GPT BGM 프롬프트
  emotion_reasoning    → 정서 판단 근거 (감정 해석) → GPT BGM 프롬프트
  scene_description    → 장면 묘사 → GPT BGM 프롬프트
  original_text        → 원문 → GPT BGM 프롬프트

Step 6 (영상)
  original_text        → 자막 burn-in 텍스트 (sentence_schedule.json 경유)
  primary_theme        → TTS:BGM 볼륨비 (nlp.json 직접 읽음)
  surface_theme        → 자막 색상/크기/스타일 (nlp.json 직접 읽음)
```

---

## 이미지 품질에 영향을 주는 6개 필드

이미지는 가장 많은 필드가 수렴하는 지점입니다.

```
original_text     ─┐
emotion (씬별)    ─┤  → [Step 1 이미지 LLM]  → image_prompt ──→ [ComfyUI Flux] → PNG
scene_description ─┤   (pose_type이 구도 가이드)                              ↑
dominant_emotion  ─┘  (emotion_tone 변환 후)                                  │
                                                                              │
surface_theme ───────────────────────────── theme_color append ───────────────┘
```

| 순위 | 필드 | 역할 | 영향 강도 |
|------|------|------|---------|
| 1 | `image_prompt` | ComfyUI Flux 양성 프롬프트 그 자체 | ★★★★★ |
| 2 | `original_text` | image_prompt 핵심 주제 재료 | ★★★★☆ |
| 3 | `pose_type` | image_prompt 생성 시 구도/자세 가이드 (간접) | ★★★☆☆ |
| 4 | `scene_description` | image_prompt 장면 묘사 재료 | ★★★☆☆ |
| 5 | `surface_theme` | 색감 키워드 append | ★★★☆☆ |
| 6 | `dominant_emotion` | emotion_tone → 조명/색감 지침 | ★★☆☆☆ |

---

## 핵심 설계 원칙

- **`image_prompt`는 가장 중요한 중간 산출물**: `original_text`, `emotion`, `scene_description`, `dominant_emotion` 4개가 합쳐져 만들어지는 압축 결과물. 여기서 이미지 품질이 결정됨.
- **테마 이원화 역할 분리**: `surface_theme`은 이미지·자막(시각), `primary_theme`은 TTS·BGM·볼륨(청각)에 각각 특화.
- **`original_text`는 가장 직접적인 필드**: TTS 음성 텍스트와 자막 텍스트 둘 다 이 값을 그대로 사용. 원문이 영상 전반에 직결. 1씬 = 1행 = 1문장 불변 조건 자동 보장.
- **`dominant_emotion`은 청각(BGM)과 시각(이미지 색감) 양쪽에 간접 영향**.
