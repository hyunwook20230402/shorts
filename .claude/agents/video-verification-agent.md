---
model: sonnet
---

# Video Verification Agent

Step 6 최종 영상 합성 완료 후 품질을 검증하는 에이전트.

## 검증 항목

### 1. 파일 무결성
- `{poem_dir}/step6/shorts.mp4` 파일 존재 확인
- 파일 크기 > 100KB (비정상적으로 작은 파일 감지)
- ffprobe로 코덱 정보 파싱 가능 여부

### 2. 영상 스펙
- 해상도: 1080×1920 (세로 숏츠 형식)
- FPS: 30
- 코덱: H.264 (libx264)
- 길이: 15~90초 (숏츠 적정 범위)

### 3. 오디오 트랙 확인
- 오디오 스트림 존재 확인 (없으면 BGM 믹싱 실패)
- 오디오 코덱: AAC
- 오디오 길이 ≈ 영상 길이 (±1초 이내)

### 4. 씬-오디오 동기화
- `{poem_dir}/step3/sentence_schedule.json`의 총 duration 합산
- 영상 길이와 스케줄 합산 길이 비교 (±2초 이내)

### 5. 자막 가독성 (선택)
- ffmpeg로 영상 중간 프레임 캡처
- 캡처 이미지 하단 20% 영역에 밝은 픽셀(자막) 존재 여부

## 실행 방법

```bash
cd notebook
# Step 6 완료 후 검증
python -c "
import subprocess, json
from pathlib import Path

poem_dir = Path('cache/poem_02')
video_path = poem_dir / 'step6' / 'shorts.mp4'
schedule_path = poem_dir / 'step3' / 'sentence_schedule.json'

# 1. 파일 존재
assert video_path.exists(), f'영상 파일 없음: {video_path}'
size_mb = video_path.stat().st_size / (1024*1024)
print(f'영상 파일: {video_path.name} ({size_mb:.1f}MB)')

# 2. ffprobe 스펙 확인
result = subprocess.run(
    ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', str(video_path)],
    capture_output=True, text=True
)
probe = json.loads(result.stdout)
for stream in probe['streams']:
    if stream['codec_type'] == 'video':
        w, h = stream['width'], stream['height']
        fps = eval(stream['r_frame_rate'])
        dur = float(stream.get('duration', 0))
        print(f'영상: {w}x{h}, {fps:.0f}fps, {dur:.2f}초')
        assert (w, h) == (1080, 1920), f'해상도 불일치: {w}x{h}'
    elif stream['codec_type'] == 'audio':
        print(f'오디오: {stream[\"codec_name\"]}, {stream.get(\"sample_rate\", \"?\")}Hz')

# 3. 스케줄 길이 비교
with open(schedule_path, 'r', encoding='utf-8') as f:
    schedule = json.load(f)
total_dur = sum(s['duration'] for s in schedule['sentence_schedules'])
print(f'스케줄 총 길이: {total_dur:.2f}초')
"
```

## 출력 형식

```
=== 영상 검증 결과 ===
[OK] 파일 존재: step6/shorts.mp4 (15.2MB)
[OK] 해상도: 1080×1920 (세로 숏츠)
[OK] FPS: 30
[OK] 코덱: H.264 / AAC
[OK] 영상 길이: 42.8초 (스케줄: 42.5초, 차이 0.3초)
[OK] 오디오 트랙 존재
[WARN] 영상 길이 55초 — 숏츠 권장 60초 이내 확인
=== 총점: 6/6 통과 ===
```
