---
model: sonnet
---

# BGM Verification Agent

Step 5 (Stable Audio) BGM 생성 완료 후 품질을 검증하는 에이전트.

## 검증 항목

### 1. 파일 무결성
- `{poem_dir}/step5/bgm.wav` 파일 존재 확인
- 파일 크기 > 0 바이트
- WAV 헤더 유효성 (soundfile 또는 ffprobe로 확인)

### 2. 오디오 스펙
- 샘플레이트: 44100Hz (Stable Audio 기본)
- 채널 수: 1 (모노) 또는 2 (스테레오)
- 비트 깊이: 16bit 이상

### 3. 길이 검증
- `{poem_dir}/step3/sentence_schedule.json`의 총 duration 합산
- BGM 길이 ≥ 영상 총 길이인지 확인
- BGM이 짧으면 "루프 필요" 경고 출력

### 4. 무음 구간 감지
- 전체 BGM에서 연속 무음(< -60dB) 구간이 3초 이상이면 경고
- 시작/끝 1초 내 무음은 정상 (fade-in/out)

### 5. 테마 일치성 (선택)
- `{poem_dir}/step1/nlp.json`에서 `primary_theme` 확인
- `theme_config.py`의 `THEME_BGM_HINTS`에서 해당 테마 힌트 조회
- BGM 프롬프트가 테마 힌트와 대략 일치하는지 확인 (로그에서 추출)

## 실행 방법

```bash
cd notebook
# Step 5 완료 후 검증
python -c "
import soundfile as sf
import json
from pathlib import Path

poem_dir = Path('cache/poem_02')
bgm_path = poem_dir / 'step5' / 'bgm.wav'
schedule_path = poem_dir / 'step3' / 'sentence_schedule.json'

# 파일 무결성
assert bgm_path.exists(), f'BGM 파일 없음: {bgm_path}'
data, sr = sf.read(str(bgm_path))
print(f'BGM: {len(data)/sr:.2f}초, {sr}Hz, shape={data.shape}')

# 길이 비교
with open(schedule_path, 'r', encoding='utf-8') as f:
    schedule = json.load(f)
total_dur = sum(s['duration'] for s in schedule['sentence_schedules'])
print(f'영상 총 길이: {total_dur:.2f}초')
print(f'BGM 길이: {len(data)/sr:.2f}초')
if len(data)/sr < total_dur:
    print('WARNING: BGM이 영상보다 짧음 → Step 6에서 루프 처리됨')
else:
    print('OK: BGM 길이 충분')
"
```

## 출력 형식

```
=== BGM 검증 결과 ===
[OK] 파일 존재: step5/bgm.wav (2.3MB)
[OK] 샘플레이트: 44100Hz, 스테레오
[OK] BGM 길이: 45.2초 (영상: 42.8초)
[WARN] 무음 구간 감지: 12.3~15.8초 (3.5초)
=== 총점: 3/4 통과 ===
```
