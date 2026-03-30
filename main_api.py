import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from api.routes import upload, tasks, steps, files

# 환경변수 로드
load_dotenv()

# 작업 디렉토리를 프로젝트 루트로 고정
os.chdir(Path(__file__).parent)

# 로깅 설정
logging.basicConfig(
  level=logging.INFO,
  format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# FastAPI 앱 생성 (UTF-8 JSON 응답)
app = FastAPI(
  title='고전시가 → YouTube Shorts 자동 생성 파이프라인 API',
  version='1.0.0',
  description='Step 0~5 웹 UI 백엔드 API 서버',
  default_response_class=ORJSONResponse  # UTF-8 인코딩 보장
)

# 미들웨어 설정
app.add_middleware(
  CORSMiddleware,
  allow_origins=['*'],
  allow_credentials=True,
  allow_methods=['*'],
  allow_headers=['*'],
)

# 라우터 등록
app.include_router(upload.router, prefix='/api/v1', tags=['파일 업로드'])
app.include_router(steps.router, prefix='/api/v1', tags=['파이프라인 실행'])
app.include_router(tasks.router, prefix='/api/v1', tags=['작업 관리'])
app.include_router(files.router, prefix='/api/v1', tags=['캐시 파일'])


@app.get('/api/v1/health', tags=['시스템'])
async def health_check() -> dict:
  """헬스 체크"""
  return {
    'status': 'ok',
    'service': '고전시가 파이프라인 API',
    'version': '1.0.0'
  }


if __name__ == '__main__':
  import uvicorn
  api_port = int(os.environ.get('API_PORT', '8000'))
  uvicorn.run(
    app,
    host='0.0.0.0',
    port=api_port,
    log_level='info'
  )
