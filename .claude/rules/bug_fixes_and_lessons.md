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

## 5. Flux.1-dev FP8 전환 (2026-04-05)

SD 1.5 + ControlNet + IP-Adapter 레거시 코드를 전면 제거하고 Flux.1-dev FP8을 유일한 이미지 생성 경로로 확정.

**제거된 항목**:
- SD15_CHECKPOINT, ControlNet, IP-Adapter 관련 환경변수/함수/워크플로우 (~800줄)
- `notebook/cache/pose_refs/` 스켈레톤 PNG 디렉토리
- `USE_FLUX` / `USE_CONTROLNET` 분기 플래그

**pose_type 확장**: 기존 9종 → 18종 (expressive, gazing_distant, riding_horse 등 추가)
- `expressive`: 구체적 신체 동작 없이 감정이 중심인 장면 (화자의 주장/선언/감정토로)

---

## 6. Step 4 이미지 품질 개선 — Flux guidance distillation 특성 (2026-04-06)

**증상**:
1. 비인물 씬(main_focus=object/background)에 인간 형체가 반복 등장 (3회 연속 실패)
2. 인물 씬에서 현대 신발(나이키 유사) 등 시대 고증 위반

**근본 원인**:
1. **Flux.1-dev는 guidance distillation 사용** → `BasicGuider` + `FluxGuidance` 구조이므로 **네거티브 프롬프트가 구조적으로 불가**. "no people", "without humans" 같은 부정 표현이 CLIP 임베딩에서 오히려 "people", "humans"를 활성화.
2. **seed 42 고정** → 동일 latent space 영역만 탐색하여 인물 포함 구도에서 탈출 불가.
3. **추상적 키워드** "traditional korean shoes" → Flux가 구체적 전통 신발로 해석하지 못하고 현대 신발로 폴백.

**해결책**:
```python
# ✅ 긍정 프롬프트 전환 (부정 표현 제거)
FLUX_STYLE_SUFFIX_NO_CHARACTER = (
  'uninhabited landscape, empty scenery, desolate nature, '
  'still life of nature, untouched wilderness'
)

# ✅ seed 랜덤화
'noise_seed': seed if seed >= 0 else random.randint(0, 2**31 - 1)

# ✅ composition guard (비인물 씬에서 인물 구도 폴백)
figure_comps = {'back_view', 'front_closeup', 'side_profile', 'over_shoulder'}
if not has_character and comp in figure_comps:
  comp = 'wide_establishing'

# ✅ 시대 고증 키워드 구체화
'traditional straw sandals, wooden clogs, leather shoes'  # (추상적 "traditional korean shoes" 대체)
```

**적용 규칙**:
- **Rule 1**: Flux.1-dev에서 "no X", "without X" 등 부정 표현 사용 금지 → 긍정적 대체어 사용
- **Rule 2**: seed는 항상 랜덤 (-1 기본값), 디버깅 시에만 고정
- **Rule 3**: 비인물 씬에서 인물 구도(back_view, front_closeup 등) → wide_establishing 자동 폴백
- **Rule 4**: 시대 고증 키워드는 추상적이 아닌 구체적 소품명 사용

---

## 향후 예방 규칙

1. **캐시 키/경로**: Step 모듈의 `get_cache_path()` 함수만 사용
2. **캐시 이원화**: CLI(`notebook/cache/`)와 UI(`upload_cache/`)는 분리된 캐시 사용. 상대경로 `cache/` 하드코딩 금지 — 반드시 `poem_dir` 인자 기반으로 경로 생성.
3. **선택적 파라미터**: API 라우터에서 명시적으로 전달
4. **상태 명시성**: 각 Step 완료/실패 후 `task.status` 명시적 설정
5. **Streamlit 폴링**:
   - `@st.cache_data(ttl=N)` ❌ (결과 캐싱이 부작용 야기)
   - `@st.fragment(run_every=N)` ✅ (폴링 블록만 재실행, 캐시 없음)
6. **타임스탬프 오프셋**: 씬별 alignment 사용 시 항상 누적 오프셋 더하기
7. **VRAM 보호**: 장시간 영상은 청크 분할 후 concat
