"""Empathy detection — sentiment analysis + adaptive tone (Phase 10).

Detects emotional state from user messages and suggests appropriate
tone adjustments for the response.
"""

import re
from dataclasses import dataclass


@dataclass
class EmotionalState:
    primary: str = "neutral"
    intensity: float = 0.0
    keywords_found: list[str] = None

    def __post_init__(self):
        if self.keywords_found is None:
            self.keywords_found = []


# Sentiment patterns
SENTIMENT_PATTERNS = {
    "frustrated": {
        "keywords": [
            "ya te dije", "otra vez", "no me entendés", "no entendés",
            "te dije", "cuantas veces", "estás sordo", "no escuchás",
            "mal", "pésimo", "no sirve", "no funciona",
        ],
        "response_prefix": "Entiendo, disculpá. ",
        "tone": "conciliatory",
    },
    "excited": {
        "keywords": [
            "genial", "buenísimo", "excelente", "me encanta", "me gustó",
            "espectacular", "divino", "hermoso", "qué lindo", "justo lo que",
            "perfecto", "ideal", "amo", "fantástico",
        ],
        "response_prefix": "¡Qué bueno! ",
        "tone": "enthusiastic",
    },
    "uncertain": {
        "keywords": [
            "no sé", "no estoy seguro", "tal vez", "quizás",
            "dudo", "no me decido", "me cuesta", "no entiendo",
            "confundido", "no me queda claro", "cómo es",
        ],
        "response_prefix": "Tranquilo, tomate tu tiempo. ",
        "tone": "patient",
    },
    "rushed": {
        "keywords": [
            "rápido", "urgente", "ya", "apurate", "no tengo tiempo",
            "es para hoy", "lo antes posible", "cuánto antes",
            "necesito ya", "conseguime",
        ],
        "response_prefix": "Dale, voy directo. ",
        "tone": "efficient",
    },
    "polite": {
        "keywords": [
            "por favor", "gracias", "si fueras tan amable",
            "te agradecería", "disculpá", "perdón",
        ],
        "response_prefix": "",
        "tone": "warm_formal",
    },
}


def detect_emotion(message: str) -> EmotionalState:
    """Detect the user's emotional state from their message.

    Returns the strongest matching emotion.
    """
    msg = message.lower()
    best = EmotionalState()

    for emotion, data in SENTIMENT_PATTERNS.items():
        matches = [kw for kw in data["keywords"] if kw in msg]
        if matches:
            intensity = len(matches) / len(data["keywords"]) * 2  # 0-2 scale
            if intensity > best.intensity:
                best = EmotionalState(
                    primary=emotion,
                    intensity=min(1.0, intensity),
                    keywords_found=matches,
                )

    return best


def get_empathetic_prefix(message: str) -> str:
    """Get an empathetic response prefix based on detected emotion."""
    emotion = detect_emotion(message)
    data = SENTIMENT_PATTERNS.get(emotion.primary, {})
    return data.get("response_prefix", "")


def adjust_tone(response: str, emotion: EmotionalState) -> str:
    """Adjust response tone based on detected emotion.

    If emotion is frustrated: be more concise and apologetic.
    If emotion is excited: match enthusiasm.
    If emotion is rushed: be concise and direct.
    """
    if emotion.primary == "frustrated" and emotion.intensity > 0.3:
        prefix = SENTIMENT_PATTERNS["frustrated"]["response_prefix"]
        if not response.startswith("Entiendo"):
            response = prefix + response
        # Make more concise
        if len(response) > 300:
            sentences = response.split(".")
            response = ". ".join(sentences[:3]) + "."

    elif emotion.primary == "excited" and emotion.intensity > 0.3:
        prefix = SENTIMENT_PATTERNS["excited"]["response_prefix"]
        if not response.startswith("¡"):
            response = prefix + response

    elif emotion.primary == "rushed" and emotion.intensity > 0.3:
        prefix = SENTIMENT_PATTERNS["rushed"]["response_prefix"]
        if not response.startswith("Dale"):
            response = prefix + response
        if len(response) > 250:
            sentences = response.split(".")
            response = ". ".join(sentences[:2]) + "."

    elif emotion.primary == "uncertain" and emotion.intensity > 0.3:
        prefix = SENTIMENT_PATTERNS["uncertain"]["response_prefix"]
        if not response.startswith("Tranquilo"):
            response = prefix + response

    return response
