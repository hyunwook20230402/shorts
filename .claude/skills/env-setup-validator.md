---
name: env-setup-validator
description: "환경변수 설정을 검증합니다. .env 파일의 필수 키 존재, 플레이스홀더 감지, 패키지 설치 상태를 확인합니다."
---

# 환경 설정 검증

새 환경 설정 시나 "환경변수 맞아?" 요청 시 아래 절차를 따르세요.

## 절차

1. **`.env` 파일 존재 확인**: `notebook/.env` 읽기

2. **필수 환경변수 체크리스트**:

| 변수 | 용도 | 필수 |
|------|------|------|
| `NCP_CLOVA_API_KEY` | HCX-005 OCR/번역 | ✅ |
| `OPENAI_API_KEY` | gpt-4o-mini 프롬프트 | ✅ |
| `NOTION_API_KEY` | Notion DB 연동 | ⚠️ 선택 |
| `EDGE_TTS_VOICE` | TTS 음성 (기본: ko-KR-SunHiNeural) | ⚠️ 기본값 |
| `COMFYUI_HOST` | ComfyUI 서버 주소 | ✅ |
| `COMFYUI_OUTPUT_DIR` | ComfyUI 출력 경로 | ✅ |
| `COMFYUI_MAX_WAIT` | 최대 대기 시간(초) | ⚠️ 기본값 1200 |
| `FLUX_UNET` | Flux.1-dev FP8 모델 파일명 | ✅ |
| `FLUX_LORA_NAME` | Flux 국풍 LoRA 파일명 | ✅ |
| `FLUX_LORA_STRENGTH` | Flux LoRA 적용 강도 | ⚠️ 기본값 0.8 |
| `FLUX_STEPS` | Flux 샘플링 스텝 수 | ⚠️ 기본값 20 |
| `FLUX_GUIDANCE` | Flux guidance 값 | ⚠️ 기본값 3.5 |
| `SUBTITLE_FONT_PATH` | 자막 폰트 경로 (NanumSquare.ttf) | ✅ |
| `STABLE_AUDIO_MODEL` | Stable Audio 모델 경로 | ⚠️ 기본값 |

3. **플레이스홀더 감지**: `your_key`, `your_`, `xxx`, `TODO`, 빈 값(`=""`) 패턴 검색

4. **폰트 파일 존재 확인**: `SUBTITLE_FONT_PATH` 경로에 NanumSquare.ttf 파일이 있는지 확인

5. **패키지 설치 확인**: `uv pip list` 또는 `.venv` 존재 확인

6. **결과 보고**:

```
환경 설정 검증 결과:
✅ 필수 키 N/N 설정됨
⚠️ NOTION_API_KEY — 미설정 (Notion 동기화 비활성)
✅ 폰트 파일 존재: %LOCALAPPDATA%/Microsoft/Windows/Fonts/NanumSquare.ttf
✅ .venv 존재, 패키지 설치 완료
```

## 주의

`.env` 파일은 직접 수정하지 않습니다. 변경이 필요하면 사용자에게 수정 내용을 안내합니다.
