import json
import logging
import os
import requests
import streamlit as st
import time
from pathlib import Path
from PIL import Image
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 페이지 설정
st.set_page_config(
  page_title='고전시가 → YouTube Shorts',
  page_icon='📺',
  layout='wide',
  initial_sidebar_state='expanded'
)

# API 기본 설정
if 'api_base' not in st.session_state:
  api_host = os.environ.get('API_HOST', '127.0.0.1')
  api_port = os.environ.get('API_PORT', '8000')
  st.session_state.api_base = f'http://{api_host}:{api_port}/api/v1'

if 'task_id' not in st.session_state:
  st.session_state.task_id = None

if 'pipeline_running' not in st.session_state:
  st.session_state.pipeline_running = False

if 'step_running' not in st.session_state:
  st.session_state.step_running = None


# 헬퍼 함수
def fetch_task_status(task_id: str) -> dict | None:
  """작업 상태 조회 (캐시 없음, 매 호출마다 실시간 조회)"""
  try:
    resp = requests.get(f'{st.session_state.api_base}/tasks/{task_id}', timeout=5)
    if resp.status_code == 200:
      return resp.json()
    logger.warning(f'상태 조회 실패: {resp.status_code} - {resp.text[:200]}')
  except requests.exceptions.ConnectionError:
    logger.error(f'API 서버 연결 불가: {st.session_state.api_base}')
  except Exception as e:
    logger.error(f'상태 조회 오류: {e}')
  return None


def upload_images(files: list) -> str | None:
  """이미지 N장 업로드 (순서 중요)"""
  try:
    # multipart/form-data로 여러 파일 전송
    multipart_files = [
      ('files', (f.name, f.read(), 'image/jpeg'))
      for f in files
    ]
    resp = requests.post(
      f'{st.session_state.api_base}/upload',
      files=multipart_files,
      timeout=60
    )
    if resp.status_code == 200:
      data = resp.json()
      return data['task_id']
    else:
      st.error(f'업로드 실패: {resp.status_code} - {resp.text}')
  except Exception as e:
    st.error(f'업로드 오류: {e}')
    logger.error(f'업로드 오류 상세: {e}', exc_info=True)
  return None


def run_pipeline_async(task_id: str) -> bool:
  """파이프라인 실행"""
  try:
    resp = requests.post(
      f'{st.session_state.api_base}/pipeline/run',
      json={'task_id': task_id}
    )
    return resp.status_code == 200
  except Exception as e:
    st.error(f'파이프라인 실행 오류: {e}')
  return False


def poll_until_complete(task_id: str, placeholder) -> dict | None:
  """작업 완료까지 폴링"""
  start_time = time.time()

  while True:
    status = fetch_task_status(task_id)
    if not status:
      return None

    elapsed = time.time() - start_time
    current_step = status['current_step']

    # 상태 업데이트 표시
    with placeholder.container():
      col1, col2 = st.columns([3, 1])
      with col1:
        st.progress((current_step + 1) / 7, f"Step {current_step}")
        st.write(status['status_message'])
      with col2:
        st.write(f'⏱️ {int(elapsed)}초')

    # Step별 에러 표시
    step_key = f'step{current_step}'
    if status['error_log'].get(step_key):
      st.error(f"❌ 오류: {status['error_log'][step_key]}")

    # 완료 또는 실패
    if status['status'] in ('completed', 'failed'):
      return status

    time.sleep(2)


# ============================================================================
# 사이드바
# ============================================================================

