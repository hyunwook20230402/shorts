---
name: 데이터베이스 Supabase → Notion API 마이그레이션
description: 파이프라인 데이터베이스를 PostgreSQL 기반 Supabase에서 Notion API 기반으로 변경
type: project
---

## 결정사항

파이프라인의 핵심 데이터베이스를 **Supabase (PostgreSQL)**에서 **Notion API (Notion Database)**로 변경했습니다. (2026-03-26 결정)

**Why:** Notion API를 사용하면 별도 데이터베이스 관리 부담 감소, 팀 협업 강화, MCP 연동을 통한 간편한 데이터 조회 가능

**How to apply:**
- 모든 신규 PRD에서 데이터베이스 스키마 정의 시 Notion Database 기반으로 작성
- 기존 Supabase SQL 스키마는 사용하지 않음
- Notion API 연동 시 필수 환경변수: `NOTION_API_KEY`, `NOTION_POEM_LOG_DB_ID`, `NOTION_TASK_STATUS_DB_ID`

## 데이터베이스 구조 변경

### poem_translation_log
- **이전**: Supabase PostgreSQL 테이블 (log_id UUID PK, original_archaic_text TEXT, ...)
- **현재**: Notion Database (log_id Title, original_archaic_text Rich Text, ...)

### task_status_log
- **이전**: Supabase PostgreSQL 테이블 (task_id UUID PK, current_step INTEGER, ...)
- **현재**: Notion Database (task_id Title, current_step Number, ...)

## 구현 지침

- Notion 페이지 생성: MCP `notion-create-pages` 또는 `notion-client` SDK 사용
- 속성 맵핑: 파이프라인 변수명 → Notion 속성명 일대일 대응 필수
- API 호출 시 retry 3회 + 지수 백오프 정책 적용
