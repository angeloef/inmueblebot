"""Echo tool — repeats a message back."""

from typing import Any


def echo(text: str = "") -> str:
    """Repeat the given text back to the user.

    If no text is provided, returns a default message.
    """
    if not text.strip():
        return "No especificaste ningún texto para repetir."
    return f"Eco: {text}"
