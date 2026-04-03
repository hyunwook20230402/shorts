"""
테마 설정 모듈 — 모든 Step이 import하는 단일 소스.
학술 기반 13개 고전시가 주제 분류 체계 + Step별 파라미터.
"""

# 13개 테마 카탈로그
THEME_CATALOG: dict[str, dict[str, str]] = {
  "A": {"ko": "강호자연", "en": "gangho_nature", "desc": "자연 속 한가로운 삶, 풍류"},
  "B": {"ko": "연군", "en": "yearning_for_king", "desc": "임금에 대한 그리움 (유배/파직 후)"},
  "C": {"ko": "충절/우국", "en": "loyalty_patriotism", "desc": "변함없는 충성, 나라 걱정"},
  "D": {"ko": "유배", "en": "exile", "desc": "유배지의 한과 억울함"},
  "E": {"ko": "애정", "en": "love", "desc": "남녀 간 사랑, 상사의 정"},
  "F": {"ko": "이별의 정한", "en": "farewell_sorrow", "desc": "이별의 슬픔, 기다림, 재회 기원"},
  "G": {"ko": "교훈/도학", "en": "moral_teaching", "desc": "유교 윤리 덕목, 교화"},
  "H": {"ko": "풍자/해학", "en": "satire_humor", "desc": "사회 모순 비판, 웃음"},
  "I": {"ko": "무상/탄로", "en": "impermanence", "desc": "세월의 덧없음, 늙음 한탄"},
  "J": {"ko": "종교/신앙", "en": "religion", "desc": "불교 신앙, 극락왕생 기원"},
  "K": {"ko": "기행", "en": "travel", "desc": "여행, 풍경 감상"},
  "L": {"ko": "노동/세시풍속", "en": "labor_customs", "desc": "농사, 세시풍속, 민속"},
  "M": {"ko": "건국 송축", "en": "founding_celebration", "desc": "건국의 위업, 송축"},
}

DEFAULT_THEME = "A"  # fallback: 강호자연 (가장 중립적)


# ─── Step 1: 테마 분류 LLM 프롬프트용 ───

def get_theme_classification_prompt() -> str:
  """Step 1 LLM 시스템 프롬프트에 삽입할 테마 분류 지시문 (이중 테마)"""
  lines = ["이 시의 테마/주제를 분석하여 다음 13개 카탈로그 중에서 선택하세요:"]
  for code, info in THEME_CATALOG.items():
    lines.append(f"  {code}. {info['ko']} — {info['desc']}")

  lines.append("")
  lines.append("[중첩 해소 및 복합 주제 규칙]")
  lines.append("- 고전 시가는 표면적 화자(예: 이별한 여성)와 이면적 의도(예: 유배된 신하)가 다른 경우가 많습니다.")
  lines.append("- 'primary_theme': 시의 궁극적 핵심 진심(해설/나레이션용).")
  lines.append("- 'surface_theme': 표면적 시적 상황(이미지 생성용). 같을 경우 동일 코드 사용.")
  lines.append("- 연군 vs 애정: 실제 작가가 임금을 그리워하는 내용이라도, 시적 화자가 여성이면 primary=B, surface=E 또는 F")
  lines.append("- 충절 vs 연군: 충성 의지이면 C, 임금 그리움이면 B")
  lines.append("- 이별 vs 애정: 이별/기다림이면 F, 사랑 자체면 E")
  lines.append("- 유배 vs 연군: 유배 고난이면 D, 임금 그리움이면 B")
  lines.append("- 강호자연 vs 교훈: 자연미면 A, 윤리면 G")
  lines.append("")
  lines.append("응답 JSON 최상위에 다음 4개 필드를 반드시 포함하세요:")
  lines.append('"primary_theme": "코드(A~M)", "primary_theme_en": "영문키",')
  lines.append('"surface_theme": "코드(A~M)", "surface_theme_en": "영문키"')

  return "\n".join(lines)


# ─── Step 1: 테마별 이미지 프롬프트 스타일 가이드 ───

