from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Optional

import requests
from playwright.async_api import async_playwright


@dataclass
class PageData:
    url: str
    text: str
    screenshot: Optional[bytes] = None


@dataclass
class SubmissionResponse:
    correct: bool
    next_url: Optional[str] = None
    reason: Optional[str] = None


class BrowserClient:
    """
    Thin abstraction over Playwright for loading quiz pages and
    submitting answers to the endpoint described on the page.
    """

    def __init__(self, timeout_ms: int = 30000) -> None:
        self.timeout_ms = timeout_ms

    async def get(self, url: str) -> PageData:
        """
        Use Playwright to render the page (executing JavaScript),
        then return the visible text and a full-page screenshot.
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)
                text = await page.inner_text("body")
                screenshot = await page.screenshot(full_page=True)
            finally:
                await browser.close()

        return PageData(url=url, text=text, screenshot=screenshot)

    def _identify_submission_target(self, page_text: str, quiz_url: str) -> Optional[str]:
        """
        Best-effort heuristic to find the submission URL from page text.

        The quiz description guarantees that the page will describe where
        to POST the answer (for example: "Post your answer to
        https://example.com/submit ..."). We scan for URLs and prefer those
        that appear near phrases like "post your answer" or "submit".
        """
        urls = re.findall(r"https?://[^\s\"'<>]+", page_text)
        if not urls:
            return None

        # Deduplicate while preserving order.
        seen: list[str] = []
        for url in urls:
            if url not in seen:
                seen.append(url)

        quiz_url_lower = quiz_url.strip().lower()
        candidates = [u for u in seen if u.strip().lower() != quiz_url_lower]
        if not candidates:
            candidates = seen

        lower_text = page_text.lower()
        ranked: list[str] = []
        for url in candidates:
            idx = lower_text.find(url.lower())
            if idx == -1:
                continue
            window = lower_text[max(0, idx - 120) : idx + 120]
            if "post your answer" in window or "submit" in window:
                ranked.append(url)

        if ranked:
            return ranked[0]

        return candidates[0] if candidates else None

    async def post_answer(
        self,
        current_url: str,
        email: str,
        secret: str,
        answer: str,
        page_text: str,
    ) -> SubmissionResponse:
        """
        Submit the answer to the endpoint described on the quiz page.
        The payload follows the format in the project brief:

        {
          "email": "...",
          "secret": "...",
          "url": "https://example.com/quiz-834",
          "answer": 12345
        }
        """
        submit_url = self._identify_submission_target(page_text=page_text, quiz_url=current_url)
        if not submit_url:
            return SubmissionResponse(
                correct=False,
                reason="Could not identify submission endpoint from page text.",
            )

        payload = {
            "email": email,
            "secret": secret,
            "url": current_url,
            "answer": answer,
        }

        loop = asyncio.get_running_loop()

        def _send() -> requests.Response:
            return requests.post(submit_url, json=payload, timeout=self.timeout_ms / 1000)

        try:
            response = await loop.run_in_executor(None, _send)
        except Exception as exc:  # pragma: no cover - network error path
            return SubmissionResponse(correct=False, reason=f"Error submitting answer: {exc}")

        try:
            data = response.json()
        except Exception as exc:  # pragma: no cover - unexpected response path
            return SubmissionResponse(
                correct=False,
                reason=f"Invalid response from submission endpoint (status {response.status_code}): {exc}",
            )

        correct = bool(data.get("correct"))
        next_url = data.get("url")
        reason = data.get("reason")

        return SubmissionResponse(correct=correct, next_url=next_url, reason=reason)
