from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Optional, List

import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from urllib.parse import urljoin

from logging_utils import log_event


@dataclass
class PageData:
    url: str
    text: str
    screenshot: Optional[bytes] = None
    html: Optional[str] = None
    audio_urls: List[str] = field(default_factory=list)
    data_urls: List[str] = field(default_factory=list)


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
        then return the visible text, HTML, and a full-page screenshot.
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)
                text = await page.inner_text("body")
                html = await page.inner_html("body")
                screenshot = await page.screenshot(full_page=True)
            finally:
                await browser.close()

        audio_urls: List[str] = []
        data_urls: List[str] = []

        if html:
            soup = BeautifulSoup(html, "html.parser")

            # Audio sources (e.g. <audio src="demo-audio.opus">)
            for audio in soup.find_all("audio"):
                src = audio.get("src")
                if not src:
                    continue
                audio_urls.append(urljoin(url, src))

            # Data files (CSV / TSV / Excel etc.)
            data_exts = (".csv", ".tsv", ".xlsx", ".xls")
            for link in soup.find_all("a", href=True):
                href = link["href"]
                if not href:
                    continue
                if any(href.lower().endswith(ext) for ext in data_exts):
                    data_urls.append(urljoin(url, href))

        return PageData(
            url=url,
            text=text,
            screenshot=screenshot,
            html=html,
            audio_urls=audio_urls,
            data_urls=data_urls,
        )

    def _identify_submission_target(self, page_text: str, quiz_url: str) -> Optional[str]:
        """
        Best-effort heuristic to find the submission URL from page text.

        The quiz description guarantees that the page will describe where
        to POST the answer (for example: "Post your answer to
        https://example.com/submit ..."). We scan for URLs and prefer those
        that appear near phrases like "post your answer" or "submit".

        This implementation supports both absolute URLs and relative paths
        such as "/submit", resolving the latter against the quiz_url.
        """
        quiz_url_lower = quiz_url.strip().lower()
        lower_text = page_text.lower()

        # Collect candidate (display_text, absolute_url) pairs.
        candidates: list[tuple[str, str]] = []

        # 1) Absolute URLs.
        abs_urls = re.findall(r"https?://[^\s\"'<>]+", page_text)
        for url in abs_urls:
            full_url = url.strip()
            if not full_url:
                continue
            full_lower = full_url.lower()
            if full_lower == quiz_url_lower:
                continue
            if any(full_url == existing_full for _, existing_full in candidates):
                continue
            # display_text == full_url for absolute URLs.
            candidates.append((full_url, full_url))

        # 2) Relative paths starting with "/".
        rel_paths = re.findall(r"/[^\s\"'<>]+", page_text)
        for path in rel_paths:
            path = path.strip()
            if not path:
                continue
            full_url = urljoin(quiz_url, path)
            full_lower = full_url.lower()
            if full_lower == quiz_url_lower:
                continue
            if any(full_url == existing_full for _, existing_full in candidates):
                continue
            candidates.append((path, full_url))

        if not candidates:
            return None

        # Rank candidates by proximity to "post your answer" or "submit".
        ranked: list[str] = []
        for display_text, full_url in candidates:
            idx = lower_text.find(display_text.lower())
            if idx == -1:
                continue
            window = lower_text[max(0, idx - 120) : idx + 120]
            if "post your answer" in window or "submit" in window:
                ranked.append(full_url)

        if ranked:
            return ranked[0]

        # Fallback: first candidate in discovery order.
        return candidates[0][1] if candidates else None

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
            log_event(
                "SENT_POST",
                submit_url=submit_url,
                status_code="network_error",
                error=str(exc),
            )
            return SubmissionResponse(correct=False, reason=f"Error submitting answer: {exc}")

        try:
            data = response.json()
        except Exception as exc:  # pragma: no cover - unexpected response path
            safe_payload = dict(payload)
            if "secret" in safe_payload:
                safe_payload["secret"] = "***"
            log_event(
                "SENT_POST",
                submit_url=submit_url,
                status_code=response.status_code,
                payload=json.dumps(safe_payload),
                error=f"Invalid JSON response: {exc}",
            )
            return SubmissionResponse(
                correct=False,
                reason=f"Invalid response from submission endpoint (status {response.status_code}): {exc}",
            )

        correct = bool(data.get("correct"))
        next_url = data.get("url")
        reason = data.get("reason")

        safe_payload = dict(payload)
        if "secret" in safe_payload:
            safe_payload["secret"] = "***"
        log_event(
            "SENT_POST",
            submit_url=submit_url,
            status_code=response.status_code,
            payload=json.dumps(safe_payload),
        )

        # Log the evaluator's submission result (correctness, next URL, feedback).
        log_event(
            "SUBMISSION_RESULT",
            submit_url=submit_url,
            status_code=response.status_code,
            correct=correct,
            next_url=next_url,
            reason=reason,
            raw_response=json.dumps(data),
        )

        return SubmissionResponse(correct=correct, next_url=next_url, reason=reason)
