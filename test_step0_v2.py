#!/usr/bin/env python
"""Step 0 테스트 스크립트 - 진단용 (v2)"""

import requests
import json
import time
from pathlib import Path

API_BASE = "http://127.0.0.1:8000/api/v1"

# 1. 테스트용 이미지 찾기
test_images = list(Path("cache/step2").glob("*_01_image.png"))
if not test_images:
    print("[ERROR] 테스트 이미지 없음")
    exit(1)

test_image = test_images[0]
print(f"[IMAGE] 테스트 이미지: {test_image}")

# 2. 이미지 업로드 (task_id 자동 생성)
print("\n[1/5] 이미지 업로드 중...")
with open(test_image, 'rb') as f:
    files = {'file': f}
    upload_resp = requests.post(f"{API_BASE}/upload", files=files)

print(f"응답 상태: {upload_resp.status_code}")
upload_data = upload_resp.json()
print(f"응답: {upload_data}")

if upload_resp.status_code != 200:
    print("[ERROR] 업로드 실패")
    exit(1)

task_id = upload_data['task_id']
print(f"생성된 task_id: {task_id}")

# 3. 작업 상태 확인
print("\n[2/5] 작업 상태 확인...")
task_status = requests.get(f"{API_BASE}/tasks/{task_id}").json()
print(f"초기 상태: {task_status.get('status')}")
print(f"업로드 경로: {task_status.get('uploaded_image_path')}")

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
    status = task_status.get('status', 'unknown')
    current_step = task_status.get('current_step', -1)
    message = task_status.get('status_message', '')
    ocr_text = task_status.get('ocr_text', '')

    elapsed = int(time.time() - start)
    ocr_len = len(ocr_text) if ocr_text else 0
    print(f"[{elapsed:2d}초] status={status:12s} | step={current_step} | ocr_len={ocr_len} | {message}")

    if status in ('completed', 'failed'):
        print(f"\n[OK] Step 0 {status}!")
        break

    time.sleep(2)
else:
    print("[TIMEOUT] 60초 타임아웃 - Step 0 미완료")

# 6. 최종 결과
print("\n[5/5] 최종 결과...")
task_final = requests.get(f"{API_BASE}/tasks/{task_id}").json()
print(f"최종 상태: {task_final.get('status')}")
print(f"OCR 텍스트 길이: {len(task_final.get('ocr_text', '')) if task_final.get('ocr_text') else 0}")
print(f"에러 로그: {task_final.get('error_log', {})}")

if task_final.get('ocr_text'):
    print(f"\n[OCR] 결과 (처음 300자):")
    print(task_final['ocr_text'][:300])
else:
    print("\n[WARN] OCR 텍스트 없음")

# 7. 캐시 파일 확인
cache_files = sorted(Path("cache/step0").glob("*_ocr.txt"), key=lambda x: x.stat().st_mtime, reverse=True)
if cache_files:
    latest = cache_files[0]
    print(f"\n[CACHE] 최신 파일: {latest.name}")
    with open(latest, 'r', encoding='utf-8') as f:
        content = f.read()
        print(f"파일 내용 (처음 300자):")
        print(content[:300])
else:
    print("\n[CACHE] 캐시 파일 없음")
