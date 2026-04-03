# Streamlit 패턴 규칙

## 폴링 패턴

- **`@st.cache_data(ttl=N)` 사용 금지:** 상태 조회 함수에 TTL 캐시를 적용하면, 캐시 유효 기간 내에 이전 상태가 반환되어 결과 미표시 버그가 발생합니다. (실제 버그 사례 있음)
- **`@st.fragment(run_every=N)` 의무화:** 폴링 블록은 fragment로 격리하여 해당 블록만 N초마다 재실행되도록 합니다. 다른 UI 탭의 깜빡임을 방지합니다.
- **`st.rerun()` 최소화:** 완료(`completed`) 또는 실패(`failed`) 상태 확인 후에만 전체 페이지 갱신 호출합니다. 무한 루프 방지.

## 상태 관리

- **`st.session_state.step_running`:** 현재 실행 중인 Step을 추적하는 플래그. 값이 `None`이면 대기 상태.
- **상태 조회 함수:** 매 호출마다 실제 API를 조회합니다 (캐시 없음).

```python
# ✅ 올바른 패턴
def fetch_task_status(task_id: str):
  response = requests.get(f"{API_URL}/api/v1/tasks/{task_id}")
  return response.json()

@st.fragment(run_every=2)
def polling_step(task_id: str):
  status = fetch_task_status(task_id)
  if status and status['status'] in ('completed', 'failed'):
    st.session_state.step_running = None
    st.rerun()

# ❌ 금지 패턴
@st.cache_data(ttl=2)
def fetch_task_status(task_id: str):
  ...
```
