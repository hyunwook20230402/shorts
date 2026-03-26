---
name: 데이터 플라이휠 3가지 파인튜닝 구간
description: 파이프라인 운영에서 생성되는 데이터로 오픈소스 모델을 점진적으로 개선하는 전략
type: project
---

## 데이터 플라이휠 전략

**적용 날짜:** 2026-03-26

프로젝트의 핵심 가치: **파이프라인 운영 → 데이터 축적 → 파인튜닝 → 성능 향상**의 선순환

### 3가지 파인튜닝 구간

#### 1. [Vision] 웹툰 스타일 일관성 고도화 (필수)
- 수집 대상: ComfyUI에서 생성한 이미지 (512x910), 피드백 로그, 재생성 횟수
- 파인튜닝 대상: ComfyUI LoRA 가중치
- 목표: 조선시대 복식 정확도, 웹툰 화풍 안정성, 이질적 생성 감소
- 활용처: Step 2 Vision 단계

#### 2. [NLP] 고어 번역 특화 모델
- 수집 대상: poem_translation_log (original_archaic_text X + translated_modern_text y)
- 파인튜닝 대상: 오픈소스 LLM (Llama 3 등, QLoRA 방식)
- 목표: 상용 API(gpt-4o-mini) 의존도 감소, 번역 지연 시간 단축
- 활용처: Step 1 NLP 단계 (로컬 모델 우선 사용)

#### 3. [OCR] 옛한글 추출 특화 모델
- 수집 대상: 고전시가 원문 이미지 + extracted_raw_text 쌍
- 파인튜닝 대상: TrOCR 등 경량 문서 이해 모델
- 목표: Vision LLM 비용 절감, 추론 속도 향상
- 활용처: Step 0 OCR 단계 (로컬 모델 우선, 실패 시 Vision LLM 폴백)

**Why:** 상용 API 비용 절감 + 내부 데이터에 특화된 모델로 성능 극대화

**How to apply:** 모든 PRD의 "데이터 플라이휠 전략" 섹션에서 이 3가지 구간을 명시, Step별 구현 지침에서 데이터 수집 요구사항 포함
