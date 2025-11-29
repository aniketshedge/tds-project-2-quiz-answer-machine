from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

import requests

from config import Settings
from tools.browser import BrowserClient
from tools.sandbox import SandboxExecutor
from logging_utils import log_event
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
        overall_last_next_url: Optional[str] = None
        used_fallback = False

        while time.time() < deadline or (overall_last_next_url is not None and not used_fallback):
            # If the global time budget has elapsed, but we have a latest
            # suggested next URL that we haven't tried yet, follow it once
            # before giving up.
            if time.time() >= deadline:
                if overall_last_next_url is not None and not used_fallback:
                    current_url = overall_last_next_url
                    used_fallback = True
                else:
                    return "Timed out before completing quiz."
            url_start = time.time()
            # Per-URL time budget: allow up to ~2 minutes of work on a
            # single quiz URL, so that we can safely make multiple attempts
            # before following any redirect to the next URL. For the final
            # fallback URL (after the global deadline), we still allow a
            # short per-URL budget.
            if used_fallback:
                url_deadline = url_start + 60
            else:
                url_deadline = min(deadline, url_start + 120)

            page = await browser.get(current_url)
            page_text = page.text

            # Augment page text with audio transcripts and explicit data resource hints.
            combined_page_text = page_text

            # Transcribe any audio sources found on the page.
            transcripts: List[Dict[str, Any]] = []
            if page.audio_urls:
                log_event(
                    "AUDIO_SOURCES_FOUND",
                    current_url=current_url,
                    audio_urls=page.audio_urls,
                )
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
                        log_event(
                            "AUDIO_TRANSCRIPT",
                            current_url=current_url,
                            audio_url=audio_url,
                            transcript=text,
                        )
                    except Exception as exc:
                        # Record the error in history so the LLM can see it if needed,
                        # and also log it explicitly for debugging.
                        self.history.append(
                            {
                                "error": f"Audio transcription failed for {audio_url}: {exc}",
                                "stage": "audio_transcription",
                            }
                        )
                        log_event(
                            "AUDIO_TRANSCRIPT_ERROR",
                            current_url=current_url,
                            audio_url=audio_url,
                            error=str(exc),
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
            last_next_url: Optional[str] = None
            attempt = 0
            while attempt < 3 and time.time() < url_deadline:
                attempt += 1
                # On the first attempt, do not send the full-page screenshot
                # (to save tokens); from the second attempt onward, include it.
                screenshot = page.screenshot if attempt > 1 else None
                code = llm.plan_and_code(
                    page_text=combined_page_text,
                    history=self.history,
                    current_url=current_url,
                    email=self.email,
                    screenshot=screenshot,
                    image_urls=page.image_urls,
                )

                # Provide the JS-rendered page context and discovered data URLs
                # directly to the sandboxed code as Python variables so the
                # generated code can rely on them instead of re-fetching
                # the main page HTML.
                context_prefix = (
                    f"PAGE_TEXT = {combined_page_text!r}\n"
                    f"CURRENT_URL = {current_url!r}\n"
                    f"DATA_URLS = {page.data_urls!r}\n"
                )
                wrapped_code = context_prefix + "\n" + code

                exec_result = await sandbox.run(wrapped_code)

                if exec_result.returncode != 0:
                    # Record sandbox stderr so subsequent attempts can adapt.
                    self.history.append(
                        {
                            "error": exec_result.stderr[:300],
                            "stage": "execution",
                            "attempt": attempt,
                        }
                    )

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
                        last_next_url = submission.next_url
                        overall_last_next_url = submission.next_url
                        current_url = submission.next_url
                        self.history = []
                        # Treat this as a redirect after a successful solve.
                        break
                    return "Quiz Completed"

                # Incorrect answer handling
                error_reason = submission.reason or "Incorrect answer"
                self.history.append({"error": error_reason, "attempt": attempt})

                if submission.next_url:
                    # Remember the latest suggested next URL, but do not
                    # follow it yet. We keep retrying this URL while there
                    # is time left in the per-URL budget.
                    last_next_url = submission.next_url
                    overall_last_next_url = submission.next_url

            # After attempts or per-URL time budget are exhausted:
            if last_next_url:
                # Follow only the final suggested next URL from the last
                # attempt made for this question.
                current_url = last_next_url
                # Keep history so the next URL can see previous context.
                continue

            # No redirect URL was ever provided and attempts are exhausted.
            return "Failed to solve quiz within attempts."
        return "Timed out before completing quiz."
