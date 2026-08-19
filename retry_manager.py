"""
retry_manager.py
----------------
PHASE 4 of the AI News Automation Agent.

Provides reusable exponential backoff retry utilities for network requests, RSS feed fetching,
AI processing, and Telegram API interactions.
"""

import time
import functools
import logging
from typing import Callable
import config

logger = logging.getLogger("retry_manager")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)


def retry_with_backoff(
    func=None,
    max_retries: int = None,
    initial_delay: float = None,
    exponential: bool = True,
    exceptions: tuple = (Exception,)
):
    """
    Decorator / utility that retries a callable with backoff upon failure.
    """
    if max_retries is None:
        max_retries = getattr(config, "MAX_RETRIES", 3)
    if initial_delay is None:
        initial_delay = getattr(config, "RETRY_DELAY_SECONDS", 10)

    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None

            for attempt in range(1, max_retries + 1):
                try:
                    return f(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_retries:
                        logger.warning("Operation '%s' failed after %d attempts: %s", f.__name__, max_retries, e)
                        raise e

                    logger.info(
                        "Attempt %d/%d for '%s' failed: %s. Retrying in %s seconds...",
                        attempt,
                        max_retries,
                        f.__name__,
                        e,
                        delay
                    )
                    time.sleep(delay)
                    if exponential:
                        delay *= 2

            if last_exception:
                raise last_exception

        return wrapper

    if callable(func):
        return decorator(func)
    return decorator


def execute_with_retry(
    func: Callable,
    *args,
    max_retries: int = None,
    initial_delay: float = None,
    exponential: bool = True,
    exceptions: tuple = (Exception,),
    **kwargs
):
    """Direct execution helper for functions without using decorators."""
    decorated = retry_with_backoff(
        max_retries=max_retries,
        initial_delay=initial_delay,
        exponential=exponential,
        exceptions=exceptions
    )(func)
    return decorated(*args, **kwargs)
