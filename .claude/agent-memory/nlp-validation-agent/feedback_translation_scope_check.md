---
name: 번역 범위 이탈 검증
description: modern_text가 해당 씬 1행만 번역했는지 엄격히 검증하는 항목 추가 요청
type: feedback
---

각 씬의 modern_text에 다른 씬(N+1, N+2 등) 원문 내용이 혼입됐는지 반드시 검증해야 한다.

**Why:** HCX-005가 번역 시 인접 행 내용을 한 씬에 묶어 출력하는 경우가 발생함. 예: 씬2 원문 "가을에 말라 떨어지지 아니하매,"인데 modern_text에 씬3("귀하게 여기겠다고 하셨으나") 또는 씬4("겨울에는 낯빛이 변하셨네요") 내용이 포함되는 오류.

**How to apply:**
- 검증 항목 4-1 (Translation Scope Violation)로 추가
- 다른 씬 핵심 어절 2개 이상 매칭 → ERROR, 1개 → WARNING
- 씬 병합이 의도된 경우(scene_count < ocr_line_count)는 병합 범위 내 어절 매칭 허용
- 결과를 `원문-번역 1:1 대응 검증` 표로 명시적으로 출력
- JSON 보고서에 `translation_scope_results` 배열 필드 추가
