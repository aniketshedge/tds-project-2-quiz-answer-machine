from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
from typing import Any, Dict, List, Optional

from openai import OpenAI, BadRequestError

from config import Settings
from logging_utils import log_event
from . import prompts


class LlmClient:
    """
    Lightweight wrapper around the OpenAI client for GPT-5-nano style models.
    """

    def __init__(self, settings: Settings) -> None:
        kwargs: Dict[str, Any] = {"api_key": settings.openai_api_key}
        if settings.openai_base_url:
            kwargs["base_url"] = str(settings.openai_base_url)
        self._client = OpenAI(**kwargs)
        self._model = settings.openai_model
        self._audio_model = settings.openai_transcription_model

    def transcribe_audio(self, audio_bytes: bytes) -> str:
        """
        Transcribe an audio clip to text using the configured transcription model.
        """
        # First attempt: send the original bytes as-is.
        def _call_transcription(b: bytes, filename: str) -> str:
            file_obj = io.BytesIO(b)
            file_obj.name = filename
            response = self._client.audio.transcriptions.create(
                model=self._audio_model,
                file=file_obj,
            )
            text: Optional[str] = getattr(response, "text", None)
            if not text:
                raise RuntimeError("Audio transcription returned empty text.")
            return text

        try:
            return _call_transcription(audio_bytes, "audio.opus")
        except BadRequestError as exc:
            message = str(exc)
            # Custom endpoints may reject OPUS; attempt a local conversion
            # to WAV using ffmpeg, then retry once.
            if "Unsupported file format" not in message and "unsupported_value" not in message:
                raise

            # Best-effort conversion; if this fails we re-raise the original error.
            try:
                with tempfile.NamedTemporaryFile(suffix=".opus", delete=False) as src:
                    src.write(audio_bytes)
                    src_path = src.name
                dst_path = src_path + ".wav"
                try:
                    subprocess.run(
                        [
                            "ffmpeg",
                            "-y",
                            "-i",
                            src_path,
                            "-acodec",
                            "pcm_s16le",
                            "-ar",
                            "16000",
                            dst_path,
                        ],
                        check=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    with open(dst_path, "rb") as f:
                        wav_bytes = f.read()
                finally:
                    for p in (src_path, dst_path):
                        try:
                            os.remove(p)
                        except OSError:
                            pass

                return _call_transcription(wav_bytes, "audio.wav")
            except Exception:
                # If conversion or second call fails, surface the original error.
                raise exc

    def plan_and_code(
        self,
        page_text: str,
        history: List[Dict[str, Any]],
        current_url: str,
        email: str,
    ) -> str:
        """
        Ask the model to propose Python code that, when executed, produces
        the final quiz answer and prints it to stdout.
        """
        combined_input = (
            "You are given the text content of a quiz web page. "
            "The page may include example JSON payloads with fields like "
            "\"email\", \"secret\", and \"answer\" that describe how an external "
            "caller will submit the result.\n\n"
            f"The current page URL is: {current_url}\n"
            f"The student email for this run is: {email}\n\n"
            "Important behavioral constraints for your Python code:\n"
            "- The \"secret\" field is an authentication token and is NOT the quiz answer.\n"
            "- Your job is to read the natural-language question on the page and "
            "  compute the value that should go into the \"answer\" field.\n"
            "- Your Python code must NOT print the secret or any authentication tokens.\n"
            "- In the execution environment, the following Python variables are already defined:\n"
            "    * PAGE_TEXT: a string with the fully rendered page text plus any extracted\n"
            "      audio transcripts and data resource hints.\n"
            "    * CURRENT_URL: the current quiz page URL.\n"
            "    * DATA_URLS: a Python list of absolute URLs to linked data files (for example CSVs).\n"
            "- Do NOT re-download the main quiz page using requests; instead, parse PAGE_TEXT\n"
            "  to understand the question and find any URLs mentioned there.\n"
            "- You MAY use the `requests` library (and libraries like `pandas`) to fetch and\n"
            "  process additional URLs that are explicitly mentioned in PAGE_TEXT or provided\n"
            "  via DATA_URLS (for example CSV files, API endpoints, or secondary pages like\n"
            "  `/demo-scrape-data?...`).\n"
            "- If the page refers to relative URLs such as `/submit` or `/demo-scrape-data?...`, "
            "treat them as relative to CURRENT_URL using standard URL-joining logic "
            "(for example via `urllib.parse.urljoin`).\n\n"
            "Write Python code that uses PAGE_TEXT, CURRENT_URL, and DATA_URLS plus any\n"
            "necessary HTTP requests to linked resources to perform the required computations,\n"
            "and finally prints ONLY the answer to stdout (no extra text).\n\n"
            f"PAGE_TEXT (page text and extracted context):\n{page_text}\n\n"
            f"Previous attempts and errors:\n{history}"
        )

        log_event(
            "LLM_REQUEST",
            model=self._model,
            current_url=current_url,
        )

        response = self._client.responses.create(
            model=self._model,
            instructions=prompts.SYSTEM_PROMPT,
            input=combined_input,
            reasoning={"effort": "medium"},
        )

        content: Optional[str] = getattr(response, "output_text", None)
        log_event(
            "LLM_RESPONSE",
            model=self._model,
            current_url=current_url,
            output_full=content,
        )
        if not content:
            raise RuntimeError("Model returned empty content.")
        return content

    def parse_answer(self, execution_output: str) -> str:
        """
        For now, treat the sandbox stdout as the answer.
        A more advanced implementation could ask the model to sanitize it.
        """
        return execution_output.strip()
