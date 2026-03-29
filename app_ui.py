import json
import logging
import requests
import streamlit as st
import time
from pathlib import Path
from PIL import Image

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
  st.session_state.api_base = 'http://localhost:8000/api/v1'

if 'task_id' not in st.session_state:
  st.session_state.task_id = None

if 'pipeline_running' not in st.session_state:
  st.session_state.pipeline_running = False


# 헬퍼 함수
def fetch_task_status(task_id: str) -> dict | None:
  """작업 상태 조회"""
  try:
    resp = requests.get(f'{st.session_state.api_base}/tasks/{task_id}', timeout=5)
    if resp.status_code == 200:
      return resp.json()
  except Exception as e:
    logger.error(f'상태 조회 오류: {e}')
  return None


def upload_image(file) -> str | None:
  """이미지 업로드"""
  try:
    resp = requests.post(
      f'{st.session_state.api_base}/upload',
      files={'file': (file.name, file, 'image/jpeg')}
    )
    if resp.status_code == 200:
      data = resp.json()
      return data['task_id']
  except Exception as e:
    st.error(f'업로드 오류: {e}')
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
  last_step = -1

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
        st.progress((current_step + 1) / 6, f"Step {current_step}")
        st.write(status['status_message'])
      with col2:
        st.write(f'⏱️ {int(elapsed)}초')

    # Step별 에러 표시
    if status['error_log']:
      st.error(f"❌ 오류: {status['error_log']}")

    # 완료 또는 실패
    if status['status'] in ('completed', 'failed'):
      return status

    time.sleep(2)


# ============================================================================
# 사이드바
# ============================================================================

with st.sidebar:
  st.title('⚙️ 설정')

  # API 서버 주소
  api_base = st.text_input(
    'FastAPI 서버 주소',
    value=st.session_state.api_base,
    help='기본값: http://localhost:8000/api/v1'
  )
  st.session_state.api_base = api_base

  st.divider()

  st.title('📤 이미지 업로드')
  uploaded_file = st.file_uploader(
    '고전시가 이미지 선택',
    type=['png', 'jpg', 'jpeg'],
    help='OCR로 인식할 고전시가 이미지'
  )

  if uploaded_file:
    if st.button('✅ 업로드', use_container_width=True):
      with st.spinner('업로드 중...'):
        task_id = upload_image(uploaded_file)
        if task_id:
          st.session_state.task_id = task_id
          st.success(f'✅ 업로드 완료!\nTask ID: {task_id[:8]}...')
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
      st.write(f"**Step**: {status['current_step']}/5")


# ============================================================================
# 메인 영역 - 탭
# ============================================================================

if not st.session_state.task_id:
  st.title('📺 고전시가 → YouTube Shorts 자동 생성')
  st.info('사이드바에서 이미지를 업로드하여 시작하세요.')
