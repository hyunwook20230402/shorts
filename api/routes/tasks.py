import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from api.models import TaskStatus
from api.pipeline_runner import task_status_dict

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get('/tasks/{task_id}', response_model=TaskStatus)
async def get_task_status(task_id: str) -> TaskStatus:
  """작업 상태 조회"""
  if task_id not in task_status_dict:
    raise HTTPException(status_code=404, detail=f'작업 {task_id}를 찾을 수 없습니다')

  return task_status_dict[task_id]


@router.get('/tasks', response_model=list[TaskStatus])
async def list_tasks() -> list[TaskStatus]:
  """전체 작업 목록"""
  return list(task_status_dict.values())


@router.delete('/tasks/{task_id}')
async def delete_task(task_id: str) -> dict:
  """작업 삭제"""
  if task_id not in task_status_dict:
    raise HTTPException(status_code=404, detail=f'작업 {task_id}를 찾을 수 없습니다')

  del task_status_dict[task_id]
  logger.info(f'작업 삭제: {task_id}')
  return {'ok': True, 'task_id': task_id}
