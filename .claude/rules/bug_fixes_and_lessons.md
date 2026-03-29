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

## 향후 예방 규칙

1. **캐시 키/경로**: Step 모듈의 `get_cache_path()` 함수만 사용
2. **선택적 파라미터**: API 라우터에서 명시적으로 전달
3. **상태 명시성**: 각 Step 완료/실패 후 `task.status` 명시적 설정
4. **Streamlit 폴링**:
   - `@st.cache_data(ttl=N)` ❌ (결과 캐싱이 부작용 야기)
   - `@st.fragment(run_every=N)` ✅ (폴링 블록만 재실행, 캐시 없음)
