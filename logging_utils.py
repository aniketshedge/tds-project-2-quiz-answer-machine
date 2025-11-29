from __future__ import annotations

import os
from datetime import datetime
from typing import Any

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "agent.log")
LLM_LOG_FILE = os.path.join(LOG_DIR, "llm_requests.log")

_submission_correct_count = 0
_submission_incorrect_count = 0


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
        global _submission_correct_count, _submission_incorrect_count

        timestamp = datetime.utcnow().isoformat() + "Z"
        lines = [f"Event type: {event_type}", f"({timestamp})"]

        # Maintain running totals of correct / incorrect submissions and
        # include them in the header for SUBMISSION_RESULT events.
        if event_type == "SUBMISSION_RESULT":
            correct_flag = bool(details.get("correct"))
            if correct_flag:
                _submission_correct_count += 1
            else:
                _submission_incorrect_count += 1
            lines.insert(
                1,
                f"Totals - correct: {_submission_correct_count}, incorrect: {_submission_incorrect_count}",
            )
        for key, value in details.items():
            lines.append(f"{key}: {value}")
        lines.append("-----")
        record = "\n".join(lines) + "\n"
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(record)
    except Exception:
        # Logging failures must never break the main application flow.
        return


def log_llm_request(
    model: str,
    current_url: str,
    instructions: str,
    input_payload: Any,
    reasoning: Any,
) -> None:
    """
    Append the full LLM request payload to a dedicated log file.
    Format:
    Model: <model>
    Timestamp: <ISO-UTC>
    Current URL: <url>
    Instructions:
    <instructions>
    Input:
    <JSON-serialized input payload>
    Reasoning:
    <JSON-serialized reasoning>
    -----
    """
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        timestamp = datetime.utcnow().isoformat() + "Z"
        import json

        lines = [
            f"Model: {model}",
            f"Timestamp: {timestamp}",
            f"Current URL: {current_url}",
            "Instructions:",
            instructions,
            "Input:",
            json.dumps(input_payload, ensure_ascii=False),
            "Reasoning:",
            json.dumps(reasoning, ensure_ascii=False),
            "-----",
        ]
        record = "\n".join(lines) + "\n"
        with open(LLM_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(record)
    except Exception:
        # Logging failures must never break the main application flow.
        return
