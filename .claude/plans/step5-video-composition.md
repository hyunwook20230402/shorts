# Step 5: MoviePy 영상 합성 계획

## 개요

Step 3 오디오, Step 2 이미지, Step 4 자막을 MoviePy로 합성하여 최종 Shorts 영상 생성.

**입력:**
- 이미지: `cache/step2/` (PNG 512×912, 7개)
- 오디오: `cache/step3/` (MP3, 총 54초)
- 자막: `cache/step4/{hash}_subtitles.srt` (SRT)
- 타이밍: audio-visual-qa 리포트의 `scene_durations` (각 씬 표시 시간)

**출력:**
- 영상: `cache/step5/{hash}_shorts.mp4` (1080×1920, 9:16, 60초 이내)

---

## 기술 결정

### 1. 해상도 및 종횡비

**Shorts 규격:**
- 목표: 1080×1920 (9:16)
- 영상 길이: 60초 이내

**Step 2 → Step 5 변환:**
```
Step 2 출력: 512×912 (9:16) → MoviePy 스케일 업샘플링 → 1080×1920
또는
Step 2에서 직접 1080×1920 생성 (ComfyUI FLUX.1 가능, 시간 2배)
```

**현재 구현 계획:** Step 2 출력(512×912) 사용 후 Step 5에서 스케일 업샘플링

### 2. 씬별 타이밍 계산

**입력:**
```python
scene_durations = [9.1, 5.6, 6.1, 7.3, 8.6, 7.8, 9.8]  # 초 단위
# 전체 합산: 54.3초 ≤ 60초 제약
```

**로직:**
- 각 이미지 표시 시간 = `scene_durations[i]`
- 각 이미지는 오디오 시작 시간부터 표시

### 3. 자막 오버레이

**MoviePy 자막 통합:**
```python
from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip, CompositeAudioFileClip
from pysrt import SubRipFile

srt = SubRipFile.parse('xxx_subtitles.srt')  # SRT 파일 로드
# 각 서브타이틀에 대해 TextClip 생성
# 타이밍: subtitle.start ~ subtitle.end에 맞춰 배치
```

### 4. 캐시 구조

```
cache/
├── step2/              ← PNG 이미지 (512×912)
├── step3/              ← MP3 오디오
├── step4/              ← SRT + audio-visual-qa 리포트
├── step5/              ← 최종 MP4 영상
└── step5_work/         ← (임시) 중간 파일 (삭제 가능)
```

---

## CLI 사용법 (예상)

```bash
# Step 4 완료 후 Step 5 실행
uv run python step5_video.py cache/step1/xxx_nlp.json --audio-dir cache/step3

# 또는 명시적 지정
uv run python step5_video.py \
  cache/step1/xxx_nlp.json \
  cache/step2/ \
  cache/step3/xxx_audio.mp3 \
  cache/step4/xxx_subtitles.srt \
  cache/step4/audio_visual_qa_report.json
```

---

## 예상 함수 구조

### step5_video.py (개발 예정)

```python
def compose_video(
  image_dir: str,
  audio_path: str,
  srt_path: str,
  qa_report: dict,
  output_path: Path,
) -> str:
  """
  이미지 + 오디오 + 자막 합성 → MP4 생성

  - scene_durations: qa_report['scene_durations']에서 추출
  - 각 이미지를 scene_durations[i]만큼 표시
  - 자막을 SRT 타이밍에 맞춰 오버레이
  - 출력: cache/step5/{hash}_shorts.mp4 (1080×1920, 60초 이내)
  """
```

---

## 주요 라이브러리

- **moviepy**: 영상 합성, 자막 오버레이
- **pysrt**: SRT 파싱
- **PIL/Pillow**: 이미지 스케일링

---

## 예상 오류 및 해결책

| 오류 | 원인 | 해결 |
|------|------|------|
| 영상 길이 초과 | scene_durations 합산 > 60초 | audio-visual-qa에서 조정 |
| 자막 타이밍 오류 | SRT와 오디오 불일치 | Step 4 자막 재검증 |
| 메모리 부족 | 고해상도 이미지 합성 | 배치 처리 또는 스트리밍 |
| FFmpeg 미설치 | MoviePy 의존성 | `pip install ffmpeg-python` |

---

## 다음 단계

Step 5 구현 완료 후:
1. Step 6 YouTube 업로드 (youtube-dl, YouTube Data API v3)
2. Phase 2 웹툰 고품질화 (LoRA, IPAdapter, 컷 확장)
