import os
import json
from datetime import datetime

LOG_PATH = "data/journal.json"
WILDERNESS_PATH = "data/wilderness.md"

def log_event(event: dict) -> None:
    """
    Appends an event (dict) with timestamp to a JSON log file.
    Silently ignores all errors.
    """
    try:
        # Ensure parent directory exists
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        if not os.path.isfile(LOG_PATH):
            with open(LOG_PATH, "w", encoding="utf-8") as f:
                f.write("[]")
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            log = json.load(f)
        log.append({"ts": datetime.now().isoformat(), **event})
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # Silently ignore all errors

def wilderness_log(fragment: str) -> None:
    """
    Appends a text fragment to the wilderness log (Markdown file).
    Silently ignores all errors.
    """
    try:
        os.makedirs(os.path.dirname(WILDERNESS_PATH), exist_ok=True)
        with open(WILDERNESS_PATH, "a", encoding="utf-8") as f:
            f.write(fragment.strip() + "\n\n")
    except Exception:
        pass  # Silently ignore all errors
