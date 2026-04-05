---
name: test1_qa_result
description: test1 Step 2 QA 결과 — 8씬 전체 합격, 28.8s, scene_durations 산출 완료 (2026-04-05)
type: project
---

test1 (농부가 — 작자 미상) Step 2 TTS QA 검증 결과.

## 2026-04-05 검증

- poem_dir: notebook/cache/test1
- 씬 수: 8 (NLP scene_index 1~8, 파일 scene00~scene07)
- 전체 오디오 합산 (alignment duration 기준): 28.800s
- Shorts 60초 제한 여유: 31.2s
- 전체 합격 — 경고/중단 권고 없음

시 내용: 농부의 고된 노동과 관리의 착취 비판 (테마 labor_customs, 정서 E3 resolute_solemn)

씬별 alignment_duration:
  씬0: 3.288s, 씬1: 3.576s, 씬2: 3.408s, 씬3: 3.864s
  씬4: 3.552s, 씬5: 3.912s, 씬6: 4.080s, 씬7: 3.120s

Step 3 scene_durations (audio + 0.5s 패딩):
  [3.788, 4.076, 3.908, 4.364, 4.052, 4.412, 4.58, 3.62]

누적 오프셋:
  [0.0, 3.288, 6.864, 10.272, 14.136, 17.688, 21.6, 25.68]

**Why:** Bash 실행 권한 없는 상황에서 alignment JSON 직접 읽기로 검증 수행. mutagen 실측 불가.
**How to apply:** 향후 동일 제약 상황 시 alignment JSON duration을 기준값으로 사용 가능 (오차 매우 작음).

보고서 경로: notebook/cache/test1/step2/audio_visual_qa_report.json
