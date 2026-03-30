#!/usr/bin/env python
"""Step 0 테스트 스크립트 - 진단용"""

import requests
import json
import time
import uuid
from pathlib import Path

API_BASE = "http://127.0.0.1:8000/api/v1"

# 1. 테스트용 이미지 찾기
test_images = list(Path("cache/step2").glob("*_01_image.png"))
if not test_images:
    test_images = list(Path(".").glob("**/*.jpg")) + list(Path(".").glob("**/*.png"))

if not test_images:
    print("[ERROR] 테스트 이미지 없음")
    exit(1)

test_image = test_images[0]
print(f"[IMAGE] 테스트 이미지: {test_image}")

# 2. 작업 생성 + 이미지 업로드
print("\n[1/5] 작업 생성 중...")
task_id = str(uuid.uuid4())

with open(test_image, 'rb') as f:
    files = {'file': f}
    upload_resp = requests.post(
        f"{API_BASE}/upload",
        files=files,
        data={'task_id': task_id}
    )

print(f"응답 상태: {upload_resp.status_code}")
print(f"응답: {upload_resp.json()}")

if upload_resp.status_code != 200:
    print("[ERROR] 업로드 실패")
    exit(1)

# 3. 작업 상태 조회
print("\n[2/5] 작업 상태 조회...")
task_status = requests.get(f"{API_BASE}/tasks/{task_id}").json()
print(f"초기 상태: {task_status.get('status', 'unknown')}")
print(f"업로드 이미지 경로: {task_status.get('uploaded_image_path', 'N/A')}")

# 4. Step 0 실행
print("\n[3/5] Step 0 실행 중...")
step0_resp = requests.post(
    f"{API_BASE}/steps/step0",
    json={'task_id': task_id, 'use_cache': False, 'invalidate_downstream': False}
)
print(f"Step 0 응답: {step0_resp.json()}")

# 5. 폴링: 최대 60초 동안 상태 확인
print("\n[4/5] Step 0 완료 대기 중 (최대 60초)...")
start = time.time()
while time.time() - start < 60:
    task_status = requests.get(f"{API_BASE}/tasks/{task_id}").json()
    status = task_status['status']
    current_step = task_status.get('current_step', -1)
    message = task_status.get('status_message', '')
    ocr_text = task_status.get('ocr_text', '')

    elapsed = int(time.time() - start)
    print(f"[{elapsed:2d}초] 상태={status:12s} | Step={current_step} | {message}")

    if status in ('completed', 'failed'):
        print(f"\n[OK] Step 0 {status}!")
        break

    time.sleep(2)
else:
    print("[TIMEOUT] 60초 타임아웃 - Step 0 미완료")

# 6. 최종 결과 확인
print("\n[5/5] 최종 결과 확인...")
task_final = requests.get(f"{API_BASE}/tasks/{task_id}").json()
print(f"최종 상태: {task_final['status']}")
print(f"OCR 텍스트 길이: {len(task_final.get('ocr_text', ''))}")
print(f"에러 로그: {task_final.get('error_log', {})}")

if task_final.get('ocr_text'):
    print(f"\n[OCR] 결과 (처음 200자):\n{task_final['ocr_text'][:200]}")
else:
    print("\n[WARN] OCR 텍스트 없음")

# 7. 캐시 파일 확인
cache_files = list(Path("cache/step0").glob(f"*_ocr.txt"))
print(f"\n[CACHE] 캐시 파일 개수: {len(cache_files)}")
if cache_files:
    latest = max(cache_files, key=lambda x: x.stat().st_mtime)
    print(f"최신 파일: {latest.name}")
    with open(latest, 'r', encoding='utf-8') as f:
        content = f.read()
        print(f"파일 내용 (처음 200자):\n{content[:200]}")
