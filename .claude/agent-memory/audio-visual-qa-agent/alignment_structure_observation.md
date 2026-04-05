---
name: alignment_structure_observation
description: edge-tts alignment JSON 실제 구조 — word/sentence 레벨 타임스탬프 없음, duration 단일 값만 저장
type: project
---

edge-tts로 생성된 alignment JSON의 실제 구조는 시스템 프롬프트 예시와 다르다.

실제 구조 (scene00_sent00_alignment.json 예시):
```json
{
  "scene_index": 0,
  "sent_index": 0,
  "text": "...",
  "duration": 4.896,
  "audio_path": "..."
}
```

- `total_duration`, `words`, `sentences` 필드 없음
- `duration` 단일 값만 존재 (mutagen 측정값과 동일)
- word-level / sentence-level 타임스탬프 미포함

**Why:** edge-tts 자체는 정밀 word-level alignment를 제공하지 않음. Step 2 구현에서 텍스트 길이 기반 추정값을 `duration`에 저장하는 방식으로 설계됨.

**How to apply:** 타임스탬프 정확성 검증 시 `duration` vs mutagen 측정값 비교로 수행. word/sentence 레벨 검증은 현재 구조에서 불가능 — 정밀 타임스탬프가 필요하면 Step 2 재설계 필요.

NLP scene_index: 1-based (1~8)
파일명 scene_index: 0-based (scene00~scene07)
→ 인덱스 오프셋 주의: alignment의 scene_index = 파일 번호 + 1
