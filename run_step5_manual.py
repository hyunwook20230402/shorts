"""
Step 5 Manual Runner - 기존 Step 4 clips + Step 2 audio를 연결
"""
import os
import sys
import logging
from pathlib import Path
from step5_video import compose_final_video

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('step5_manual.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def main():
    logger.info('=' * 70)
    logger.info('Step 5: Manual Run - AnimateDiff clips + ElevenLabs audio')
    logger.info('=' * 70)

    # Step 4 clips (hash: 8a1ea3af)
    clip_paths = sorted([
        str(p) for p in Path('cache/step4').glob('8a1ea3af_*_clip.mp4')
    ])

    logger.info(f'Step 4 clips: {len(clip_paths)}')
    for p in clip_paths:
        logger.info(f'  - {Path(p).name}')

    # Step 2 audio/alignment (most recent for each scene index)
    # Scene 0: bf1e3689_00
    # Scene 1: 61a4713d_01
    # Scene 2: 259c40b6_02
    audio_paths = [
        'cache/step2/bf1e3689_00_audio.mp3',
        'cache/step2/61a4713d_01_audio.mp3',
        'cache/step2/259c40b6_02_audio.mp3',
    ]

    alignment_paths = [
        'cache/step2/bf1e3689_00_alignment.json',
        'cache/step2/61a4713d_01_alignment.json',
        'cache/step2/259c40b6_02_alignment.json',
    ]

    # Verify files exist
    for p in clip_paths + audio_paths + alignment_paths:
        if not Path(p).exists():
            logger.error(f'File not found: {p}')
            return 1

    logger.info(f'Step 2 audio: {len(audio_paths)}')
    for p in audio_paths:
        logger.info(f'  - {Path(p).name}')

    logger.info(f'Step 2 alignment: {len(alignment_paths)}')
    for p in alignment_paths:
        logger.info(f'  - {Path(p).name}')

    try:
        logger.info('\n최종 영상 합성 실행 중...')
        output_path = compose_final_video(clip_paths, audio_paths, alignment_paths, use_cache=False)

        if Path(output_path).exists():
            size_mb = Path(output_path).stat().st_size / (1024 * 1024)
            logger.info(f'\nSuccess: {Path(output_path).name}')
            logger.info(f'File size: {size_mb:.1f}MB')
            logger.info('\n' + '=' * 70)
            logger.info('Step 5 Complete')
            logger.info('=' * 70)
            return 0
        else:
            logger.error(f'Output file not created: {output_path}')
            return 1

    except Exception as e:
        logger.error(f'Step 5 failed: {e}', exc_info=True)
        return 1

if __name__ == '__main__':
    sys.exit(main())
