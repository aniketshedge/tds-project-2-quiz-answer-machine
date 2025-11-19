from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

from config import Settings
from tools.browser import BrowserClient
from tools.sandbox import SandboxExecutor
from .llm import LlmClient


@dataclass
class AgentFlow:
    initial_url: str
    email: str
    settings: Settings

    history: List[Dict[str, Any]] = field(default_factory=list)

    async def run(self) -> str:
        """
        Main recursive quiz loop with a global time budget.
        """
        browser = BrowserClient(timeout_ms=self.settings.browser_timeout_ms)
        sandbox = SandboxExecutor()
        llm = LlmClient(self.settings)

        deadline = time.time() + self.settings.max_run_seconds
        current_url = self.initial_url

        while time.time() < deadline:
            page = await browser.get(current_url)

            # Simple text-only implementation for now.
            page_text = page.text

            answer = None
            for attempt in range(3):
                code = llm.plan_and_code(page_text=page_text, history=self.history)
                exec_result = await sandbox.run(code)
                answer = llm.parse_answer(exec_result.stdout)

                submission = await browser.post_answer(
                    current_url=current_url,
                    email=self.email,
                    secret=self.settings.student_secret,
                    answer=answer,
                    page_text=page_text,
                )

                if submission.correct:
                    if submission.next_url:
                        current_url = submission.next_url
                        self.history = []
                        break
                    return "Quiz Completed"

                # Incorrect answer handling
                error_reason = submission.reason or "Incorrect answer"
                self.history.append({"error": error_reason, "attempt": attempt + 1})

                if submission.next_url:
                    current_url = submission.next_url
                    break

            # If inner loop exhausted without success and no redirect, stop.
            else:
                return "Failed to solve quiz within attempts."

        return "Timed out before completing quiz."
