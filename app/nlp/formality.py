"""Formality levels — context-aware formality adaptation (Phase 10).

Adjusts response formality based on user's language patterns.
"""

import re


FORMALITY_LEVELS = {
    "formal": {
        "pronouns": ["usted", "su", "le"],
        "verbs": ["quisiera", "podría", "desearía", "precisaría"],
        "greetings": ["buenos días", "buenas tardes", "buenas noches"],
        "polite_markers": ["por favor", "gracias", "si es tan amable"],
    },
    "neutral": {
        "pronouns": ["vos", "tu", "te"],
        "verbs": ["querés", "podés", "buscás", "necesitás"],
        "greetings": ["hola", "buenas"],
        "polite_markers": ["gracias", "dale"],
    },
    "casual": {
        "pronouns": ["vos", "te"],
        "verbs": ["querés", "podés", "buscás"],
        "greetings": ["hola", "buenas", "che"],
        "expressions": ["dale", "joya", "genial", "de una", "bárbaro", "buenísimo"],
    },
}


def detect_formality(message: str) -> str:
    """Detect the user's formality level from their message.

    Returns: 'formal', 'neutral', or 'casual'
    """
    import re
    msg = message.lower()
    scores = {"formal": 0, "neutral": 0, "casual": 0}

    for level, data in FORMALITY_LEVELS.items():
        for category, terms in data.items():
            for term in terms:
                # Match as whole word only (not substring)
                if re.search(rf"\b{re.escape(term)}\b", msg):
                    scores[level] += 1

    return max(scores, key=lambda k: (scores[k], {"formal": 0, "neutral": 2, "casual": 1}[k]))


def get_formality_guidance(level: str) -> str:
    """Get a system prompt addition for formality guidance."""
    if level == "formal":
        return "Usá 'usted' y un tono profesional y respetuoso."
    elif level == "casual":
        return "Usá 'vos' y un tono relajado y amigable. Podés usar 'dale', 'joya', 'genial'."
    return "Usá 'vos' y un tono neutral pero cálido."
