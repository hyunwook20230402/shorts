---
name: pipeline-status-check
description: "파이프라인 진행 상태를 시각화합니다. task_states.json과 실제 캐시 파일을 대조하여 Step 0~5 진행도를 표로 출력합니다."
---

# 파이프라인 상태 확인

사용자가 파이프라인 진행 상태를 물을 때 아래 절차를 따르세요.

## 절차

1. **활성 task 찾기**: `notebook/cache/task_states.json`을 읽어 가장 최근 task_id와 poem_id를 식별합니다.
2. **poem_dir 확인**: `notebook/cache/{poem_id}/` 디렉토리 내 파일 목록을 조회합니다.
3. **Step별 캐시 존재 확인**:
   - Step 0: `step0_ocr.txt` 존재 여부
   - Step 1: `step1_nlp.json` 존재 여부
   - Step 2: `step2_scene*_audio.mp3` 파일 수
   - Step 3: `step3_sentence_schedule.json` 존재 여부
   - Step 4: `step4_scene*_still.png` 파일 수
   - Step 5: `step5_shorts.mp4` 존재 여부
4. **task_states.json 상태와 비교**: 선언 상태(`status`)와 실제 캐시 존재 여부 불일치 감지
5. **결과 테이블 출력**:

```
| Step | 이름     | 선언 상태 | 캐시 파일 | 비고 |
|------|---------|----------|----------|------|
| 0    | OCR     | completed | ✅ 1개   |      |
| 1    | NLP     | completed | ✅ 1개   |      |
| 2    | TTS     | completed | ✅ 28개  |      |
| 3    | 스케줄   | completed | ✅ 1개   |      |
| 4    | 이미지   | running   | ⚠️ 15/28 | 진행 중 |
| 5    | 병합     | pending   | ❌       |      |
```

6. **다음 행동 안내**: 다음 실행 가능한 Step과 명령어를 알려줍니다.
