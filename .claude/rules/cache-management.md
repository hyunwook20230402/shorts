# 캐시 관리 규칙

## 캐시 경로 구조

모든 캐시는 `notebook/cache/{poem_id}/` 하위에 poem_dir 기반으로 저장됩니다.

```
cache/{poem_id}/
├── step0_ocr.txt
├── step1_nlp.json
├── step1_context.txt
├── step2_scene{NN}_sent{MM}_audio.mp3
├── step2_scene{NN}_sent{MM}_alignment.json
├── step3_sentence_schedule.json
├── step4_scene{NN}_sent{MM}_still.png
└── step5_shorts.mp4
```

## 필수 규칙

- **get_cache_path() 의무화:** 각 Step 모듈(`stepN_*.py`)에서만 캐시 경로를 생성하는 함수를 정의합니다. `pipeline_runner.py`는 Step 모듈의 함수를 import하여 사용합니다. 직접 경로를 조합하면 캐시 키 불일치 버그가 발생합니다.
- **poem_dir 기반:** 캐시 경로의 루트는 항상 `cache/{poem_id}/`입니다. hash8 기반 경로는 사용하지 않습니다.
- **task_states.json 직접 수정 금지:** 반드시 `PersistentTaskDict` API(`api/models.py`)를 통해 접근합니다.
- **캐시 무효화:** Step N의 코드를 수정한 경우, Step N 이하(N~5)의 캐시를 `use_cache=false`로 재실행하여 갱신합니다.
- **`.gitignore` 확인:** `cache/` 디렉토리는 항상 `.gitignore`에 포함되어야 합니다.
