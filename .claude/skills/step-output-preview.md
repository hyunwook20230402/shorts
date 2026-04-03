---
name: step-output-preview
description: "특정 Step의 최신 캐시 결과를 요약 출력합니다. Step 완료 후 결과를 확인하거나 디버깅 시 사용합니다."
---

# Step 결과 미리보기

Step 완료 후 "결과 봐줘" 요청이나 디버깅 시 아래 절차를 따르세요.

## 절차

1. **대상 식별**: `notebook/cache/task_states.json`에서 활성 task의 poem_id를 읽고 `notebook/cache/{poem_id}/` 경로를 결정합니다.

2. **Step별 출력 형식**:

### Step 0 (OCR)
- `step0_ocr.txt` 전문 출력 (원문 텍스트)

### Step 1 (NLP)
- `step1_nlp.json` 읽어서 요약 테이블:
```
| 씬 | 원문 (앞 20자) | 감정 | 배경 | 포커스 |
|----|---------------|------|------|--------|
| 1  | 청산리 벽계수야... | 비장 | 산수화 | background |
| 2  | 일도 창해하면... | 서정 | 바다 | character |
```
- 총 씬 수, 제목, 작가 정보 포함

### Step 2 (TTS)
- 오디오 파일 목록 + 각 파일의 `total_duration` 값
- alignment JSON에서 문장 타임스탬프 샘플 3개 출력
- 총 재생 시간 합계

### Step 3 (스케줄링)
- `step3_sentence_schedule.json` 읽어서 요약:
  - 총 문장 수, 각 문장의 duration 범위
  - image_prompt 앞 50자 샘플 3개

### Step 4 (이미지)
- PNG 파일 목록 + 각 파일 크기
- 총 이미지 수 / 예상 이미지 수 비교
- 이미지 파일이 있으면 Read 도구로 시각적 확인 가능 안내

### Step 5 (최종 병합)
- `step5_shorts.mp4` 파일 크기
- 영상 사양 안내 (1080x1920, 30fps)
- 완성 상태 확인

3. **누락 감지**: 예상 파일이 없으면 해당 Step 재실행 안내를 제공합니다.
