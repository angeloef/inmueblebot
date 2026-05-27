"""Conversation logger — records every turn to a JSONL file for debugging."""

import json
import os
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(os.environ.get("CONVERSATION_LOG_DIR", "logs"))
LOG_FILE = LOG_DIR / "conversations.jsonl"


def ensure_log_dir():
    """Create the log directory if it doesn't exist."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def log_turn(
    session_id: str,
    turn: int,
    message: str,
    response: str,
    router: str,
    latency_ms: float,
    confidence: float,
    tools_called: list[str],
    criteria_count: int = 0,
    phone: str = "",
    selection: int | None = None,
) -> dict:
    """Log a single conversation turn to the JSONL file.

    Returns the logged entry as a dict (also written to disk).
    """
    ensure_log_dir()

    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "session_id": session_id,
        "turn": turn,
        "phone": phone,
        "message": message,
        "response": response[:300],  # Truncate long responses
        "tools_called": tools_called,
        "router": router,
        "latency_ms": round(latency_ms, 1),
        "confidence": round(confidence, 2),
        "criteria_count": criteria_count,
        "selection": selection,
    }

    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass

    return entry


def read_recent_logs(limit: int = 20) -> list[dict]:
    """Read the most recent conversation turns from the log file."""
    ensure_log_dir()
    if not LOG_FILE.exists():
        return []

    entries = []
    try:
        with open(LOG_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except Exception:
        pass

    return entries[-limit:]


def get_session_logs(session_id: str) -> list[dict]:
    """Get all turns for a specific session."""
    ensure_log_dir()
    if not LOG_FILE.exists():
        return []

    entries = []
    try:
        with open(LOG_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entry = json.loads(line)
                        if entry.get("session_id") == session_id:
                            entries.append(entry)
                    except json.JSONDecodeError:
                        continue
    except Exception:
        pass

    return entries


def clear_logs() -> int:
    """Clear the log file. Returns number of entries removed."""
    if not LOG_FILE.exists():
        return 0
    count = sum(1 for _ in open(LOG_FILE))
    LOG_FILE.unlink()
    return count
