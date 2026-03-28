---
name: Step 4 SRT 자막 생성 기술 명세
description: MoviePy 영상 합성 전 독립 모듈로 SRT 자막을 생성, 오디오 길이 기반 타이밍 계산
type: project
---

## 개요

Step 3 오디오 생성 완료 후, 음성 길이를 측정하여 자동으로 SRT 자막 파일 생성.

**파이프라인 위치:**
- 입력: `cache/step1/xxx_nlp.json` (modern_script_data) + `cache/step3/` (MP3 파일)
- 처리: mutagen으로 오디오 길이 측정 → 타임코드 계산
- 출력: `cache/step4/{hash8}_subtitles.srt`

## 주요 기술 결정

### 1. 자막 포맷: SubRip (SRT)
- YouTube, MoviePy, 모든 플레이어 지원
- 형식: 블록 번호 + 시작--끝 타임코드 + 텍스트
- 자막 텍스트: Step 1에서 생성한 `narration` 필드 사용 (TTS 음성과 정확히 일치)

### 2. 타이밍 계산
```python
def seconds_to_srt_time(seconds: float) -> str:
  h = int(seconds // 3600)
  m = int((seconds % 3600) // 60)
  s = int(seconds % 60)
  ms = int((seconds % 1) * 1000)
  return f'{h:02d}:{m:02d}:{s:02d},{ms:03d}'
```

- 오디오 길이: `mutagen.mp3.MP3(path).info.length` (초 단위 float)
- 각 씬 시작/종료 시간을 누적 계산

### 3. 캐시 키 생성
- 오디오 경로 목록 → `hashlib.md5()|` 조인 → 8자리 해시
- 캐시 경로: `cache/step4/{hash8}_subtitles.srt`
- **효과:** 오디오 파일 변경 시 자동 캐시 미스

## CLI 명령어

### 방식 A: 디렉터리 자동 수집 (권장)
```bash
uv run python step4_subtitle.py cache/step1/xxx_nlp.json --audio-dir cache/step3
```
- `cache/step3/`의 모든 `*.mp3` 자동 수집
- 파일명 패턴 `{hash8}_{idx:02d}_audio.mp3`에서 씬 인덱스(idx) 추출
- 씬 순서대로 정렬 → 타이밍 정확성 보장

### 방식 B: 명시적 파일 목록
```bash
uv run python step4_subtitle.py cache/step1/xxx_nlp.json \
  cache/step3/hash_00_audio.mp3 cache/step3/hash_01_audio.mp3 ...
```

### 캐시 정리
```bash
uv run python step4_subtitle.py --clean-cache [--force]
```

## 주요 함수

**step4_subtitle.py의 핵심:**

```python
def generate_subtitles(
  audio_paths: list[str],
  script_data: list[dict],
  output_path: Path,
) -> str:
  """
  오디오 길이 기반 SRT 생성
  - 각 씬마다: 시작시간(누적) + 오디오길이 = 종료시간
  - narration 텍스트를 SRT 블록으로 변환
  """
```

## Step 4 → Step 5 인터페이스

**Step 5 (MoviePy)로 전달:**
1. `subtitle_path`: SRT 파일 경로 → 영상에 오버레이
2. `scene_durations`: audio-visual-qa-agent에서 산출한 각 씬 표시 시간 배열
   - 계산식: `max(audio_length + 0.5초 버퍼, 최소 3.0초)`
   - Shorts 60초 제약 고려: 전체 합산 ≤ 55초

## 에러 처리

| 상황 | 처리 |
|------|------|
| 오디오 파일 없음 | 해당 씬 자막 스킵 |
| mutagen 미설치 | 경고 출력, 길이 0.0 처리 |
| 오디오 길이 조회 실패 | 해당 씬 건너뜀 |
| 빈 narration | 씬 스킵 |

## 캐시 정책

- **생성:** 첫 실행 시 `cache/step4/{hash8}_subtitles.srt` 생성
- **재사용:** `--no-cache` 플래그 없으면 기존 파일 재사용
- **무효화:** 오디오 파일 변경 시 자동 캐시 미스 (다시 생성)

## 검증 체크리스트 (PRD)

- [ ] 자막 텍스트가 narration과 정확히 일치하는가?
- [ ] 타이밍이 오디오 길이와 정확히 매칭되는가?
- [ ] 씬 순서가 idx 기준으로 정렬되는가?
- [ ] cache/step4/ 위치에만 SRT 파일이 생성되는가?
- [ ] --audio-dir 방식으로 자동 수집되는가?
