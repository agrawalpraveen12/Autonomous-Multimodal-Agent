"""Shared helpers for tools: a structured result envelope and a small retry wrapper.

Every tool returns a ToolResult-shaped dict so the agent graph can branch on success
instead of parsing magic error strings out of the extracted content.
"""
import time
from typing import Any, Callable, Dict, Optional


def tool_result(
    ok: bool,
    content: str = "",
    error: Optional[str] = None,
    **meta: Any,
) -> Dict[str, Any]:
    """Build the standard tool return envelope.

    Keys:
        ok      -> did the tool succeed
        content -> extracted / transcribed text (empty on failure)
        error   -> user-facing error message (None on success)
        meta    -> arbitrary metadata (source_type, method, confidence, duration, pages, ...)
    """
    return {"ok": ok, "content": content or "", "error": error, "meta": meta}


def with_retries(
    fn: Callable[..., Any],
    *args: Any,
    retries: int = 3,
    base_delay: float = 1.2,
    **kwargs: Any,
) -> Any:
    """Call ``fn`` with simple exponential backoff on transient errors.

    Retries on any exception (covers Groq 429/5xx and network blips). Re-raises the
    last exception if all attempts fail so the caller can degrade gracefully.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(retries):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - intentional broad retry
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(base_delay * (attempt + 1))
    raise last_exc  # type: ignore[misc]
