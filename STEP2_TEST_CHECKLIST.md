# Step 2 Vision 테스트 체크리스트

## 설치 전 확인사항

- [ ] Windows 11 Pro 확인
- [ ] NVIDIA GPU 있는지 확인 (없으면 CPU 모드 사용 가능)
- [ ] Python 3.10+ 설치 확인
- [ ] 인터넷 연결 확인 (모델 다운로드 필요)
- [ ] 저장소 공간 확인 (약 20GB 필요)

## ComfyUI 설치 단계

### 1. 클론 및 설치 (uv 사용)
```bash
# uv 설치 (처음 한 번만)
irm https://astral.sh/uv/install.ps1 | iex

# ComfyUI 클론
cd C:\
git clone https://github.com/comfyanonymous/ComfyUI.git
cd ComfyUI

# uv로 가상환경 생성 및 의존성 설치
uv venv
.\.venv\Scripts\Activate.ps1  # PowerShell
# 또는
.\.venv\Scripts\activate.bat  # cmd

uv pip install -r requirements.txt
uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```
- [ ] uv 설치 완료
- [ ] ComfyUI 클론 완료 (에러 없음)
- [ ] 가상환경 활성화 완료
- [ ] Python 버전 3.10+ 확인

### 2. 모델 다운로드
```bash
# models/checkpoints/ 디렉토리에 다음 파일 배치:
# - model.safetensors (또는 다른 Stable Diffusion 모델)
```
- [ ] 모델 파일 다운로드 (4-7GB)
- [ ] `C:\ComfyUI\models\checkpoints\` 에 배치
- [ ] 파일명 확인 (예: `model.safetensors`)

### 3. 환경변수 설정
`C:\Users\user\workspaces\shorts\.env` 파일:
```env
COMFYUI_HOST=localhost
COMFYUI_PORT=8188
COMFYUI_MODEL=model.safetensors
```
- [ ] `.env` 파일 생성 또는 업데이트
- [ ] 모델명이 실제 파일명과 일치

## ComfyUI 실행

```bash
cd C:\ComfyUI
venv\Scripts\activate
python main.py
```

- [ ] 서버 실행 (콘솔 메시지 확인)
- [ ] "To see the GUI, go to http://127.0.0.1:8188" 메시지 확인
- [ ] 브라우저에서 `http://localhost:8188` 접속 가능

## Step 2 테스트 실행

**새 터미널 창에서** (ComfyUI 서버 실행 중인 상태):

```bash
cd C:\Users\user\workspaces\shorts
python step2_vision.py cache/step1/12975cb9eb3c0067_nlp.json
```

- [ ] 명령어 실행 (에러 없음)
- [ ] 콘솔에 "이미지 생성 시작 (총 7씬)" 메시지
- [ ] 각 씬별 진행 상황 로깅
- [ ] 최종 "✅ 이미지 생성 완료!" 메시지

## 결과 검증

```bash
# 생성된 이미지 확인
ls cache/step2/
```

- [ ] `cache/step2/` 디렉토리에 PNG 파일 7개 생성
- [ ] 각 이미지 파일명 패턴: `{hash}_{idx:02d}_image.png`
- [ ] 파일 크기 > 50KB (유효한 이미지)

### 이미지 품질 점검

각 생성된 이미지에 대해:

- [ ] **해상도**: 512×910 픽셀 (웹툰 세로 비율)
- [ ] **스타일**: 웹툰 스타일 반영
- [ ] **역사적 배경**: 함경도 배경 설정이 반영되었는가?
  - 예: 척박한 산악 지형, 조선시대 의복, 겨울 계절감
- [ ] **색감**: 자연스러운 컬러, 왜곡 없음
- [ ] **텍스트/워터마크**: 없음 (네거티브 프롬프트에서 제거)

## 성능 측정

Step 2 실행 중:

```
시간 측정:
- 씬 1 이미지 생성: ___초
- 씬 7 이미지 생성: ___초
- 평균 시간/씬: ___초
```

- [ ] 평균 생성 시간 기록
- [ ] 예상: GPU (30초-2분/씬) / CPU (5-10분/씬)

## 캐시 검증

2번째 실행 시:

```bash
python step2_vision.py cache/step1/12975cb9eb3c0067_nlp.json
```

- [ ] "캐시에서 이미지 로드" 메시지 7번 출력
- [ ] 실행 시간 < 1초 (캐시 히트)
- [ ] ComfyUI 서버에 추가 요청 없음

## 오류 처리 검증

### 시나리오 1: ComfyUI 서버 중단
ComfyUI 실행 중단 후 Step 2 실행:

```bash
python step2_vision.py cache/step1/12975cb9eb3c0067_nlp.json
```

- [ ] RuntimeError 발생: "ComfyUI API 호출 실패"
- [ ] 재시도 3회 후 최종 실패
- [ ] 에러 로그 명확함

### 시나리오 2: 잘못된 환경변수
`.env`에서 `COMFYUI_PORT=9999` 로 변경 후:

```bash
python step2_vision.py cache/step1/12975cb9eb3c0067_nlp.json
```

- [ ] 포트 오류 감지
- [ ] 에러 메시지 출력
- [ ] 정상 종료

### 시나리오 3: 잘못된 모델명
`.env`에서 `COMFYUI_MODEL=nonexistent.safetensors` 로 변경 후:

- [ ] ComfyUI 서버 에러 로그 확인
- [ ] Step 2 timeout 또는 오류 발생

## 최종 체크리스트

- [ ] 7개 이미지 모두 생성됨
- [ ] 이미지 품질 만족
- [ ] 캐시 기능 정상 작동
- [ ] 에러 처리 정상 작동
- [ ] 평균 생성 시간 기록됨

## 다음 단계

Step 2 테스트 완료 후:
- [ ] 생성된 이미지 저장 (백업)
- [ ] Step 3 Audio 작업 진행
- [ ] 이미지 + 음성 + 자막 결합 (Step 4)
