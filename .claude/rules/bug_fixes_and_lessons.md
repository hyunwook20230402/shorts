# 버그 수정 및 설계 교훈

## 1. 캐시 키 일관성 & Step 1 use_cache 파라미터 전달 버그

**발생 시기**: 2026-03-29

**증상**:
- Step 1 NLP 캐시 경로 불일치 (생성 경로 ≠ 조회 경로)
- API 라우터에서 `use_cache` 파라미터를 무시하여 캐시 무효화 불가능

**근본 원인**:
1. `pipeline_runner.py`가 독립적으로 캐시 경로를 계산 → `step1_nlp.py`의 로직과 불일치
2. `api/routes/steps.py`에서 요청 파라미터를 명시적으로 전달하지 않음

**해결책**:
```python
# ✅ 캐시 경로: 항상 Step 모듈의 함수 사용
from step1_nlp import get_cache_path
nlp_path = get_cache_path(ocr_text)

# ✅ API 라우터: 요청 파라미터 명시적 전달
await run_step1(request.task_id, task.ocr_text, request.use_cache)
```

**적용 규칙**:
- **Rule 1**: 각 Step 모듈(`stepN_*.py`)에서만 캐시 경로 생성
- **Rule 2**: `pipeline_runner.py`는 Step 모듈의 `get_cache_path()` 함수 사용
- **Rule 3**: API 라우터는 요청 파라미터를 명시적으로 전달
- **Rule 4**: 완료 후 `task.status = StepStatusEnum.completed` 명시적 설정

---

## 2. Step 1 NLP 결과 미표시 버그 (@st.cache_data TTL 이슈)

**발생 시기**: 2026-03-30

**증상**: Step 0 완료 후 Step 1 실행 버튼을 눌러도 씬 카드가 표시되지 않음

**근본 원인**:
- `@st.cache_data(ttl=2)` 캐시가 TTL(2초) 내에 새로운 상태(nlp_cache_path=None)를 반환
- Step 1 완료 직후에도 캐시된 이전 상태를 반환하여 조건 `if status['nlp_cache_path']:`가 False 평가

**해결책**:
```python
# ❌ 제거된 패턴
@st.cache_data(ttl=2)
def fetch_task_status(task_id: str):
  ...

# ✅ 새로운 패턴
def fetch_task_status(task_id: str):  # 캐시 제거, 매번 실제 API 조회
  ...

# 폴링은 @st.fragment(run_every=2)로 분리
@st.fragment(run_every=2)
def polling_step1(task_id: str):
  status = fetch_task_status(task_id)
  if status and status['status'] in ('completed', 'failed'):
    st.session_state.step_running = None
    st.rerun()  # 전체 페이지 갱신 (완료 시만)
```

**이점**:
- **캐시 없음**: 매 폴링마다 최신 상태 조회
- **Fragment**: 폴링 블록만 2초마다 재실행 → 다른 탭 깜빡임 없음
- **St.rerun() 최소화**: 완료 시에만 전체 페이지 갱신 → 성능 개선

---

## 3. 커밋 이력 (2026-03-30)

| 커밋 | 내용 |
|------|------|
| dfffe7b | Step 1 NLP 캐시 경로 + use_cache 파라미터 수정 |
| 7b0139e | Step 0~5 완료 후 상태 명시적 설정 |
| 5eb1a4d | 파이프라인 점검: 코드 버그 수정 + 에이전트 개선 |
| 83b10b1 | Step 5 구현: MoviePy 영상 합성 |

**최신 커밋**: Step 1 NLP 결과 미표시 버그 수정 (fragment 패턴 도입)

---

## 4. ElevenLabs alignment 타임스탬프 누적 오프셋 처리

**설계**: v2에서 각 씬의 alignment JSON은 씬 내부 시간으로만 저장됨.

최종 영상 타임라인에서 자막을 렌더링할 때:
```python
global_start = sentence.start + cumulative_time
global_end = sentence.end + cumulative_time
```
즉, 이전 씬들의 누적 오디오 길이를 `start_offset`으로 더해야 함.

**규칙**:
- Scene 0: offset = 0
- Scene 1: offset = Scene 0 duration
- Scene N: offset = sum(Scene 0...N-1 durations)

---

## 5. AnimateDiff VRAM 보호 규칙

**제약**: RTX 4070 (8GB) 제한으로 한 번에 긴 영상 생성 불가.

**해결책**: 청크 분할 렌더링
```
총 프레임 = total_duration × FPS(10)
CHUNK_SIZE = 16 (최대 배치)
if 총 프레임 > CHUNK_SIZE:
  → 16프레임씩 분할 렌더링 후 ffmpeg concat
```

**추가 설정**:
- `COMFYUI_MAX_WAIT = 1200` (초, 기본 600 → 1200으로 상향)
- SD 1.5 + LoRA + AnimateDiff는 v1 FLUX보다 렌더링 시간 증가

---

## 6. v2 호환성 규칙

**캐시 호환성**:
- 기존 v1 task 상태가 캐시에 남아 있을 경우, Pydantic `default=[]`|`None` 처리로 역직렬화 오류 없음
- v1 task로 v2 step 실행 시: "Step 2를 먼저 실행하세요" 오류 자연 처리됨

**폴더 구조**:
- `cache/step2/`: v1은 이미지 PNG, v2는 오디오 MP3 + alignment JSON → 파일명 패턴 다르므로 충돌 없음
- `cache/step3/`: v2 신규 폴더 (스케줄)
- `cache/step4/`: v1은 자막 SRT, v2는 AnimateDiff MP4 → 파일명 패턴 다름

**기존 파일 유지**:
- `step2_vision.py`, `step3_audio.py`, `step4_subtitle.py`: 삭제하지 않고 유지
  - 롤백 시 `pipeline_runner.py` import만 되돌리면 됨
  - CLI 직접 실행 호환성 보존

---

## 향후 예방 규칙

1. **캐시 키/경로**: Step 모듈의 `get_cache_path()` 함수만 사용
2. **선택적 파라미터**: API 라우터에서 명시적으로 전달
3. **상태 명시성**: 각 Step 완료/실패 후 `task.status` 명시적 설정
4. **Streamlit 폴링**:
   - `@st.cache_data(ttl=N)` ❌ (결과 캐싱이 부작용 야기)
   - `@st.fragment(run_every=N)` ✅ (폴링 블록만 재실행, 캐시 없음)
5. **타임스탬프 오프셋**: 씬별 alignment 사용 시 항상 누적 오프셋 더하기
6. **VRAM 보호**: 장시간 영상은 청크 분할 후 concat
