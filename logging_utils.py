from __future__ import annotations

import os
from datetime import datetime
from typing import Any

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "agent.log")


def log_event(event_type: str, **details: Any) -> None:
    """
    Append a structured event to the agent log file.
    Format:
    Event type: <TYPE>
    (<ISO-UTC timestamp>)
    key: value
    ...
    -----
    """
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        timestamp = datetime.utcnow().isoformat() + "Z"
        lines = [f"Event type: {event_type}", f"({timestamp})"]
        for key, value in details.items():
            lines.append(f"{key}: {value}")
        lines.append("-----")
        record = "\n".join(lines) + "\n"
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(record)
    except Exception:
        # Logging failures must never break the main application flow.
        return

