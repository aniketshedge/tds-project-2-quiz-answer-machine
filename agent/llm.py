from __future__ import annotations

from typing import Any, Dict, List, Optional

from openai import OpenAI

from config import Settings
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

    def plan_and_code(self, page_text: str, history: List[Dict[str, Any]]) -> str:
        """
        Ask the model to propose Python code that, when executed, produces
        the final quiz answer and prints it to stdout.
        """
        messages = [
            {
                "role": "system",
                "content": prompts.SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": (
                    "You are given the text content of a quiz web page. "
                    "Write Python code that loads any required data from the page text, "
                    "performs the necessary computations, and finally prints ONLY the "
                    "answer to stdout.\n\n"
                    f"Page text:\n{page_text}\n\n"
                    f"Previous attempts and errors:\n{history}"
                ),
            },
        ]

        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,  # type: ignore[arg-type]
            temperature=0.2,
        )

        content: Optional[str] = response.choices[0].message.content
        if not content:
            raise RuntimeError("Model returned empty content.")
        return content

    def parse_answer(self, execution_output: str) -> str:
        """
        For now, treat the sandbox stdout as the answer.
        A more advanced implementation could ask the model to sanitize it.
        """
        return execution_output.strip()

