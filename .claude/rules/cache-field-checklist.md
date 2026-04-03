# 캐시 필드 체크리스트

## Step별 JSON 출력에 새 필드 추가 시 필수 확인사항

1. **실제 저장 확인**: 코드에서 필드를 생성하는 것과 JSON 파일에 저장되는 것은 다르다.
   - json.dump / save_to_cache 호출부에서 해당 필드가 포함되는지 확인
   - 같은 파일에 이중 쓰기가 없는지 확인 (덮어쓰기 위험)
   - 반드시 하나의 저장 경로만 사용 (단일 쓰기 원칙)

2. **캐시 호환성**: 기존 캐시에는 새 필드가 없다.
   - load_from_cache 시 `.get(field, default)` 패턴 사용
   - 또는 self-healing: 필드 없으면 기본값 보충 후 재저장

3. **하위 Step 전파 확인**: 새 필드를 하위 Step에서 읽는다면,
   - 해당 Step의 JSON 파싱 코드에서 실제로 읽는지 확인
   - fallback 기본값이 합리적인지 확인

4. **E2E 검증**: 새 필드 추가 후 반드시 `use_cache=False`로 재실행하여
   실제 JSON 파일에 필드가 존재하는지 눈으로 확인

## 과거 사례

- **theme/theme_en 누락 (2026-04-04)**: step1_nlp.py에서 json.dump + save_to_cache 이중 쓰기로 theme 필드가 덮어써짐. 기존 캐시에는 필드 자체가 없어 하위 Step에서 항상 기본값 폴백.