THEME_IMAGE_STYLE_GUIDE: dict[str, str] = {
  "A": "emphasize shanshui landscape composition, cool blue-green palette, wide establishing shots, misty mountains, serene water",
  "B": "muted palace tones, moonlit haze, solitary figure gazing at distant palace, melancholic atmosphere",
  "C": "dramatic low-angle composition, dark ominous sky, heroic figure stance, blood-red accents, martial energy",
  "D": "cold desolate landscape, barren trees, isolated figure, gray-blue palette, prison or remote wilderness",
  "E": "warm soft-focus lighting, intimate two-figure composition, cherry blossoms or moonlight, romantic atmosphere",
  "F": "cool blue-gray tones, fading light, parting scene, river or road stretching into distance, bittersweet mood",
  "G": "neutral scholarly tones, clean structured composition, study room or lecture hall, dignified atmosphere",
  "H": "vivid saturated folk colors, exaggerated expressions, marketplace or village scene, comedic energy",
  "I": "desaturated earthy palette, falling petals or leaves, dissolving edges, vanitas symbolism, weary figure",
  "J": "golden temple light, incense haze, Buddhist imagery, lotus flowers, sacred meditative atmosphere",
  "K": "scenic panoramic vista, clear sky, traveler on mountain path, adventurous dynamic composition",
  "L": "warm earthy harvest tones, communal farming scene, rhythmic movement, folk festival atmosphere",
  "M": "majestic gold and red, royal court setting, celebratory procession, grand scale composition",
}


# ─── Step 2: TTS 파라미터 ───

THEME_TTS_PARAMS: dict[str, dict[str, str]] = {
  "A": {"rate": "-15%", "pitch": "-1Hz"},   # 느리고 여유
  "B": {"rate": "-10%", "pitch": "-2Hz"},   # 그리움
  "C": {"rate": "-5%",  "pitch": "+2Hz"},   # 비장
  "D": {"rate": "-20%", "pitch": "-3Hz"},   # 무겁고 슬픈
  "E": {"rate": "-5%",  "pitch": "+1Hz"},   # 따뜻
  "F": {"rate": "-15%", "pitch": "-2Hz"},   # 애잔
  "G": {"rate": "+0%",  "pitch": "+0Hz"},   # 차분 권위
  "H": {"rate": "+10%", "pitch": "+3Hz"},   # 경쾌
  "I": {"rate": "-20%", "pitch": "-2Hz"},   # 느리고 지친
  "J": {"rate": "-10%", "pitch": "-1Hz"},   # 경건
  "K": {"rate": "+5%",  "pitch": "+1Hz"},   # 활기
  "L": {"rate": "+5%",  "pitch": "+2Hz"},   # 리듬감
  "M": {"rate": "+0%",  "pitch": "+3Hz"},   # 장엄
}
DEFAULT_TTS_PARAMS = {"rate": "+0%", "pitch": "+0Hz"}


# ─── Step 3: 씬 전환 패딩 (초) ───

THEME_TRANSITION_PADDING: dict[str, float] = {
  "A": 0.5,  # 여유로운 여운
  "D": 0.5,  # 무거운 여운
  "I": 0.5,  # 무거운 여운
  "H": 0.2,  # 빠른 템포
  "K": 0.2,  # 활기찬 전환
  "L": 0.2,  # 활기찬 전환
}
DEFAULT_TRANSITION_PADDING = 0.3


# ─── Step 4: LoRA/CFG + 색감 프롬프트 ───

