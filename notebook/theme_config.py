"""
테마 설정 모듈 — 모든 Step이 import하는 단일 소스.
학술 기반 13개 고전시가 주제 분류 체계 + Step별 파라미터.
"""

# 13개 테마 카탈로그
THEME_CATALOG: dict[str, dict[str, str]] = {
  "A": {"ko": "강호자연", "en": "gangho_nature", "desc": "자연 속 한가로운 삶, 풍류"},
  "B": {"ko": "연군", "en": "yearning_for_king", "desc": "임금에 대한 그리움, 잊혀짐에 대한 원망 (유배/파직 후)"},
  "C": {"ko": "충절/우국", "en": "loyalty_patriotism", "desc": "변함없는 충성, 나라 걱정"},
  "D": {"ko": "유배", "en": "exile", "desc": "유배지의 한과 억울함"},
  "E": {"ko": "애정", "en": "love", "desc": "남녀 간 사랑, 상사의 정"},
  "F": {"ko": "이별의 정한", "en": "farewell_sorrow", "desc": "이별의 슬픔, 배신에 대한 원망, 기다림, 재회 기원"},
  "G": {"ko": "교훈/도학", "en": "moral_teaching", "desc": "유교 윤리 덕목, 교화"},
  "H": {"ko": "풍자/해학", "en": "satire_humor", "desc": "사회 모순 비판, 웃음"},
  "I": {"ko": "무상/탄로", "en": "impermanence", "desc": "세월의 덧없음, 늙음 한탄"},
  "J": {"ko": "종교/신앙", "en": "religion", "desc": "불교 신앙, 극락왕생 기원"},
  "K": {"ko": "기행", "en": "travel", "desc": "여행, 풍경 감상"},
  "L": {"ko": "노동/세시풍속", "en": "labor_customs", "desc": "농사, 세시풍속, 민속"},
  "M": {"ko": "건국 송축", "en": "founding_celebration", "desc": "건국의 위업, 송축"},
}

DEFAULT_THEME = "A"  # fallback: 강호자연 (가장 중립적)


# 6개 지배적 정서 카탈로그
EMOTION_CATALOG: dict[str, dict[str, str]] = {
  "E1": {"ko": "애절/그리움", "en": "melancholic_yearning",
         "desc": "부드럽고 아련하며 슬픈 분위기"},
  "E2": {"ko": "원망/차가움", "en": "cold_resentment",
         "desc": "배신감, 차갑고 단절된, 쓸쓸한 분위기"},
  "E3": {"ko": "비장/결연", "en": "resolute_solemn",
         "desc": "의지가 굳건하고 무겁고 진지한 분위기"},
  "E4": {"ko": "평화/달관", "en": "peaceful_detached",
         "desc": "여유롭고 욕심이 없는 평온한 분위기"},
  "E5": {"ko": "쾌활/해학", "en": "cheerful_witty",
         "desc": "유머러스하고 밝고 활기찬 분위기"},
  "E6": {"ko": "경건/숭고", "en": "sacred_sublime",
         "desc": "종교적 외경, 장엄하고 신성한 분위기"},
}
DEFAULT_EMOTION = "E1"

# 정서별 이미지 톤 가이드 (이미지 프롬프트에 주입)
# ※ 조명·색조·분위기만 지정. 계절·배경 장소를 직접 바꾸는 키워드는 절대 포함하지 않는다.
EMOTION_IMAGE_TONE: dict[str, str] = {
  "E1": "soft diffused lighting, hazy mist, desaturated blue tones, wistful lonely atmosphere",
  "E2": "stark cold lighting, sharp shadows, muted blue-gray color grading, bitter somber mood",
  "E3": "dramatic chiaroscuro, deep saturated tones, heavy clouds, tense powerful atmosphere",
  "E4": "warm golden hour light, gentle breeze effect, open sky, calm contemplative mood",
  "E5": "bright saturated colors, dynamic composition, warm sunlight, lively festive energy",
  "E6": "ethereal glow, golden haze, vertical composition, vast sacred space, reverent stillness",
}

# 씬별 한글 감정 → 정서 코드 매핑
SCENE_EMOTION_MAP: dict[str, str] = {
  '슬픔': 'E1',
  '그리움': 'E1',
  '외로움': 'E1',
  '원망': 'E2',
  '분노': 'E3',
  '비장': 'E3',
  '자긍심': 'E3',
  '평화': 'E4',
  '관조': 'E4',
  '희망': 'E5',
  '기쁨': 'E5',
  '쾌활': 'E5',
  '경건': 'E6',
}


# ─── Step 1: 테마 분류 LLM 프롬프트용 ───

