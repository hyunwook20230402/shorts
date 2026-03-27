---
name: ComfyUI 해상도 오류 (Step 2)
description: ComfyUI FLUX 생성 시 설정 해상도가 기준의 50%로 생성되는 문제 발견
type: project
---

## 발견사항

**발생 일시:** 2026-03-27
**Step:** Step 2 Vision (ComfyUI 이미지 생성)
**영향 범위:** 전체 7개 씬

## 문제 상세

### 증상
- 모든 생성 이미지가 **256×448 해상도**로 출력됨
- 프롬프트에는 **512×910 (9:16 수직)** 명시
- 종횡비는 맞으나(9:16) **절대 해상도가 50% 수준**

### 출력 예시
```
실제:   256 × 448
기준:   512 × 910
비율:   50% 너비, 49% 높이
```

### 영향도
- **YouTube Shorts 최종 해상도:** 1080×1920
- **확대 시 화질:** 심각한 픽셀화 및 모자이크
- **전체 파이프라인 영향:** Step 4 (비디오 합성) 품질 저하

## 원인 추정

1. **ComfyUI workflow 설정값 오류**
   - workflow JSON에서 `width: 256, height: 448` 하드코딩
   - 프롬프트와 설정값 불일치

2. **API 호출 파라미터 오류**
   - Step2 vision.py에서 ComfyUI 호출 시 잘못된 해상도 전달

3. **기본값 문제**
   - FLUX 모델 기본 해상도가 256×448일 가능성

## 복구 방안

### 즉시 조치
1. `cache/step1/12975cb9eb3c0067_nlp.json`의 image_prompts 확인
2. 프롬프트에 명시된 해상도 요구사항 재확인
3. ComfyUI workflow 파일 점검

### 수정 체크리스트
```
[ ] ComfyUI workflow JSON 해상도 설정 수정
    - width: 256 → 512
    - height: 448 → 910

[ ] step2_vision.py API 호출 파라미터 검증
    - 해상도 명시적 지정

[ ] 프롬프트에 강제 해상도 추가
    - "MUST BE 512x910 pixels"
    - "Do not downscale"

[ ] 재생성 실행 및 메타데이터 검증
```

## 교훈

**Why:** FLUX 모델이 지정된 해상도와 다르게 동작하거나, ComfyUI 설정 우선순위 문제

**How to apply:** 향후 ComfyUI 생성 시마다:
1. workflow 설정값 × 프롬프트 해상도 일치 확인
2. 생성 직후 메타데이터 검증 (PIL로 실제 해상도 확인)
3. 불일치 시 즉시 중단 및 수정 (계속 생성하면 시간 낭비)

## 상태
- **발견자:** Quality Assurance Agent
- **재생성 요청:** art_director_agent (2026-03-27)
- **1차 재시도:** 대기 중
