# ComfyUI 설치 및 설정 가이드

## 개요
이 가이드는 Windows 11 환경에서 ComfyUI를 설치하고 Step 2 Vision 파이프라인과 연동하는 방법을 설명합니다.

## 시스템 요구사항
- **OS**: Windows 11
- **GPU**: NVIDIA GPU (CUDA 지원) 권장 (CPU 모드도 가능하지만 매우 느림)
- **메모리**: 최소 8GB RAM, 권장 16GB 이상
- **저장소**: 약 10-20GB (모델 파일 포함)

## 1단계: ComfyUI 설치

### 1-1. uv 설치
```bash
# PowerShell에서 uv 설치
irm https://astral.sh/uv/install.ps1 | iex

# 또는 이미 설치된 경우 업그레이드
uv self update
```

### 1-2. 저장소 클론
```bash
# 적절한 위치에 ComfyUI 디렉토리 생생성
cd C:\
git clone https://github.com/comfyanonymous/ComfyUI.git
cd ComfyUI
```

### 1-3. Python 환경 설정 (uv 사용)
```bash
# Python 3.10 이상 필수
python --version

# uv를 사용하여 가상환경 생성 및 의존성 설치
uv venv

# 가상환경 활성화
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1

# 또는 cmd:
.\.venv\Scripts\activate.bat

# 의존성 설치
uv pip install -r requirements.txt

# CUDA 지원 PyTorch 설치 (GPU 사용 시)
uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

**uv의 장점:**
- 더 빠른 설치 속도 (병렬 처리)
- 더 나은 의존성 해결
- 자동 Python 버전 관리

### 1-3. 모델 다운로드
```bash
# ComfyUI 실행 후 자동 다운로드되거나, 수동으로 다운로드:
# - models/checkpoints/ 에 Stable Diffusion 모델 배치
#   예: model.safetensors (약 4-7GB)
# - HuggingFace에서 다운로드: https://huggingface.co/models

# 추천 모델:
# - Stable Diffusion 1.5: https://huggingface.co/runwayml/stable-diffusion-v1-5
# - Stable Diffusion XL: https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0
```

## 2단계: ComfyUI 실행

```bash
# 가상환경 활성화 (이미 활성화되어 있으면 생략)
# PowerShell:
.\.venv\Scripts\Activate.ps1

# 또는 cmd:
.\.venv\Scripts\activate.bat

# ComfyUI 서버 시작
python main.py

# 정상 실행 시 출력 예:
# ...
# To see the GUI, go to http://127.0.0.1:8188
```

## 3단계: 웹툰 스타일 LoRA 설정 (선택)

웹툰 스타일 이미지 생성을 위해 LoRA 모델을 추가할 수 있습니다:

```bash
# LoRA 다운로드
# 1. models/loras/ 디렉토리에 LoRA 파일 배치
#    예: webtoon_lora.safetensors
# 2. ComfyUI UI에서 LoRA를 workflow에 추가

# 추천 LoRA:
# - Webtoon style: https://civitai.com/models
# - Anime style: https://civitai.com/models
```

## 4단계: .env 파일 설정

프로젝트 루트 디렉토리(`C:\Users\user\workspaces\shorts\`)에 `.env` 파일 생성:

```env
# ComfyUI 설정
COMFYUI_HOST=localhost
COMFYUI_PORT=8188
COMFYUI_MODEL=model.safetensors

# 기타 API 키 (기존)
OPENAI_API_KEY=your_key_here
NOTION_API_KEY=your_key_here
```

## 5단계: Step 2 Vision 테스트

ComfyUI가 실행 중인 상태에서:

```bash
# Step 1 NLP 결과 사용하여 이미지 생성
python step2_vision.py cache/step1/12975cb9eb3c0067_nlp.json

# 결과:
# ✅ 이미지 생성 완료!
# ============================================================
#   씬 1: C:\Users\user\workspaces\shorts\cache\step2\xxx_00_image.png
#   씬 2: C:\Users\user\workspaces\shorts\cache\step2\xxx_01_image.png
#   ...
```

## 트러블슈팅

### 문제: "Cannot connect to ComfyUI at http://localhost:8188"
**원인**: ComfyUI 서버가 실행되지 않음

**해결**:
1. ComfyUI가 실행 중인지 확인
2. 포트 8188이 다른 프로세스에서 사용 중인지 확인:
   ```bash
   netstat -ano | findstr :8188
   ```
3. `.env`에서 `COMFYUI_PORT` 확인

### 문제: "CUDA out of memory"
**원인**: GPU 메모리 부족

**해결**:
1. 해상도 감소 (512×910 → 512×640)
2. 배치 크기 감소 (1로 설정)
3. 모델 선택: 가벼운 모델 사용 (SDXL 대신 SD 1.5)
4. CPU 모드 실행: `python main.py --cpu`

### 문제: 모델 파일을 찾을 수 없음
**원인**: `COMFYUI_MODEL` 환경변수가 잘못됨

**해결**:
1. `C:\ComfyUI\models\checkpoints\` 에서 실제 모델명 확인
2. `.env`에서 정확한 파일명으로 수정
   ```env
   COMFYUI_MODEL=model.safetensors
   # 또는
   COMFYUI_MODEL=sd-v1-5.safetensors
   ```

### 문제: "timeout" 에러
**원인**: 이미지 생성이 시간 초과

**해결**:
1. 단계별 로그 확인 (ComfyUI 서버 콘솔 확인)
2. 생성 단계(steps) 감소: `step2_vision.py` 라인 111에서 `'steps': 20` → `'steps': 10`
3. 더 강력한 GPU 필요 여부 검토

## ComfyUI API 상태 확인

ComfyUI가 제대로 설정되었는지 빠르게 테스트:

```bash
# PowerShell에서:
$response = Invoke-WebRequest -Uri "http://localhost:8188/system_stats" -ErrorAction SilentlyContinue
if ($response.StatusCode -eq 200) {
    Write-Host "✅ ComfyUI is running"
    $response.Content | ConvertFrom-Json | Format-List
} else {
    Write-Host "❌ ComfyUI is not responding"
}
```

또는 Python:

```python
import requests

try:
    response = requests.get('http://localhost:8188/system_stats', timeout=5)
    if response.status_code == 200:
        print("✅ ComfyUI is running")
        print(response.json())
except:
    print("❌ ComfyUI is not responding")
```

## 참고 자료

- **ComfyUI GitHub**: https://github.com/comfyanonymous/ComfyUI
- **ComfyUI 문서**: https://github.com/comfyanonymous/ComfyUI/wiki
- **Civit AI** (모델/LoRA): https://civitai.com/
- **Hugging Face** (모델): https://huggingface.co/

---

## 다음 단계

ComfyUI 설치 완료 후:
1. `python step2_vision.py cache/step1/12975cb9eb3c0067_nlp.json` 실행
2. `cache/step2/` 에 생성된 이미지 확인
3. 이미지 품질 검증 (해상도, 스타일, 역사적 배경 반영 등)