THEME_IMAGE_PARAMS: dict[str, dict] = {
  "A": {"lora": 0.9, "cfg": 7.0, "color": "blue-green tones, misty atmosphere, sage colors", "neg_extra": "urban, modern city"},
  "B": {"lora": 0.85, "cfg": 7.5, "color": "muted palace tones, moonlit haze", "neg_extra": "cheerful, bright colors"},
  "C": {"lora": 0.7, "cfg": 8.5, "color": "deep crimson accents, dark dramatic sky", "neg_extra": "bright cheerful colors"},
  "D": {"lora": 0.85, "cfg": 7.5, "color": "cold desolate gray-blue, barren landscape", "neg_extra": "warm, lush, green"},
  "E": {"lora": 0.75, "cfg": 7.0, "color": "warm rose tones, soft pink light", "neg_extra": "cold harsh lighting"},
  "F": {"lora": 0.8, "cfg": 7.0, "color": "cool blue-gray tones, fading light", "neg_extra": "vibrant warm colors"},
  "G": {"lora": 0.8, "cfg": 8.0, "color": "neutral scholarly tones, clean composition", "neg_extra": "chaotic, messy"},
  "H": {"lora": 0.6, "cfg": 6.5, "color": "vivid saturated folk colors", "neg_extra": "serious, somber, dark"},
  "I": {"lora": 0.85, "cfg": 7.0, "color": "desaturated earthy palette, autumn decay", "neg_extra": "vivid saturated colors"},
  "J": {"lora": 0.8, "cfg": 7.0, "color": "golden temple light, incense haze", "neg_extra": "secular, modern"},
  "K": {"lora": 0.8, "cfg": 7.5, "color": "scenic panoramic colors, clear sky", "neg_extra": "indoor, cramped"},
  "L": {"lora": 0.7, "cfg": 7.0, "color": "warm earthy harvest tones", "neg_extra": "cold, winter"},
  "M": {"lora": 0.8, "cfg": 8.0, "color": "majestic gold and red, royal court", "neg_extra": "humble, poor"},
}
DEFAULT_IMAGE_PARAMS = {"lora": 0.8, "cfg": 7.5, "color": "", "neg_extra": ""}


# ─── Step 5: BGM 악기/분위기 힌트 ───

THEME_BGM_HINTS: dict[str, dict[str, str]] = {
  "A": {"instruments": "gayageum, daegeum, bamboo flute", "mood": "serene, flowing, nature ambient", "tempo": "60-80 BPM"},
  "B": {"instruments": "haegeum, gayageum", "mood": "melancholic, longing, court music", "tempo": "50-70 BPM"},
  "C": {"instruments": "buk drum, janggu, brass", "mood": "heroic, solemn, martial", "tempo": "80-100 BPM"},
  "D": {"instruments": "solo haegeum, sparse percussion", "mood": "desolate, lonely, sorrowful", "tempo": "40-60 BPM"},
  "E": {"instruments": "gayageum, soft flute", "mood": "romantic, tender, gentle", "tempo": "60-80 BPM"},
  "F": {"instruments": "solo daegeum, subtle strings", "mood": "wistful, fading, bittersweet", "tempo": "50-70 BPM"},
  "G": {"instruments": "geomungo, temple bell", "mood": "dignified, scholarly, composed", "tempo": "60-80 BPM"},
  "H": {"instruments": "piri, janggu, lively percussion", "mood": "playful, satirical, witty", "tempo": "100-120 BPM"},
  "I": {"instruments": "geomungo, wind sounds", "mood": "ephemeral, fading, contemplative", "tempo": "40-60 BPM"},
  "J": {"instruments": "moktak, temple bell, chant", "mood": "sacred, meditative, ethereal", "tempo": "40-60 BPM"},
  "K": {"instruments": "mixed ensemble, nature sounds", "mood": "adventurous, scenic, dynamic", "tempo": "80-100 BPM"},
  "L": {"instruments": "janggu, folk instruments", "mood": "rhythmic, communal, festive", "tempo": "100-120 BPM"},
  "M": {"instruments": "full court orchestra", "mood": "majestic, celebratory, grand", "tempo": "80-100 BPM"},
}


# ─── Step 6: 자막 스타일 + BGM 볼륨 ───

