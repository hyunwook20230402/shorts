---
name: 현재 프로젝트 ComfyUI 워크플로우 설정값
description: 고전시가→웹툰 파이프라인에서 사용 중인 ComfyUI 기본 설정 및 제약사항
type: project
---

## 프로젝트 개요
고전시가(예: 조선시대 시조) 원문 이미지를 입력 → 최종 웹툰 쇼츠 영상 생성.
Step 2 Vision (ComfyUI 이미지 생성)에서 사용 중.

## 현재 ComfyUI 설정값

### 모델 정보
- **Diffusion 모델:** FLUX.1 Dev fp8 (17.2GB, 경량화)
- **VAE:** ae.safetensors
- **CLIP 1:** clip_l.safetensors (clip 인코더)
- **CLIP 2:** t5xxl_fp8_e4m3fn.safetensors (t5 인코더)
- **주의:** DualCLIPLoader 필수 (CLIPLoader 단일 사용 불가, t5xxl KeyError 발생)

### KSampler 파라미터 (고정값)
```
steps: 20
cfg: 3.5
sampler_name: euler
scheduler: karras
denoise: 1.0
```

### 목표 해상도
- **최종 출력:** 512×912 (9:16 웹툰/모바일 숏츠 비율)
- **실제 입력:** 1024×1824 (ComfyUI 50% 축소 보정으로 인해 2배 입력)
- **프롬프트에 명시할 해상도:** 512×912

### 생성 성능
- **첫 로드 시간:** 5~7분 (모델 캐싱 후 2분 단축)
- **씬당 생성 시간:** 30~45초
- **최대 대기 시간:** 1800초 (타임아웃)

## 프롬프트 가이드라인

### 프롬프트 구조 (필수)
```
[LoRA_TRIGGER_IF_PRESENT], [CHARACTER_DESC], [ACTION], [SETTING], [CAMERA], [LIGHTING], [STYLE_TAGS]
```

### 캐릭터 설명 (고정 템플릿, 변경 금지)
```
korean old scholar wearing white hanbok, long white beard, wise elderly face, traditional korean clothing
```
→ 모든 씬에서 동일하게 반복 사용할 것

### 추천 파라미터
- **Camera:** close-up shot, wide shot, medium shot 등 씬 특성에 맞게 선택
- **Lighting:** cinematic lighting, warm candlelight, golden hour lighting 등
- **Style:** masterpiece, best quality, highly detailed, 8k resolution, sharp focus, professional photography

### 네거티브 프롬프트 (고정)
```
worst quality, low quality, blurry, deformed, ugly, duplicate, watermark, text, bad anatomy, extra limbs, missing limbs, disfigured, out of frame
```

## 현재 제약사항 및 향후 개선

### 1차 완료 상태 (현재)
- ✅ 기본 파이프라인 동작
- ✅ 프롬프트 이해도 개선됨 (DualCLIPLoader)
- ✅ 해상도 정상화 (512×912)
- ❌ 웹툰 스타일 LoRA 미적용
- ❌ 캐릭터 외모 일관성 없음 (씬마다 다른 외모)
- ❌ 씬 간 연결성 없음 (각 씬 독립 생성)

### 2차 고품질화 계획 (Step 3~5 완성 후)
- FLUX.1 + LoRA 학습 (웹툰/조선시대 풍속화 스타일)
- 캐릭터 Dreambooth LoRA (특정 캐릭터 외모 고정)
- IPAdapter로 씬 간 연결성 강화
- 컷 수 확장: 7개 → 20~30개

## 환경 정보
- **서버:** 로컬 (127.0.0.1:8188)
- **OS:** Windows 11 Pro
- **GPU:** NVIDIA RTX 4070 Laptop (8GB VRAM)
- **ComfyUI 버전:** 0.18.1
- **Python:** 3.12 (uv 패키지 관리)

## 주의사항
- 외부 서버(Linux)로 전환 시 모델 경로 변경 필요 (`flux1-dev-fp8.safetensors` → `FLUX1/flux1-dev-fp8.safetensors`)
- KJ 커스텀 노드 사용 여부도 서버마다 다름 (로컬: 없음, 외부: 있음)
