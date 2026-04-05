---
name: comfyui-health-check
description: "ComfyUI 서버 연결 상태, 필수 모델 파일 존재 여부, VRAM 사용 현황을 점검합니다. Step 4 실행 전이나 에러 발생 시 사용합니다."
---

# ComfyUI 헬스 체크

Step 4 실행 전이나 이미지 생성 에러 발생 시 아래 절차를 따르세요.

## 절차

1. **서버 연결 확인**:
   - `curl -s http://127.0.0.1:8188/system_stats` 응답 확인
   - 응답 없으면 "ComfyUI 서버가 실행 중이 아닙니다" 안내

2. **환경변수 확인** (`.env`에서 읽기):
   - `COMFYUI_HOST` 설정값
   - `FLUX_UNET` — Flux.1-dev FP8 모델 파일명
   - `FLUX_LORA_NAME` — 국풍 LoRA 파일명
   - `COMFYUI_OUTPUT_DIR`, `COMFYUI_MAX_WAIT`

3. **모델 파일 존재 확인** (Bash로 확인):
   - Flux UNET: `COMFYUI_OUTPUT_DIR/../models/unet/{FLUX_UNET}`
   - LoRA: `COMFYUI_OUTPUT_DIR/../models/loras/{FLUX_LORA_NAME}`
   - CLIP: `clip_l.safetensors`, `t5xxl_fp8_e4m3fn.safetensors`
   - VAE: `ae.safetensors`
   - 업스케일: `4x-UltraSharp.pth`

4. **최근 로그 분석**:
   - `notebook/step4_image.log` 마지막 50줄 읽기
   - ERROR/WARNING 패턴 추출
   - 흔한 에러 패턴: "Connection refused", "CUDA out of memory", "timeout"

5. **결과 보고**:

```
| 항목 | 상태 | 비고 |
|------|------|------|
| 서버 연결 | ✅ | http://127.0.0.1:8188 |
| Flux UNET | ✅ | flux1-dev-fp8.safetensors |
| 국풍 LoRA | ✅ | GuoFeng5-FLUX.1-Lora.safetensors |
| CLIP 모델 | ✅ | clip_l + t5xxl_fp8 |
| 최근 에러 | ⚠️ | CUDA OOM 2건 (최근 1시간) |
```

## 흔한 문제 해결

- **CUDA OOM**: 다른 GPU 프로세스 종료, 해상도 줄이기
- **Connection refused**: ComfyUI 프로세스 확인 (`tasklist | grep python`)
- **Timeout**: `COMFYUI_MAX_WAIT` 상향 (1200 → 1800)
