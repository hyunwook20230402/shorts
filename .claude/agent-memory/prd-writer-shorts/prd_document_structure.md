---
name: 표준 PRD 문서 구조 및 품질 검증 체크리스트
description: 모든 PRD 작성 시 따르는 10개 섹션 구조 및 검증 항목
type: project
---

## 표준 PRD 문서 구조

**적용 날짜:** 2026-03-26 (최종 업데이트: 2026-03-28)

**파이프라인 구조:** Step 0~6 (7단계)
- Step 0: OCR
- Step 1: NLP
- Step 2: Vision (ComfyUI)
- Step 3: Audio (TTS)
- Step 4: Subtitle (SRT)
- Step 5: Video (MoviePy)
- Step 6: Publish (YouTube)

### 10가지 필수 섹션

1. **제품 개요 (Product Overview)** — 목표, 핵심 가치, 성공 지표
2. **시스템 아키텍처 및 데이터 흐름** — 컴포넌트 다이어그램, task_status_dict 정의
3. **데이터베이스 스키마** — Notion Database 테이블 정의 (poem_translation_log, task_status_log)
4. **단계별 요구사항 및 구현 지침** — 각 Step 0~6의 입력/처리/출력/제약조건
5. **API 명세** — FastAPI `/api/v1/` 엔드포인트, 요청/응답 스키마
6. **UI 요구사항** — Streamlit 화면별 컴포넌트
7. **에러 처리 및 재시도 정책** — retry 3회 + 지수 백오프
8. **데이터 플라이휠 전략** — 3가지 파인튜닝 구간
9. **비기능 요구사항** — 성능, 보안, 확장성
10. **용어 사전** — 프로젝트 전용 변수명 및 개념 정의

## 품질 검증 체크리스트

PRD 작성 완료 후 반드시 확인:

- [ ] 모든 변수명이 snake_case인가?
- [ ] 각 Step의 입력/출력이 명확히 연결되는가?
- [ ] API 엔드포인트가 `/api/v1/` 형식인가?
- [ ] 에러 처리 및 retry 정책이 명시되었는가?
- [ ] ComfyUI LoRA 트리거 워드 삽입 조건이 명시되었는가?
- [ ] 영상 해상도(512x910 생성 → 1080x1920 최종) 명시되었는가?
- [ ] **poem_translation_log DB 로깅이 Step 1에 포함되는가?**
- [ ] **데이터 플라이휠 전략(3가지 파인튜닝 구간)이 명시되었는가?**
- [ ] **Notion Database 연동이 명시되었는가? (Supabase 아님)**
- [ ] **Step 4 (Subtitle SRT 생성)이 독립 모듈로 포함되는가?**
- [ ] **Step 3~4 캐시 구조가 명시되었는가?** (cache/step3/ MP3, cache/step4/ SRT+JSON)

**Why:** 일관된 PRD 품질 보장, 데이터 플라이휠 전략 및 DB 요구사항 누락 방지

**How to apply:** 매 PRD 작성 후 이 체크리스트로 검증, 모든 항목이 체크되어야 PRD 완성
