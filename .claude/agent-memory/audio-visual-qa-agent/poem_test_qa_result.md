---
name: poem_test_qa_result
description: poem_test Step 2 QA 결과 — 8씬 전체 합격, scene_durations 산출 완료 (최신: 2026-04-05)
type: project
---

poem_test (길재 "오백년 도읍지를 ~") Step 2 TTS QA 검증 결과.

## 2026-04-05 검증 (최신)

- 씬 수: 8 (NLP scene_index 1~8, 파일 scene00~scene07)
- 전체 오디오 합산: 39.456s (Shorts 60초 제한 여유 20.544s)
- 전체 합격 — 경고/중단 권고 없음
- 이전 검증(2026-04-04, 36.72s) 대비 TTS 재생성으로 길이 변경됨

씬별 actual_duration (mutagen):
  씬0: 6.744s, 씬1: 4.752s, 씬2: 5.376s, 씬3: 3.696s
  씬4: 5.328s, 씬5: 4.488s, 씬6: 4.104s, 씬7: 4.968s

Step 3 scene_durations (audio + 0.5s 패딩):
  [7.244, 5.252, 5.876, 4.196, 5.828, 4.988, 4.604, 5.468]

누적 오프셋:
  [0.0, 6.744, 11.496, 16.872, 20.568, 25.896, 30.384, 34.488]

보고서 경로: notebook/cache/poem_test/step2/audio_visual_qa_report.json

## 2026-04-04 검증 (구버전 참고)

씬별 actual_duration:
  씬0: 4.896s, 씬1: 6.264s, 씬2: 5.304s, 씬3: 4.080s
  씬4: 3.312s, 씬5: 4.656s, 씬6: 4.056s, 씬7: 4.152s
전체 합산: 36.72s