with st.sidebar:
  st.title('⚙️ 설정')

  # API 연결 상태 확인
  try:
    _health_resp = requests.get(f'{st.session_state.api_base}/health', timeout=3)
    if _health_resp.status_code == 200:
      st.success('API 연결됨')
    else:
      st.error(f'API 응답 이상: {_health_resp.status_code}')
  except requests.exceptions.ConnectionError:
    st.error('API 연결 안됨')
  except Exception:
    st.error('API 연결 안됨')

  st.divider()

  st.title('📤 이미지 업로드')
  uploaded_files = st.file_uploader(
    '고전시가 이미지 선택 (여러 장 가능 — 순서대로 업로드)',
    type=['png', 'jpg', 'jpeg'],
    accept_multiple_files=True,
    help='긴 작품은 여러 페이지 이미지를 순서대로 선택하세요. OCR 후 자동으로 이어붙입니다.'
  )

  if uploaded_files:
    st.caption(f'{len(uploaded_files)}장 선택됨')
    if st.button('✅ 업로드', use_container_width=True):
      with st.spinner(f'{len(uploaded_files)}장 업로드 중...'):
        task_id = upload_images(uploaded_files)
        if task_id:
          st.session_state.task_id = task_id
          st.success(f'✅ 업로드 완료! ({len(uploaded_files)}장)\nTask ID: {task_id[:8]}...')
        else:
          st.error('업로드 실패')

  st.divider()

  if st.session_state.task_id:
    st.title('🚀 파이프라인')
    if st.button('▶️ 전체 파이프라인 실행', use_container_width=True, type='primary'):
      st.session_state.pipeline_running = True

    if st.session_state.pipeline_running:
      status_placeholder = st.empty()
      final_status = poll_until_complete(st.session_state.task_id, status_placeholder)

      if final_status and final_status['status'] == 'completed':
        st.success('✅ 파이프라인 완료!')
        st.session_state.pipeline_running = False
        st.rerun()
      elif final_status:
        st.error('❌ 파이프라인 실패')
        st.session_state.pipeline_running = False
  else:
    st.info('📝 먼저 이미지를 업로드하세요')

  st.divider()

  if st.session_state.task_id:
    st.title('📊 작업 정보')
    status = fetch_task_status(st.session_state.task_id)
    if status:
      st.write(f"**Task ID**: `{st.session_state.task_id[:8]}...`")
      st.write(f"**상태**: {status['status']}")
      st.write(f"**Step**: {status['current_step']}/6")


# ============================================================================
# 메인 영역 - 탭
# ============================================================================

if not st.session_state.task_id:
  st.title('📺 고전시가 → YouTube Shorts 자동 생성')
  st.info('사이드바에서 이미지를 업로드하여 시작하세요.')
