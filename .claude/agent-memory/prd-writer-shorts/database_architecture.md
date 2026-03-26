---
name: Supabase 데이터베이스 아키텍처
description: Supabase PostgreSQL 스키마 설계, poem_translation_log 및 task_status_log 테이블 구조
type: project
---

## 데이터베이스 구조 결정사항

**적용 날짜:** 2026-03-26

**핵심 테이블:**

1. **poem_translation_log**
   - 목적: 고전시가 원문과 현대문 번역 쌍 저장 (파인튜닝 데이터셋 기초)
   - 칼럼: log_id (UUID, PK), original_archaic_text (TEXT), translated_modern_text (TEXT), task_id (FK), created_at (TIMESTAMP)
   - Step 1 NLP에서 번역 완료 후 즉시 INSERT 필수

2. **task_status_log**
   - 목적: 파이프라인 실행 이력 추적 및 상태 관리
   - 칼럼: task_id (UUID, PK), current_step (INTEGER 0-5), status_message (TEXT), is_completed (BOOLEAN), error_log (JSONB), created_at, updated_at (TIMESTAMP)

**Why:** 데이터 축적을 통한 파인튜닝 기반 마련 필요, 파이프라인 운영 중 발생하는 X/y 쌍을 즉시 수집하려면 DB 구조가 필수

**How to apply:** 모든 PRD 작성 시 Supabase 연동 요구사항을 반드시 명시, Step 1 NLP 구현 지침에 poem_translation_log INSERT 로직 포함
