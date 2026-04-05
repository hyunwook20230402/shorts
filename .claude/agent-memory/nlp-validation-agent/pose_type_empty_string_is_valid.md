---
name: pose_type 빈 문자열 정상 케이스
description: main_focus에 character가 없는 씬에서 pose_type 빈 문자열은 의도된 정상 동작
type: feedback
---

pose_type이 빈 문자열인 씬을 오류로 판정하면 오탐(false positive)이 발생한다.

`step1_nlp.py` 283번 줄, 489~491번 줄의 설계:
- `main_focus`에 "character"가 포함된 씬 → pose_type 9종 중 1개 선택 (필수)
- `main_focus`에 "character"가 없는 씬 (background/object 전용) → `pose_type = ''` (빈 문자열, 정상)

빈 문자열인 경우 Step 4 ComfyUI에서 ControlNet 포즈를 적용하지 않음 — 의도된 동작.

**Why:** main_focus가 background/object인 씬에는 인물 포즈 자체가 불필요하며, ControlNet 포즈를 강제 적용하면 오히려 이미지 품질이 저하됨.

**How to apply:** pose_type 검증 시 반드시 해당 씬의 main_focus를 먼저 확인한다.
- main_focus에 "character"가 없으면 → pose_type 빈 문자열은 정상, 경고 불필요
- main_focus에 "character"가 포함됐는데 pose_type이 빈 문자열이면 → 경고 발행
