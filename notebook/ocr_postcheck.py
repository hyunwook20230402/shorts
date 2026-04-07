"""
OCR 후처리 검증 — 수동 교정이 필요한 의심 행 감지

step0_ocr.py __main__ 및 Streamlit UI에서 호출.
"""

import re


def detect_suspicious_lines(text: str) -> list[dict]:
  """
  OCR 텍스트에서 수동 검토가 필요한 의심 행을 감지.

  반환: [{'line_no': int, 'text': str, 'reason': str}, ...]
  """
  lines = text.splitlines()
  issues = []

  for i, line in enumerate(lines):
    stripped = line.strip()
    if not stripped:
      continue

    # 패턴 1: 한자 병기 포함 단어 1개만 있는 짧은 행
    # 예: "경경(耿耿)", "도화(桃花)*"
    # → 볼드 강조 단어가 행에서 분리된 오인식 가능성
    if re.fullmatch(r'[가-힣]+\([^\)]+\)\*?', stripped):
      issues.append({
        'line_no': i + 1,
        'text': stripped,
        'reason': '단독 한자 병기 단어 — 앞/뒤 행과 합쳐진 것일 수 있음',
      })
      continue

    # 패턴 2: 한자 병기를 제거했을 때 순수 한글이 3글자 이하인 초단문 행
    # 예: "아" → 오인식, "넋" → 행 분리 가능성
    plain = re.sub(r'\([^\)]+\)', '', stripped)  # 한자 병기 제거
    plain = re.sub(r'[*\s]', '', plain)           # * 기호, 공백 제거
    if 0 < len(plain) <= 3:
      issues.append({
        'line_no': i + 1,
        'text': stripped,
        'reason': f'매우 짧은 행({len(plain)}자) — 행 분리 오류 가능성',
      })
      continue

    # 패턴 3: 행 시작이 한자 병기 단어(2글자+) + 나머지 텍스트 (이전 행에서 밀려온 의심)
    # 예: "경경(耿耿) 서창(西窓)을 열어 하니" → "경경(耿耿)"이 이전 행 소속일 수 있음
    # 1글자 한자 병기(정(情), 소(沼) 등)는 관용적 행 시작이므로 제외
    hanja_start = re.match(r'^([가-힣]{2,}\([^\)]+\)\*?)\s+(.+)', stripped)
    if hanja_start and i > 0:
      prev = lines[i - 1].strip()
      if prev:
        issues.append({
          'line_no': i + 1,
          'text': stripped,
          'reason': (
            f'행 시작 "{hanja_start.group(1)}"이 이전 행에서 밀려왔을 가능성'
            ' — 이전 행과 합쳐야 할 수 있음'
          ),
        })

  return issues


def format_warnings(issues: list[dict], ocr_path: str | None = None) -> str:
  """감지 결과를 사람이 읽기 쉬운 경고 문자열로 포맷"""
  if not issues:
    return ''

  lines = ['⚠️  수동 검토 필요 행:']
  for issue in issues:
    lines.append(f"  [{issue['line_no']}행] '{issue['text']}' — {issue['reason']}")

  if ocr_path:
    lines.append(f'\n→ {ocr_path} 를 직접 수정 후 Step 1을 실행하세요.')

  return '\n'.join(lines)
