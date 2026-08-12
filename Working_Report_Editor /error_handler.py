"""
error_handler.py — Custom exceptions, retry decorator, structured error logging.
"""

import json
import logging
import traceback
from datetime import datetime
from functools import wraps
from typing import Any, Dict, Optional

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config import (
    ERROR_LOG_PATH,
    MAX_RETRIES,
    RETRY_MAX_WAIT_SEC,
    RETRY_MIN_WAIT_SEC,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Custom Exceptions
# ─────────────────────────────────────────────

class BaseProcessingError(Exception):
    """Root exception for all pipeline errors."""

    def __init__(self, message: str, error_type: str, details: Optional[Dict] = None):
        super().__init__(message)
        self.error_type = error_type
        self.details = details or {}
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "error_type": self.error_type,
            "message": str(self),
            "details": self.details,
        }


class EmailFetchError(BaseProcessingError):
    pass


class ParsingError(BaseProcessingError):
    pass


class ValidationError(BaseProcessingError):
    pass


class SheetUpdateError(BaseProcessingError):
    pass


class AttachmentError(BaseProcessingError):
    pass


class DuplicateEmailError(BaseProcessingError):
    pass


# ─────────────────────────────────────────────
# Structured Error Logger
# ─────────────────────────────────────────────

def log_error(error: Exception, context: Dict[str, Any]) -> None:
    """Append a structured JSON error record to the error log file."""
    import os
    os.makedirs("logs", exist_ok=True)

    record = {
        "timestamp": datetime.now().isoformat(),
        "error_type": type(error).__name__,
        "message": str(error),
        "traceback": traceback.format_exc(),
        "context": {k: str(v)[:500] for k, v in context.items()},
    }

    try:
        with open(ERROR_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as write_err:
        logger.error(f"Could not write to error log: {write_err}")

    logger.error(f"[{type(error).__name__}] {error} | context={context}")


# ─────────────────────────────────────────────
# Retry Decorator
# ─────────────────────────────────────────────

def with_retry(
    retry_count: int = MAX_RETRIES,
    retryable_exceptions: tuple = (ConnectionError, TimeoutError, OSError),
):
    """
    Decorator that:
      • Retries on transient network/IO errors with exponential back-off.
      • Wraps unexpected exceptions in BaseProcessingError.
      • Never retries on custom domain exceptions (they're deterministic).
    """
    def decorator(func):
        @wraps(func)
        @retry(
            stop=stop_after_attempt(retry_count),
            wait=wait_exponential(
                multiplier=1,
                min=RETRY_MIN_WAIT_SEC,
                max=RETRY_MAX_WAIT_SEC,
            ),
            retry=retry_if_exception_type(retryable_exceptions),
            reraise=True,
        )
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except BaseProcessingError:
                raise
            except retryable_exceptions:
                raise
            except Exception as exc:
                ctx = {
                    "function": func.__name__,
                    "args": str(args)[:300],
                    "kwargs": str(kwargs)[:300],
                }
                log_error(exc, ctx)
                raise BaseProcessingError(
                    f"Unexpected error in {func.__name__}: {exc}",
                    "unhandled_error",
                    ctx,
                ) from exc

        return wrapper
    return decorator
