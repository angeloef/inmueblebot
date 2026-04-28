from langdetect import detect, LangDetectException


def detect_language(text: str) -> str:
    try:
        lang = detect(text)
        return "es" if lang == "es" else "en"
    except LangDetectException:
        return "es"