def get_theme_classification_prompt() -> str:
  """Step 1 LLM 시스템 프롬프트에 삽입할 테마 분류 지시문 (CoT + Few-shot)"""
  catalog_lines = []
  for code, info in THEME_CATALOG.items():
    catalog_lines.append(f"  {code}. {info['ko']} — {info['desc']}")
  catalog_str = "\n".join(catalog_lines)

  emotion_lines = []
  for code, info in EMOTION_CATALOG.items():
    emotion_lines.append(f"  {code}. {info['ko']} — {info['desc']}")
  emotion_str = "\n".join(emotion_lines)

  prompt = f"""## 테마/정서 분류 (3단계 순서대로 판단)

### 테마 카탈로그 (13개)
{catalog_str}

---

### [1단계] surface_theme — 텍스트 표면에 보이는 상황
시를 처음 읽었을 때 시적 화자가 처한 상황, 묘사된 장면이 무엇인지 고릅니다.
제목이나 작가 정보 없이 원문 텍스트만 보고 판단하세요.

예) "떠난 임을 기다리는 여인의 한탄" → F (이별의 정한)
예) "자연 속에서 한가로이 노닌다" → A (강호자연)
예) "나라를 걱정하며 죽음도 불사하겠다" → C (충절/우국)

### [2단계] primary_theme — 작가의 궁극적 진심
작가가 이 시를 왜 지었는지, 시 너머의 진짜 의도를 고릅니다.
고전시가는 여성 화자를 빌려 임금에 대한 그리움을 표현하거나,
자연을 빌려 유배의 한을 표현하는 경우가 많습니다.

판단 규칙:
- 화자가 여성이지만 실제로는 신하가 임금을 그리는 내용 → primary=B (연군)
- 임금을 향한 충성 의지 표현 → primary=C (충절)
- 유배지 고난 묘사 → primary=D (유배)
- 표면과 진심이 같으면 surface와 동일 코드 사용

혼동 방지:
- 연군(B) vs 이별(F): 신하→임금 관계이면 B, 남녀 이별이면 F
- 연군(B) vs 애정(E): 임금 그리움이면 B, 남녀 사랑 자체이면 E
- 충절(C) vs 연군(B): 충성 의지·결의이면 C, 임금 그리움·잊혀짐이면 B
- 유배(D) vs 연군(B): 유배지 고난·억울함이면 D, 임금 그리움이면 B

### [3단계] dominant_emotion — 작품 전체 감정선 (테마와 독립 판단)
테마에 관계없이 작품이 전달하는 지배적 감정을 고릅니다.

{emotion_str}

핵심 신호 단어:
- E1 (그리움): "보고 싶다", "그립다", "기다린다", 아련하고 부드러운 슬픔
- E2 (원망): "변했다", "잊었다", "낯이 변하다", "배신", "달라졌다", 차갑고 쓴 감정
- E3 (비장): "죽어도", "변치 않겠다", "충성", "결의", 굳건한 의지
- E4 (달관): "한가롭다", "흥겹다", "자연과 하나", 여유롭고 평온
- E5 (해학): 풍자, 웃음, 과장, 반어적 표현
- E6 (경건): 불교, 부처, 극락, 하늘, 종교적 외경

⚠️ E1 vs E2 구분이 가장 중요:
  상대방의 변심·배신·냉대를 원망하면 → E2
  상대가 그립고 보고 싶고 아련하면 → E1

---

### Few-shot 예시 (참고)

**예시 1 — 원가/연군류** (surface≠primary, 원망이 핵심)
원문 발췌: "질 좋은 잣이 가을에도 떨어지지 않건만, 낯이 변해버리신 겨울이여"
→ theme_reasoning: "표면적으로는 변심한 상대를 원망하는 이별의 한이나, 실제 작가는 자신을 잊은 임금을 향해 쓴 연군시"
→ surface_theme: F (이별의 정한)
→ primary_theme: B (연군)
→ emotion_reasoning: "잣나무의 변치 않음 vs 변해버린 임금의 마음을 대조하여 배신감을 극대화. 차갑고 쓴 원망이 지배적"
→ dominant_emotion: E2 (원망/차가움)

**예시 2 — 강호자연류** (surface=primary, 달관이 핵심)
원문 발췌: "청산리 벽계수야 수이 감을 자랑 마라, 명월이 만공산하니 쉬어 간들 어떠리"
→ theme_reasoning: "자연물(물, 달)을 노래하며 인생의 덧없음을 달관하는 시. 표면과 진심 모두 강호자연"
→ surface_theme: A (강호자연)
→ primary_theme: A (강호자연)
→ emotion_reasoning: "급히 흘러가는 물을 만류하며 달과 함께 쉬어가자는 여유. 평화롭고 달관된 정서"
→ dominant_emotion: E4 (평화/달관)

**예시 3 — 충절류** (surface=primary, 비장함이 핵심)
원문 발췌: "이 몸이 죽고 죽어 일백번 고쳐 죽어, 백골이 진토 되어 넋이라도 있고 없고"
→ theme_reasoning: "죽음을 무릅쓴 충성 의지를 직접 표현. 임금 그리움보다는 변치 않는 충성 결의가 핵심"
→ surface_theme: C (충절/우국)
→ primary_theme: C (충절/우국)
→ emotion_reasoning: "죽어도 변치 않겠다는 굳건한 결의. 무겁고 비장한 분위기"
→ dominant_emotion: E3 (비장/결연)

---

### 응답 JSON에 반드시 포함할 필드 (순서 중요)
"theme_reasoning": "판단 근거 1~2문장 (surface→primary 순서로 설명)",
"emotion_reasoning": "감정 판단 근거 1문장",
"surface_theme": "코드(A~M)", "surface_theme_en": "영문키",
"primary_theme": "코드(A~M)", "primary_theme_en": "영문키",
"dominant_emotion": "코드(E1~E6)", "dominant_emotion_en": "영문키"
"""
  return prompt


