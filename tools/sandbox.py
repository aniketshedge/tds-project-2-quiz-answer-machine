from __future__ import annotations

import asyncio
import textwrap
from dataclasses import dataclass


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    returncode: int


class SandboxExecutor:
    """
    Very lightweight sandbox that runs Python code in a subprocess.
    In a production deployment, this should be restricted further.
    """

    async def run(self, code: str) -> SandboxResult:
        wrapped_code = textwrap.dedent(code)

        proc = await asyncio.create_subprocess_exec(
            "python",
            "-c",
            wrapped_code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await proc.communicate()

        return SandboxResult(
            stdout=stdout_bytes.decode("utf-8", errors="ignore"),
            stderr=stderr_bytes.decode("utf-8", errors="ignore"),
            returncode=proc.returncode,
        )
