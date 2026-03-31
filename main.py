#!/usr/bin/env python3
"""
Shorts 파이프라인 CLI 진입점
단독 실행: python main.py [command] [options]
또는 uv run python main.py [command] [options]
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from api.pipeline_runner import run_pipeline_async, PersistentTaskDict

# 로깅 설정
logging.basicConfig(
  level=logging.INFO,
  format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_pipeline_cmd(args):
  """pipeline 서브커맨드: 파이프라인 실행"""
  image_path = Path(args.image)

  if not image_path.exists():
    logger.error(f'이미지 파일 없음: {image_path}')
    sys.exit(1)

  logger.info(f'파이프라인 실행: {image_path}')
  logger.info(f'  시작 step: {args.start}')
  logger.info(f'  종료 step: {args.end}')
  logger.info(f'  캐시: {not args.no_cache}')

  try:
    # 비동기 파이프라인 실행
    task_id = asyncio.run(
      run_pipeline_async(
        image_path=str(image_path),
        start_step=args.start,
        end_step=args.end,
        use_cache=not args.no_cache
      )
    )
    logger.info(f'✓ 파이프라인 시작: task_id={task_id}')

    # 작업 상태 모니터링
    task_dict = PersistentTaskDict()
    while True:
      status = task_dict.get(task_id)
      if status and status.get('status') in ('completed', 'failed'):
        if status['status'] == 'completed':
          logger.info('✓ 파이프라인 완료')
          if 'video_output_path' in status:
            logger.info(f'  최종 영상: {status["video_output_path"]}')
        else:
          logger.error('✗ 파이프라인 실패')
          if 'error_log' in status:
            logger.error(f'  에러: {status["error_log"]}')
        break
      logger.info(f'  상태: {status.get("status", "unknown")}')
      asyncio.run(asyncio.sleep(2))

  except Exception as e:
    logger.error(f'파이프라인 실행 실패: {e}')
    sys.exit(1)


def serve_cmd(args):
  """serve 서브커맨드: FastAPI 서버 시작"""
  import uvicorn
  from main_api import app

  logger.info(f'API 서버 시작: http://127.0.0.1:{args.port}')
  logger.info('Ctrl+C로 중지')

  try:
    uvicorn.run(
      app,
      host='127.0.0.1',
      port=args.port,
      log_level='info'
    )
  except KeyboardInterrupt:
    logger.info('\n서버 중지됨')


def test_cmd(args):
  """test 서브커맨드: pytest 테스트 실행"""
  import pytest

  pytest_args = [
    'tests/',
    '-v',
    '--tb=short',
  ]

  if args.unit:
    pytest_args.append('tests/test_unit.py')
  elif args.integration:
    pytest_args.append('tests/test_integration.py')
  elif args.pipeline:
    pytest_args.append('tests/test_pipeline.py')

  if args.keyword:
    pytest_args.extend(['-k', args.keyword])

  logger.info(f'pytest 실행: {" ".join(pytest_args)}')
  exit_code = pytest.main(pytest_args)
  sys.exit(exit_code)


def main():
  """CLI 메인 진입점"""
  parser = argparse.ArgumentParser(
    description='고전시가 → Shorts 파이프라인 CLI',
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog='''
예시:
  python main.py pipeline poem.jpg                    # 전체 파이프라인
  python main.py pipeline poem.jpg --start 2 --end 4  # Step 2~4만
  python main.py serve --port 8000                    # API 서버
  python main.py test --unit                          # 단위 테스트
    '''
  )

  subparsers = parser.add_subparsers(dest='command', help='서브커맨드')

  # pipeline 커맨드
  pipeline_parser = subparsers.add_parser('pipeline', help='파이프라인 실행')
  pipeline_parser.add_argument('image', help='입력 이미지 경로')
  pipeline_parser.add_argument('--start', type=int, default=0, help='시작 step (기본: 0)')
  pipeline_parser.add_argument('--end', type=int, default=5, help='종료 step (기본: 5)')
  pipeline_parser.add_argument('--no-cache', action='store_true', help='캐시 무시')
  pipeline_parser.set_defaults(func=run_pipeline_cmd)

  # serve 커맨드
  serve_parser = subparsers.add_parser('serve', help='API 서버 시작')
  serve_parser.add_argument('--port', type=int, default=8000, help='포트 (기본: 8000)')
  serve_parser.set_defaults(func=serve_cmd)

  # test 커맨드
  test_parser = subparsers.add_parser('test', help='pytest 테스트 실행')
  test_group = test_parser.add_mutually_exclusive_group()
  test_group.add_argument('--unit', action='store_true', help='단위 테스트만')
  test_group.add_argument('--integration', action='store_true', help='통합 테스트만')
  test_group.add_argument('--pipeline', action='store_true', help='파이프라인 테스트만')
  test_parser.add_argument('-k', '--keyword', help='pytest -k 필터')
  test_parser.set_defaults(func=test_cmd)

  args = parser.parse_args()

  if not args.command:
    parser.print_help()
    sys.exit(0)

  args.func(args)


if __name__ == '__main__':
  main()