# ─── Step 1: 테마별 이미지 프롬프트 스타일 가이드 ───

THEME_IMAGE_STYLE_GUIDE: dict[str, str] = {
  "A": "cool blue-green palette, misty soft atmosphere, sage and teal hues",
  "B": "muted blue-gray tones, pale moonlit haze, cold desaturated lighting",
  "C": "dark ominous sky, deep crimson accent tones, high-contrast dramatic lighting",
  "D": "cold desolate gray-blue palette, stark overcast lighting, bleak washed-out tones",
  "E": "warm soft-focus lighting, warm rose and amber tones, gentle diffused glow",
  "F": "cool blue-gray tones, fading dusk light, desaturated melancholic palette",
  "G": "neutral muted tones, clean even lighting, composed understated palette",
  "H": "vivid saturated folk colors, bright warm lighting, high chroma palette",
  "I": "desaturated earthy palette, dim autumn light, muted brown and ochre tones",
  "J": "warm golden light, soft incense haze, amber and ivory glow",
  "K": "clear bright natural light, vivid scenic colors, crisp high-contrast daylight",
  "L": "warm earthy harvest tones, golden afternoon light, amber and sienna palette",
  "M": "majestic gold and deep red tones, warm ceremonial lighting, rich saturated palette",
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

_SHORTS_SUB = {"color": (255, 255, 255), "stroke_color": (0, 0, 0), "stroke_width": 3, "size": 52, "opacity": 1.0}

THEME_SUBTITLE_STYLE: dict[str, dict] = {
  "A": _SHORTS_SUB,  # 숏츠 표준: 흰색 + 검은 외곽선
  "B": _SHORTS_SUB,
  "C": _SHORTS_SUB,
  "D": _SHORTS_SUB,
  "E": _SHORTS_SUB,
  "F": _SHORTS_SUB,
  "G": _SHORTS_SUB,
  "H": _SHORTS_SUB,
  "I": _SHORTS_SUB,
  "J": _SHORTS_SUB,
  "K": _SHORTS_SUB,
  "L": _SHORTS_SUB,
  "M": _SHORTS_SUB,
}
DEFAULT_SUBTITLE_STYLE = _SHORTS_SUB.copy()

THEME_BGM_VOLUME: dict[str, dict[str, float]] = {
  "A": {"tts": 0.8, "bgm": 0.4},    # BGM 높게 (자연 분위기)
  "B": {"tts": 0.9, "bgm": 0.3},    # 균형
  "C": {"tts": 1.0, "bgm": 0.2},    # TTS 우선
  "D": {"tts": 0.85, "bgm": 0.35},  # 약간 BGM
  "E": {"tts": 0.9, "bgm": 0.35},   # 로맨틱 분위기
  "H": {"tts": 1.0, "bgm": 0.15},   # TTS 최우선 (해학)
  "I": {"tts": 0.7, "bgm": 0.45},   # BGM 우세 (몽환)
  "J": {"tts": 0.8, "bgm": 0.4},    # 경건한 BGM
}
DEFAULT_BGM_VOLUME = {"tts": 0.9, "bgm": 0.25}


# ─── 헬퍼 함수 ───

def get_image_style_guide(theme_code: str) -> str:
  """surface_theme 코드 → 이미지 스타일 가이드 문자열"""
  return THEME_IMAGE_STYLE_GUIDE.get(theme_code, THEME_IMAGE_STYLE_GUIDE[DEFAULT_THEME])


def get_emotion_info(emotion_code: str) -> dict[str, str]:
  """정서 코드 → 카탈로그 정보 (fallback: DEFAULT_EMOTION)"""
  return EMOTION_CATALOG.get(emotion_code, EMOTION_CATALOG[DEFAULT_EMOTION])


def get_emotion_image_tone(emotion_code: str) -> str:
  """정서 코드 → 이미지 톤 가이드 문자열"""
  return EMOTION_IMAGE_TONE.get(emotion_code, EMOTION_IMAGE_TONE[DEFAULT_EMOTION])


def map_scene_emotion_to_code(scene_emotion: str, fallback: str = DEFAULT_EMOTION) -> str:
  """씬별 한글 감정 → 정서 코드 매핑. 매핑 실패 시 fallback(dominant_emotion) 사용."""
  return SCENE_EMOTION_MAP.get(scene_emotion, fallback)


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
  """테마 코드 → TTS/BGM 볼륨"""
  return THEME_BGM_VOLUME.get(theme_code, DEFAULT_BGM_VOLUME)
