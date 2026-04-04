---
name: cache-integrity-check
description: "캐시 파일 무결성을 검증합니다. JSON 파싱 가능 여부, 필수 필드 존재, 0바이트 파일, Step 간 일관성을 점검합니다."
---

# 캐시 무결성 검증

Step 실행 중 에러가 발생하거나 캐시 확인 요청 시 아래 절차를 따르세요.

## 절차

1. **대상 poem_dir 식별**: UI 환경은 `upload_cache/task_states.json`, CLI 환경은 `notebook/cache/`에서 활성 task의 poem_id를 읽고 해당 `{poem_dir}/` 경로를 결정합니다.

2. **Step 0 검증**:
   - `step0/ocr.txt`: 파일 크기 > 0, 한글 텍스트 포함 여부

3. **Step 1 검증**:
   - `step1/nlp.json`: JSON 파싱 가능, `modern_script_data` 배열 존재
   - 필수 필드: `primary_theme`, `surface_theme`, `dominant_emotion`
   - 각 scene에 `original_text`, `modern_text`, `narration`, `emotion`, `background`, `image_prompt` 필드 존재

4. **Step 2 검증**:
   - `step2/scene*_audio.mp3`: 파일 크기 > 1KB (유효한 MP3)
   - `step2/scene*_alignment.json`: JSON 파싱 가능, `total_duration` > 0
   - MP3 파일 수 == alignment JSON 파일 수 == Step 1의 scene 수와 일치

5. **Step 3 검증**:
   - `step3/sentence_schedule.json`: JSON 파싱 가능, `sentence_schedules` 배열 존재
   - 각 schedule에 `duration`, `image_prompt`, `audio_path` 필드 존재

6. **Step 4 검증**:
   - `step4/scene*_still.png`: 파일 크기 > 10KB (유효한 이미지)
   - PNG 파일 수 == Step 3 schedule 수와 일치

7. **Step 5 검증**:
   - `step5/bgm.wav`: 파일 크기 > 100KB, WAV 헤더 유효성

8. **Step 6 검증**:
   - `step6/shorts.mp4`: 파일 크기 > 100KB, 오디오 트랙 존재

8. **결과 보고**: 각 Step별 Pass/Fail 결과를 표로 출력하고, 실패한 Step에 대해 `use_cache=false` 재실행 안내를 제공합니다.

## 불량 캐시 발견 시

```
⚠️ Step 2 캐시 불일치: MP3 15개, alignment JSON 12개 (3개 누락)
→ 재실행: POST /api/v1/steps/step2 {"task_id": "xxx", "use_cache": false}
```