else:
  status = fetch_task_status(st.session_state.task_id)

  if not status:
    st.error(f'작업 정보를 불러올 수 없습니다 (task_id: {st.session_state.task_id[:8]}..., API: {st.session_state.api_base})')
    st.info('💡 API 서버가 재시작되었을 수 있습니다. 이미지를 다시 업로드해주세요.')
  else:
    st.title('📺 고전시가 → YouTube Shorts 자동 생성')

    tabs = st.tabs(['📸 Step 0: OCR', '📝 Step 1: NLP', '🔊 Step 2: 음성+타임스탬프', '📋 Step 3: 문장 스케줄', '🎨 Step 4: 정지이미지', '🎵 Step 5: BGM', '🎬 Step 6: 영상 병합'])

    # ========================================================================
    # Tab 0: OCR
    # ========================================================================
    with tabs[0]:
      col1, col2 = st.columns(2)

      with col1:
        st.subheader('📸 원본 이미지')
        if status['uploaded_image_path']:
          try:
            img = Image.open(status['uploaded_image_path'])
            st.image(img, use_container_width=True)
          except Exception as e:
            st.error(f'이미지 로드 오류: {e}')

      with col2:
        st.subheader('📝 OCR 결과')
        if status['current_step'] >= 0:
          if status['ocr_text']:
            st.text_area('원문 텍스트', value=status['ocr_text'], height=300, disabled=True)
          else:
            st.info('Step 0을 실행하면 결과가 표시됩니다')
        else:
          st.info('아직 실행되지 않았습니다')

      if st.button('▶️ Step 0 실행', key='step0_run'):
        resp = requests.post(
          f'{st.session_state.api_base}/steps/step0',
          json={'task_id': st.session_state.task_id, 'use_cache': False, 'invalidate_downstream': True}
        )
        if resp.status_code == 200:
          st.session_state.step_running = 'step0'
          st.rerun()

      if st.session_state.step_running == 'step0':
        @st.fragment(run_every=2)
        def polling_step0():
          status = fetch_task_status(st.session_state.task_id)
          if status:
            st.info(f'⏳ {status["status_message"]}')
            if status['error_log'].get('step0'):
              st.error(f"❌ 오류: {status['error_log']['step0']}")

            if status['status'] == 'completed':
              st.session_state.step_running = None
              st.rerun(scope="app")
            elif status['status'] == 'failed':
              st.session_state.step_running = None

        polling_step0()

    # ========================================================================
    # Tab 1: NLP
    # ========================================================================
    with tabs[1]:
      st.subheader('📝 NLP 처리 (번역, 씬 분할)')

      if status['nlp_cache_path']:
        try:
          cache_path = Path(status['nlp_cache_path'])
          if not cache_path.exists():
            st.warning(f'⚠️ NLP 캐시 파일을 찾을 수 없습니다. Step 1을 다시 실행해주세요.\n경로: {status["nlp_cache_path"]}')
          else:
            with open(status['nlp_cache_path'], 'r', encoding='utf-8') as f:
              nlp_data = json.load(f)

            scenes = nlp_data.get('modern_script_data', [])
            primary_theme = nlp_data.get('primary_theme', nlp_data.get('theme', ''))
            primary_theme_en = nlp_data.get('primary_theme_en', nlp_data.get('theme_en', ''))
            surface_theme = nlp_data.get('surface_theme', '')
            surface_theme_en = nlp_data.get('surface_theme_en', '')
            dominant_emotion = nlp_data.get('dominant_emotion', '')
            dominant_emotion_en = nlp_data.get('dominant_emotion_en', '')

            st.write(f'**총 {len(scenes)}개 씬**')
            col_meta1, col_meta2, col_meta3 = st.columns(3)
            with col_meta1:
              st.metric('주제 테마', f'{primary_theme} ({primary_theme_en})' if primary_theme else '-')
            with col_meta2:
              st.metric('표면 테마', f'{surface_theme} ({surface_theme_en})' if surface_theme else '-')
            with col_meta3:
              st.metric('지배적 정서', f'{dominant_emotion} ({dominant_emotion_en})' if dominant_emotion else '-')

            for idx, scene in enumerate(scenes):
              with st.expander(f"씬 {idx + 1}: {scene.get('original_text', '...')}"):
                col1, col2 = st.columns(2)

                with col1:
                  st.write('**원문**')
                  st.text(scene.get('original_text', ''))

                  st.write('**자막/음성** (modern_sentences)')
                  sentences = scene.get('modern_sentences', [scene.get('modern_text', '')])
                  st.text('\n'.join(sentences))

                with col2:
                  st.write('**감정**')
                  st.text(scene.get('emotion', ''))

                  st.write('**배경**')
                  st.text(scene.get('background', ''))

        except Exception as e:
          st.error(f'NLP 데이터 로드 오류: {e}')
      else:
        st.info('Step 1을 실행하면 결과가 표시됩니다')

      if st.button('▶️ Step 1 실행', key='step1_run'):
        resp = requests.post(
          f'{st.session_state.api_base}/steps/step1',
          json={'task_id': st.session_state.task_id, 'use_cache': False, 'invalidate_downstream': True}
        )
        if resp.status_code == 200:
          st.session_state.step_running = 'step1'
          st.rerun()

      if st.session_state.step_running == 'step1':
        @st.fragment(run_every=2)
        def polling_step1():
          status = fetch_task_status(st.session_state.task_id)
          if status:
            st.info(f'⏳ {status["status_message"]}')
            if status['error_log'].get('step1'):
              st.error(f"❌ 오류: {status['error_log']['step1']}")

            if status['status'] == 'completed':
              st.session_state.step_running = None
              st.rerun(scope="app")
            elif status['status'] == 'failed':
              st.session_state.step_running = None

        polling_step1()

    # ========================================================================
    # Tab 2: 음성+타임스탬프 (TTS)
    # ========================================================================
    with tabs[2]:
      st.subheader('🔊 음성 생성 (TTS)')

      # v2: sentence_audio_paths (2차원), fallback: audio_paths (flat)
      sentence_audio = status.get('sentence_audio_paths', [])
      flat_audio = status.get('audio_paths', [])

      if sentence_audio:
        for scene_idx, scene_audios in enumerate(sentence_audio):
          st.write(f'**씬 {scene_idx + 1}**')
          for sent_idx, audio_path in enumerate(scene_audios):
            try:
              with open(audio_path, 'rb') as f:
                st.audio(f.read(), format='audio/mp3')
            except Exception as e:
              st.error(f'오디오 로드 오류 (씬{scene_idx + 1}-문장{sent_idx + 1}): {e}')
      elif flat_audio:
        for idx, audio_path in enumerate(flat_audio):
          try:
            st.write(f'**씬 {idx + 1}**')
            with open(audio_path, 'rb') as f:
              st.audio(f.read(), format='audio/mp3')
          except Exception as e:
            st.error(f'오디오 로드 오류: {e}')
      elif status.get('error_log', {}).get('step2'):
        st.error(f"❌ Step 2 오류: {status['error_log']['step2']}")
      else:
        st.info('Step 2를 실행하면 결과가 표시됩니다')

      if st.button('▶️ Step 2 실행', key='step2_run'):
        resp = requests.post(
          f'{st.session_state.api_base}/steps/step2',
          json={'task_id': st.session_state.task_id, 'use_cache': False, 'invalidate_downstream': True}
        )
        if resp.status_code == 200:
          st.session_state.step_running = 'step2'
          st.rerun()
        else:
          st.error(f'Step 2 실행 실패: {resp.text}')

      if st.session_state.step_running == 'step2':
        @st.fragment(run_every=2)
        def polling_step2():
          status = fetch_task_status(st.session_state.task_id)
          if status:
            st.info(f'⏳ {status["status_message"]}')
            if status['error_log'].get('step2'):
              st.error(f"❌ 오류: {status['error_log']['step2']}")

            if status['status'] == 'completed':
              st.session_state.step_running = None
              st.rerun(scope="app")
            elif status['status'] == 'failed':
              st.session_state.step_running = None
              st.rerun(scope="app")

        polling_step2()

    # ========================================================================
    # Tab 3: 문장 스케줄
    # ========================================================================
    with tabs[3]:
      st.subheader('📋 문장 스케줄')

      # v2: sentence_schedule_path, fallback: frame_schedule_path
      schedule_path = status.get('sentence_schedule_path') or status.get('frame_schedule_path')

      if schedule_path:
        try:
          schedule_file = Path(schedule_path)
          if not schedule_file.exists():
            st.warning(f'⚠️ 스케줄 파일을 찾을 수 없습니다: {schedule_path}')
          else:
            with open(schedule_file, 'r', encoding='utf-8') as f:
              schedule_data = json.load(f)

            schedules = schedule_data.get('sentence_schedules', [])
            st.write(f'**총 {len(schedules)}개 문장 스케줄**')

            # 요약 테이블
            table_data = []
            total_duration = 0.0
            for idx, sched in enumerate(schedules):
              dur = sched.get('duration', 0)
              total_duration += dur
              prompt = sched.get('image_prompt', '')[:50]
              table_data.append({
                '번호': idx + 1,
                '길이(초)': f'{dur:.1f}',
                '이미지 프롬프트': f'{prompt}...' if len(sched.get('image_prompt', '')) > 50 else prompt,
              })

            st.dataframe(table_data, use_container_width=True, hide_index=True)
            st.write(f'**총 재생 시간: {total_duration:.1f}초**')

        except Exception as e:
          st.error(f'스케줄 데이터 로드 오류: {e}')
      elif status.get('error_log', {}).get('step3'):
        st.error(f"❌ Step 3 오류: {status['error_log']['step3']}")
      else:
        st.info('Step 3을 실행하면 결과가 표시됩니다')

      if st.button('▶️ Step 3 실행', key='step3_run'):
        try:
          resp = requests.post(
            f'{st.session_state.api_base}/steps/step3',
            json={'task_id': st.session_state.task_id, 'use_cache': False, 'invalidate_downstream': True}
          )
          if resp.status_code == 200:
            st.session_state.step_running = 'step3'
            st.rerun()
          else:
            error_detail = resp.json().get('detail', resp.text) if resp.headers.get('content-type', '').startswith('application/json') else resp.text
            st.error(f'Step 3 실행 실패: {error_detail}')
        except Exception as e:
          st.error(f'Step 3 실행 오류: {e}')

      if st.session_state.step_running == 'step3':
        @st.fragment(run_every=2)
        def polling_step3():
          status = fetch_task_status(st.session_state.task_id)
          if status:
            st.info(f'⏳ {status["status_message"]}')
            if status['error_log'].get('step3'):
              st.error(f"❌ 오류: {status['error_log']['step3']}")

            if status['status'] == 'completed':
              st.session_state.step_running = None
              st.rerun(scope="app")
            elif status['status'] == 'failed':
              st.session_state.step_running = None
              st.rerun(scope="app")

        polling_step3()

    # ========================================================================
    # Tab 4: 정지이미지 생성
    # ========================================================================
    with tabs[4]:
      st.subheader('🎨 정지이미지 생성')

      if status.get('still_image_paths'):
        st.write(f'**총 {len(status["still_image_paths"])}개 이미지 생성 완료**')
        cols = st.columns(3)
        for idx, img_path in enumerate(status['still_image_paths']):
          with cols[idx % 3]:
            try:
              img = Image.open(img_path)
              st.image(img, use_container_width=True)
              st.caption(f'문장 {idx + 1}')
            except Exception as e:
              st.error(f'이미지 로드 오류: {e}')

        if st.button('🔍 이미지 검증 실행', key='step4_qa'):
          st.info('💬 Claude에게 "이미지 검증해줘"라고 입력하면 quality-assurance-agent가 대본-이미지 정합성을 검증합니다.')

      elif status.get('error_log', {}).get('step4'):
        st.error(f"❌ Step 4 오류: {status['error_log']['step4']}")
      else:
        st.info('Step 4를 실행하면 결과가 표시됩니다')

      if st.button('▶️ Step 4 실행', key='step4_run'):
        try:
          resp = requests.post(
            f'{st.session_state.api_base}/steps/step4',
            json={'task_id': st.session_state.task_id, 'use_cache': False, 'invalidate_downstream': True}
          )
          if resp.status_code == 200:
            st.session_state.step_running = 'step4'
            st.rerun()
          else:
            error_detail = resp.json().get('detail', resp.text) if resp.headers.get('content-type', '').startswith('application/json') else resp.text
            st.error(f'Step 4 실행 실패: {error_detail}')
        except Exception as e:
          st.error(f'Step 4 실행 오류: {e}')

      if st.session_state.step_running == 'step4':
        @st.fragment(run_every=2)
        def polling_step4():
          status = fetch_task_status(st.session_state.task_id)
          if status:
            st.info(f'⏳ {status["status_message"]}')
            if status['error_log'].get('step4'):
              st.error(f"❌ 오류: {status['error_log']['step4']}")

            if status['status'] == 'completed':
              st.session_state.step_running = None
              st.rerun(scope="app")
            elif status['status'] == 'failed':
              st.session_state.step_running = None
              st.rerun(scope="app")

        polling_step4()

    # ========================================================================
    # Tab 5: BGM 생성
    # ========================================================================
    with tabs[5]:
      st.subheader('🎵 BGM 생성 (Stable Audio)')

      if status.get('bgm_path'):
        try:
          with open(status['bgm_path'], 'rb') as f:
            st.audio(f.read(), format='audio/wav')
          st.caption(f'BGM 파일: {Path(status["bgm_path"]).name}')
        except Exception as e:
          st.error(f'BGM 로드 오류: {e}')
      elif status.get('error_log', {}).get('step5'):
        st.error(f"❌ Step 5 오류: {status['error_log']['step5']}")
      else:
        st.info('Step 5를 실행하면 BGM이 생성됩니다')

      if st.button('▶️ Step 5 실행', key='step5_run'):
        try:
          resp = requests.post(
            f'{st.session_state.api_base}/steps/step5',
            json={'task_id': st.session_state.task_id, 'use_cache': False, 'invalidate_downstream': True}
          )
          if resp.status_code == 200:
            st.session_state.step_running = 'step5'
            st.rerun()
          else:
            error_detail = resp.json().get('detail', resp.text) if resp.headers.get('content-type', '').startswith('application/json') else resp.text
            st.error(f'Step 5 실행 실패: {error_detail}')
        except Exception as e:
          st.error(f'Step 5 실행 오류: {e}')

      if st.session_state.step_running == 'step5':
        @st.fragment(run_every=2)
        def polling_step5():
          status = fetch_task_status(st.session_state.task_id)
          if status:
            st.info(f'⏳ {status["status_message"]}')
            if status['error_log'].get('step5'):
              st.error(f"❌ 오류: {status['error_log']['step5']}")

            if status['status'] == 'completed':
              st.session_state.step_running = None
              st.rerun(scope="app")
            elif status['status'] == 'failed':
              st.session_state.step_running = None
              st.rerun(scope="app")

        polling_step5()

    # ========================================================================
    # Tab 6: 영상 병합
    # ========================================================================
    with tabs[6]:
      st.subheader('🎬 최종 영상 (1080×1920)')

      if status['video_path']:
        try:
          video_path = Path(status['video_path'])
          video_filename = video_path.name
          poem_id = status.get('poem_id', '')
          if poem_id:
            video_url = f"{st.session_state.api_base}/cache/{poem_id}/video/{video_filename}"
          else:
            video_url = f"{st.session_state.api_base}/cache/video/{video_filename}"
          st.video(video_url)

          # 다운로드 버튼
          with open(status['video_path'], 'rb') as f:
            st.download_button(
              label='⬇️ 영상 다운로드',
              data=f.read(),
              file_name=video_filename,
              mime='video/mp4'
            )
        except Exception as e:
          st.error(f'영상 로드 오류: {e}')
      elif status.get('error_log', {}).get('step6'):
        st.error(f"❌ Step 6 오류: {status['error_log']['step6']}")
      else:
        st.info('Step 6를 실행하면 결과가 표시됩니다')

      if st.button('▶️ Step 6 실행', key='step6_run'):
        try:
          resp = requests.post(
            f'{st.session_state.api_base}/steps/step6',
            json={'task_id': st.session_state.task_id, 'use_cache': False, 'invalidate_downstream': True}
          )
          if resp.status_code == 200:
            st.session_state.step_running = 'step6'
            st.rerun()
          else:
            error_detail = resp.json().get('detail', resp.text) if resp.headers.get('content-type', '').startswith('application/json') else resp.text
            st.error(f'Step 6 실행 실패: {error_detail}')
        except Exception as e:
          st.error(f'Step 6 실행 오류: {e}')

      if st.session_state.step_running == 'step6':
        @st.fragment(run_every=2)
        def polling_step6():
          status = fetch_task_status(st.session_state.task_id)
          if status:
            st.info(f'⏳ {status["status_message"]}')
            if status['error_log'].get('step6'):
              st.error(f"❌ 오류: {status['error_log']['step6']}")

            if status['status'] == 'completed':
              st.session_state.step_running = None
              st.rerun(scope="app")
            elif status['status'] == 'failed':
              st.session_state.step_running = None
              st.rerun(scope="app")

        polling_step6()