THEME_SUBTITLE_STYLE: dict[str, dict] = {
  "A": {"color": (20, 80, 60), "size": 44, "opacity": 0.85},    # 다크 그린
  "B": {"color": (60, 40, 80), "size": 46, "opacity": 0.9},     # 짙은 보라
  "C": {"color": (180, 20, 20), "size": 52, "opacity": 1.0},    # 딥 레드
  "D": {"color": (70, 70, 90), "size": 44, "opacity": 0.8},     # 회청
  "E": {"color": (120, 40, 80), "size": 46, "opacity": 0.9},    # 로즈
  "F": {"color": (80, 80, 110), "size": 44, "opacity": 0.85},   # 블루 그레이
  "G": {"color": (40, 40, 40), "size": 48, "opacity": 1.0},     # 진한 검정
  "H": {"color": (60, 60, 20), "size": 50, "opacity": 1.0},     # 올리브
  "I": {"color": (100, 100, 100), "size": 44, "opacity": 0.7},  # 회색
  "J": {"color": (120, 80, 20), "size": 46, "opacity": 0.9},    # 골드
  "K": {"color": (30, 70, 30), "size": 46, "opacity": 0.9},     # 그린
  "L": {"color": (100, 60, 20), "size": 48, "opacity": 1.0},    # 흙색
  "M": {"color": (150, 30, 30), "size": 52, "opacity": 1.0},    # 레드
}
DEFAULT_SUBTITLE_STYLE = {"color": (0, 0, 0), "size": 48, "opacity": 1.0}

THEME_BGM_VOLUME: dict[str, dict[str, float]] = {
  "A": {"narration": 0.8, "bgm": 0.4},    # BGM 높게 (자연 분위기)
  "B": {"narration": 0.9, "bgm": 0.3},    # 균형
  "C": {"narration": 1.0, "bgm": 0.2},    # 나레이션 우선
  "D": {"narration": 0.85, "bgm": 0.35},  # 약간 BGM
  "E": {"narration": 0.9, "bgm": 0.35},   # 로맨틱 분위기
  "H": {"narration": 1.0, "bgm": 0.15},   # 나레이션 최우선 (해학)
  "I": {"narration": 0.7, "bgm": 0.45},   # BGM 우세 (몽환)
  "J": {"narration": 0.8, "bgm": 0.4},    # 경건한 BGM
}
DEFAULT_BGM_VOLUME = {"narration": 0.9, "bgm": 0.25}


# ─── 헬퍼 함수 ───

def get_image_style_guide(theme_code: str) -> str:
  """surface_theme 코드 → 이미지 스타일 가이드 문자열"""
  return THEME_IMAGE_STYLE_GUIDE.get(theme_code, THEME_IMAGE_STYLE_GUIDE[DEFAULT_THEME])


def get_theme_info(theme_code: str) -> dict[str, str]:
  """테마 코드 → 카탈로그 정보 (fallback: DEFAULT_THEME)"""
  return THEME_CATALOG.get(theme_code, THEME_CATALOG[DEFAULT_THEME])


def get_tts_params(theme_code: str) -> dict[str, str]:
  """테마 코드 → TTS rate/pitch"""
  return THEME_TTS_PARAMS.get(theme_code, DEFAULT_TTS_PARAMS)


def get_transition_padding(theme_code: str) -> float:
  """테마 코드 → 전환 패딩 (초)"""
  return THEME_TRANSITION_PADDING.get(theme_code, DEFAULT_TRANSITION_PADDING)


def get_image_params(theme_code: str) -> dict:
  """테마 코드 → LoRA/CFG/색감"""
  return THEME_IMAGE_PARAMS.get(theme_code, DEFAULT_IMAGE_PARAMS)


def get_bgm_hints(theme_code: str) -> dict[str, str]:
  """테마 코드 → BGM 악기/분위기/템포"""
  return THEME_BGM_HINTS.get(theme_code, THEME_BGM_HINTS[DEFAULT_THEME])


def get_subtitle_style(theme_code: str) -> dict:
  """테마 코드 → 자막 color/size/opacity"""
  return THEME_SUBTITLE_STYLE.get(theme_code, DEFAULT_SUBTITLE_STYLE)


def get_bgm_volume(theme_code: str) -> dict[str, float]:
  """테마 코드 → 나레이션/BGM 볼륨"""
  return THEME_BGM_VOLUME.get(theme_code, DEFAULT_BGM_VOLUME)
