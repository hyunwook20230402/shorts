# 캐시 관리 규칙

## 캐시 경로 구조 (이원화)

캐시는 실행 환경에 따라 두 곳으로 분리됩니다.

| 환경 | 캐시 루트 | 설명 |
|------|----------|------|
| **CLI** (`cd notebook && python step*.py`) | `notebook/cache/{poem_id}/` | 파이썬 직접 실행 |
| **UI** (FastAPI + Streamlit) | `upload_cache/{poem_id}/` | 웹 UI 업로드/파이프라인 |

두 환경 모두 poem_dir 하위에 동일한 파일 구조를 사용합니다:

```
{poem_dir}/
├── step0/
│   └── ocr.txt
├── step1/
│   ├── nlp.json                 ← primary/surface_theme, dominant_emotion 필드 포함
│   └── context.txt
├── step2/
│   ├── scene{NN}_sent{MM}_audio.mp3
│   └── scene{NN}_sent{MM}_alignment.json
├── step3/
│   └── sentence_schedule.json
├── step4/
│   └── scene{NN}_sent{MM}_still.png
├── step5/
│   └── bgm.wav                  ← Stable Audio 생성 BGM (테마/정서 기반)
└── step6/
    └── shorts.mp4               ← 최종 영상 (NanumSquare 자막 + BGM 믹싱)
```

**UI 전용 파일:**
- `upload_cache/task_states.json` — PersistentTaskDict 상태 파일
- `upload_cache/poem_registry.json` — poem_id 레지스트리
- `upload_cache/uploads/{task_id}_{filename}` — 업로드 원본 이미지

## 필수 규칙

- **get_cache_path() 의무화:** 각 Step 모듈(`stepN_*.py`)에서만 캐시 경로를 생성하는 함수를 정의합니다. `pipeline_runner.py`는 Step 모듈의 함수를 import하여 사용합니다. 직접 경로를 조합하면 캐시 키 불일치 버그가 발생합니다.
- **poem_dir 기반:** 모든 Step 함수는 `poem_dir` 인자를 받아 사용합니다. CLI에서는 `cache/poem_01`, UI에서는 `upload_cache/poem_01`이 전달됩니다.
- **task_states.json 직접 수정 금지:** 반드시 `PersistentTaskDict` API(`api/pipeline_runner.py`)를 통해 접근합니다.
- **캐시 무효화:** Step N의 코드를 수정한 경우, Step N 이하(N~6)의 캐시를 `use_cache=false`로 재실행하여 갱신합니다.
- **`.gitignore` 확인:** `cache/`와 `upload_cache/` 디렉토리 모두 `.gitignore`에 포함되어야 합니다.
