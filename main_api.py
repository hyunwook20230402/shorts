import logging
import os
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

# notebook 폴더를 Python import 경로에 추가 (step*.py 파일들 위치)
sys.path.insert(0, str(Path(__file__).parent / 'notebook'))

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
logger = logging.getLogger(__name__)

api_port = int(os.environ.get('API_PORT', '8000'))


def kill_port(port: int):
  """포트 점유 중인 다른 FastAPI 프로세스 종료 (Windows)"""
  import time
  my_pid = os.getpid()
  killed = False
  try:
    result = subprocess.run(
      ['netstat', '-ano'],
      capture_output=True, text=True
    )
    for line in result.stdout.splitlines():
      if f':{port}' in line and 'LISTENING' in line:
        parts = line.split()
        try:
          pid = int(parts[-1])
          if pid != my_pid:
            subprocess.run(['taskkill', '/PID', str(pid), '/F'],
                           capture_output=True)
            logger.info(f'포트 {port} 점유 프로세스 종료: PID {pid}')
            killed = True
        except (ValueError, IndexError):
          pass
  except Exception as e:
    logger.warning(f'포트 정리 중 오류 (무시): {e}')

  # 종료한 프로세스가 있으면 포트 해제될 때까지 대기
  if killed:
    time.sleep(2)


@asynccontextmanager
async def lifespan(app: FastAPI):
  logger.info(f'FastAPI 시작: PID={os.getpid()}, PORT={api_port}')
  yield
  logger.info('FastAPI 종료')


# FastAPI 앱 생성 (UTF-8 JSON 응답)
app = FastAPI(
  title='고전시가 → YouTube Shorts 자동 생성 파이프라인 API',
  version='1.0.0',
  description='Step 0~5 웹 UI 백엔드 API 서버',
  default_response_class=ORJSONResponse,
  lifespan=lifespan,
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
    'version': '1.0.0',
    'pid': os.getpid(),
  }


if __name__ == '__main__':
  import uvicorn
  # uvicorn 바인딩 전에 포트 정리
  kill_port(api_port)
  uvicorn.run(
    app,
    host='0.0.0.0',
    port=api_port,
    log_level='info'
  )
