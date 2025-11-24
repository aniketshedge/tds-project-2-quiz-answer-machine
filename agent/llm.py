from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from openai import OpenAI

from config import Settings
from . import prompts


logger = logging.getLogger(__name__)


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
            "Important:\n"
            "- The \"secret\" field is an authentication token and is NOT the quiz answer.\n"
            "- Your job is to read the natural-language question on the page and "
            "compute the value that should go into the \"answer\" field.\n"
            "- Your Python code must NOT print the secret or any authentication tokens.\n"
            "- If the page tells you to fetch another URL (for example to scrape a table "
            "or secret code), you may use the `requests` library from Python to perform "
            "HTTP GET or POST requests.\n"
            "- If the page refers to relative URLs such as `/submit` or `/demo-scrape-data?...`, "
            "treat them as relative to the current page URL using standard URL-joining logic "
            "(for example via `urllib.parse.urljoin`).\n\n"
            "Write Python code that loads any required data from the page text and any "
            "linked URLs, performs the necessary computations, and finally prints ONLY the "
            "answer to stdout (no extra text).\n\n"
            f"Page text:\n{page_text}\n\n"
            f"Previous attempts and errors:\n{history}"
        )

        logger.info(
            "LLM request payload: %s",
            json.dumps(
                {
                    "model": self._model,
                    "instructions": prompts.SYSTEM_PROMPT,
                    "input": combined_input,
                }
            ),
        )

        response = self._client.responses.create(
            model=self._model,
            instructions=prompts.SYSTEM_PROMPT,
            input=combined_input,
            reasoning={"effort": "medium"},
        )

        content: Optional[str] = getattr(response, "output_text", None)
        logger.info("LLM response output_text: %r", content)
        if not content:
            raise RuntimeError("Model returned empty content.")
        return content

    def parse_answer(self, execution_output: str) -> str:
        """
        For now, treat the sandbox stdout as the answer.
        A more advanced implementation could ask the model to sanitize it.
        """
        return execution_output.strip()