else:
  status = fetch_task_status(st.session_state.task_id)

  if not status:
    st.error('작업 정보를 불러올 수 없습니다')
  else:
    st.title('📺 고전시가 → YouTube Shorts 자동 생성')

    tabs = st.tabs(['📸 Step 0: OCR', '📝 Step 1: NLP', '🎨 Step 2: 이미지', '🔊 Step 3: 오디오', '📄 Step 4: 자막', '🎬 Step 5: 영상'])

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
            st.image(img, use_column_width=True)
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

      if st.button('🔄 Step 0 재실행', key='step0_rerun'):
        with st.spinner('Step 0 실행 중...'):
          resp = requests.post(
            f'{st.session_state.api_base}/steps/step0',
            json={'task_id': st.session_state.task_id, 'use_cache': False, 'invalidate_downstream': True}
          )
          if resp.status_code == 200:
            st.info('Step 0 재실행 시작됨')
            st.rerun()

    # ========================================================================
    # Tab 1: NLP
    # ========================================================================
    with tabs[1]:
      st.subheader('📝 NLP 처리 (번역, 씬 분할)')

      if status['nlp_cache_path']:
        try:
          with open(status['nlp_cache_path'], 'r', encoding='utf-8') as f:
            nlp_data = json.load(f)

          scenes = nlp_data.get('modern_script_data', [])
          st.write(f'**총 {len(scenes)}개 씬**')

          for idx, scene in enumerate(scenes):
            with st.expander(f"씬 {idx + 1}: {scene.get('narration', '...')[:50]}..."):
              col1, col2 = st.columns(2)

              with col1:
                st.write('**원문**')
                st.text(scene.get('original_text', ''))

                st.write('**현대어 번역**')
                st.text(scene.get('modern_text', ''))

              with col2:
                st.write('**나레이션**')
                st.text(scene.get('narration', ''))

                st.write('**감정**')
                st.text(scene.get('emotion', ''))

                st.write('**배경**')
                st.text(scene.get('background', ''))

        except Exception as e:
          st.error(f'NLP 데이터 로드 오류: {e}')
      else:
        st.info('Step 1을 실행하면 결과가 표시됩니다')

      if st.button('🔄 Step 1 재실행', key='step1_rerun'):
        with st.spinner('Step 1 실행 중...'):
          resp = requests.post(
            f'{st.session_state.api_base}/steps/step1',
            json={'task_id': st.session_state.task_id, 'use_cache': False, 'invalidate_downstream': True}
          )
          if resp.status_code == 200:
            st.info('Step 1 재실행 시작됨')

    # ========================================================================
    # Tab 2: 이미지
    # ========================================================================
    with tabs[2]:
      st.subheader('🎨 생성 이미지 (512×912)')

      if status['image_paths']:
        cols = st.columns(3)
        for idx, img_path in enumerate(status['image_paths']):
          with cols[idx % 3]:
            try:
              img = Image.open(img_path)
              st.image(img, use_column_width=True)
              st.caption(f"씬 {idx + 1}")
            except Exception as e:
              st.error(f'이미지 로드 오류: {e}')
      else:
        st.info('Step 2를 실행하면 결과가 표시됩니다')

      if st.button('🔄 Step 2 재실행', key='step2_rerun'):
        with st.spinner('Step 2 실행 중... (1~30분 소요)'):
          resp = requests.post(
            f'{st.session_state.api_base}/steps/step2',
            json={'task_id': st.session_state.task_id, 'use_cache': False, 'invalidate_downstream': True}
          )
          if resp.status_code == 200:
            st.info('Step 2 재실행 시작됨')

    # ========================================================================
    # Tab 3: 오디오
    # ========================================================================
    with tabs[3]:
      st.subheader('🔊 생성 오디오 (TTS)')

      if status['audio_paths']:
        for idx, audio_path in enumerate(status['audio_paths']):
          try:
            st.write(f'**씬 {idx + 1}**')
            with open(audio_path, 'rb') as f:
              st.audio(f.read(), format='audio/mp3')
          except Exception as e:
            st.error(f'오디오 로드 오류: {e}')
      else:
        st.info('Step 3을 실행하면 결과가 표시됩니다')

      if st.button('🔄 Step 3 재실행', key='step3_rerun'):
        with st.spinner('Step 3 실행 중...'):
          resp = requests.post(
            f'{st.session_state.api_base}/steps/step3',
            json={'task_id': st.session_state.task_id, 'use_cache': False, 'invalidate_downstream': True}
          )
          if resp.status_code == 200:
            st.info('Step 3 재실행 시작됨')

    # ========================================================================
    # Tab 4: 자막
    # ========================================================================
    with tabs[4]:
      st.subheader('📄 SRT 자막')

      if status['subtitle_path']:
        try:
          with open(status['subtitle_path'], 'r', encoding='utf-8') as f:
            srt_content = f.read()
          st.code(srt_content, language='srt')
        except Exception as e:
          st.error(f'자막 로드 오류: {e}')
      else:
        st.info('Step 4를 실행하면 결과가 표시됩니다')

      if st.button('🔄 Step 4 재실행', key='step4_rerun'):
        with st.spinner('Step 4 실행 중...'):
          resp = requests.post(
            f'{st.session_state.api_base}/steps/step4',
            json={'task_id': st.session_state.task_id, 'use_cache': False, 'invalidate_downstream': True}
          )
          if resp.status_code == 200:
            st.info('Step 4 재실행 시작됨')

    # ========================================================================
    # Tab 5: 영상
    # ========================================================================
    with tabs[5]:
      st.subheader('🎬 최종 영상 (1080×1920)')

      if status['video_path']:
        try:
          video_filename = Path(status['video_path']).name
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
      else:
        st.info('Step 5를 실행하면 결과가 표시됩니다')

      if st.button('🔄 Step 5 재실행', key='step5_rerun'):
        with st.spinner('Step 5 실행 중... (인코딩, 1~2분 소요)'):
          resp = requests.post(
            f'{st.session_state.api_base}/steps/step5',
            json={'task_id': st.session_state.task_id, 'use_cache': False, 'invalidate_downstream': True}
          )
          if resp.status_code == 200:
            st.info('Step 5 재실행 시작됨')
