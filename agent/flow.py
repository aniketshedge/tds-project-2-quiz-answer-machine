from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

import requests

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
            page_text = page.text

            # Augment page text with audio transcripts and explicit data resource hints.
            combined_page_text = page_text

            # Transcribe any audio sources found on the page.
            transcripts: List[Dict[str, Any]] = []
            if page.audio_urls:
                loop = asyncio.get_running_loop()
                for audio_url in page.audio_urls:
                    try:
                        def _get() -> bytes:
                            resp = requests.get(
                                audio_url,
                                timeout=self.settings.browser_timeout_ms / 1000,
                            )
                            resp.raise_for_status()
                            return resp.content

                        audio_bytes = await loop.run_in_executor(None, _get)
                        text = llm.transcribe_audio(audio_bytes)
                        transcripts.append({"url": audio_url, "text": text})
                    except Exception as exc:
                        # Record the error in history so the LLM can see it if needed.
                        self.history.append(
                            {
                                "error": f"Audio transcription failed for {audio_url}: {exc}",
                                "stage": "audio_transcription",
                            }
                        )

            if transcripts:
                combined_page_text += "\n\nAudio transcripts:\n"
                for item in transcripts:
                    combined_page_text += f"- Source: {item['url']}\n{item['text']}\n"

            if page.data_urls:
                combined_page_text += "\n\nData resources linked from the page:\n"
                for data_url in page.data_urls:
                    combined_page_text += f"- {data_url}\n"

            answer = None
            for attempt in range(3):
                code = llm.plan_and_code(
                    page_text=combined_page_text,
                    history=self.history,
                    current_url=current_url,
                    email=self.email,
                )
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
