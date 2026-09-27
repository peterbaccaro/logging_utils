"""Utilities for logging application and generator lifecycle events."""

import contextvars
import functools
import logging
import sys
import time
from collections.abc import Callable, Generator, Iterator
from contextlib import contextmanager
from typing import Any, ParamSpec, TypeVar

_P = ParamSpec("_P")
_R = TypeVar("_R")
_YieldT = TypeVar("_YieldT")

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------


def configure_logging(level: int = logging.INFO) -> None:
    """
    Configure the root logger for application output.

    Args:
        level: Logging level to apply to the root logger.

    Adds a stream handler only when the root logger has no handlers. Normally
    called once from an application entry point or notebook/job.
    """
    root_logger = logging.getLogger()

    root_logger.setLevel(level)

    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)

        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")
        )

        root_logger.addHandler(handler)


# ---------------------------------------------------------------------------
# Correlation / run ID
# ---------------------------------------------------------------------------

_run_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "run_id",
    default=None,
)


def get_run_id() -> str | None:
    """
    Return the correlation ID for the current execution context.

    Returns:
        The current ID, or None if no ID has been set.
    """
    return _run_id.get()


@contextmanager
def run_context(run_id: str | None) -> Generator[None, None, None]:
    """Temporarily set the correlation ID for the current context.

    Args:
        run_id: ID to use inside the context, or None to clear it temporarily.

    Yields:
        None.

    The previous ID is restored when the context exits, including when an
    exception is raised. Contexts can be nested safely.
    """
    token = _run_id.set(run_id)
    try:
        yield
    finally:
        _run_id.reset(token)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_method_name(func: Callable[..., Any]) -> str:
    """Return a callable's qualified name.

    Args:
        func: Callable whose qualified name is retrieved.

    Returns:
        The callable's qualified name.
    """
    return func.__qualname__


def _get_result_metadata(result: Any) -> str:
    """
    Return useful metadata about a result without logging its contents.

    Args:
        result: Object whose type and length are inspected.

    Returns:
        A string containing the object's type and, when available, its length.
    """
    result_class = type(result)
    try:
        result_type = result_class.__name__
    except Exception:
        result_type = "unknown"

    if any(
        result_class is supported_type
        for supported_type in (
            str,
            bytes,
            bytearray,
            list,
            tuple,
            dict,
            set,
            frozenset,
            range,
            memoryview,
        )
    ):
        try:
            result_length = len(result)
            return f"type={result_type} length={result_length}"
        except Exception:
            pass

    return f"type={result_type}"


def _elapsed_ms(start_time: float) -> float:
    """Return elapsed time in milliseconds.

    Args:
        start_time: Start time from ``time.perf_counter()``.

    Returns:
        Elapsed time in milliseconds.
    """
    return (time.perf_counter() - start_time) * 1_000


def _get_run_id_text() -> str:
    """Return the current correlation ID as a log field.

    Returns:
        The ID as a ``run_id`` field, or an empty string when unset.
    """
    run_id = get_run_id()

    if run_id is None:
        return ""

    try:
        return f"run_id={run_id}"
    except Exception:
        return "run_id=<unavailable>"


def _is_enabled_for(logger: logging.Logger, level: int) -> bool:
    """Return whether a logger accepts a level, treating logger failures as disabled."""
    try:
        return logger.isEnabledFor(level)
    except Exception:
        return False


def _safe_log(
    logger: logging.Logger,
    level: int,
    message: str,
    *,
    exc_info: bool = False,
) -> None:
    """Emit a log message without allowing logging failures to escape."""
    try:
        if exc_info:
            logger.log(level, message, exc_info=True)
        else:
            logger.log(level, message)
    except Exception:
        pass


def _log_exception(
    logger: logging.Logger,
    method_name: str,
    log_exceptions: bool,
    start_time: float,
    items_yielded: int | None = None,
) -> None:
    """
    Log the current exception at ERROR level when enabled.

    Args:
        logger: Logger used to record the exception.
        method_name: Qualified name of the operation that failed.
        log_exceptions: Whether to emit the exception log.
        start_time: Operation start time from ``time.perf_counter()``.
        items_yielded: Number of items yielded before failure, if applicable.

    Logging errors are deliberately ignored so they never mask the application
    exception.
    """
    if not log_exceptions or not _is_enabled_for(logger, logging.ERROR):
        return

    parts = [
        f"EXCEPTION {method_name}",
    ]

    run_id_text = _get_run_id_text()

    if run_id_text:
        parts.append(run_id_text)

    if items_yielded is not None:
        parts.append(f"items_yielded={items_yielded}")

    parts.append(f"duration_ms={_elapsed_ms(start_time):.3f}")

    _safe_log(
        logger,
        logging.EXCEPTION,
        " ".join(parts),
        exc_info=True,
    )


def _log_start(
    *,
    logger: logging.Logger,
    log_level: int,
    method_name: str,
    log_start: bool,
) -> None:
    """Log an operation's start event without logging argument values.

    Args:
        logger: Logger used to record the event.
        log_level: Level for the start event.
        method_name: Qualified name of the operation.
        log_start: Whether to emit a start event.
    """

    if not log_start or not _is_enabled_for(logger, log_level):
        return

    parts = [
        f"START {method_name}",
    ]

    run_id_text = _get_run_id_text()

    if run_id_text:
        parts.append(run_id_text)

    _safe_log(
        logger,
        log_level,
        " ".join(parts),
    )


def _log_end(
    *,
    logger: logging.Logger,
    log_level: int,
    method_name: str,
    status: str,
    start_time: float,
    log_duration: bool,
    extra_fields: list[str] | None = None,
) -> None:
    """Build and log an operation's END event.

    Args:
        logger: Logger used to record the event.
        log_level: Level for the END event.
        method_name: Qualified name of the operation.
        status: Final operation status.
        start_time: Operation start time from ``time.perf_counter()``.
        log_duration: Whether to include total elapsed time.
        extra_fields: Additional fields to include after the run ID.
    """
    if not _is_enabled_for(logger, log_level):
        return

    parts = [
        f"END {method_name}",
        f"status={status}",
    ]

    run_id_text = _get_run_id_text()

    if run_id_text:
        parts.append(run_id_text)

    if extra_fields:
        parts.extend(extra_fields)

    if log_duration:
        parts.append(f"duration_ms={_elapsed_ms(start_time):.3f}")

    _safe_log(
        logger,
        log_level,
        " ".join(parts),
    )


def _log_yield(
    *,
    logger: logging.Logger,
    log_level: int,
    method_name: str,
    item_number: int,
    start_time: float,
    result: Any,
    interval_duration_ms: float | None = None,
    final: bool = False,
) -> None:
    """Build and log a YIELD event.

    Args:
        logger: Logger used to record the event.
        log_level: Level for the YIELD event.
        method_name: Qualified name of the generator.
        item_number: One-based position of this yielded item.
        start_time: Generator start time from ``time.perf_counter()``.
        result: Yielded value used only to collect type/length metadata.
        interval_duration_ms: Time since the previous logged yield, if enabled.
        final: Whether this is the final yield event.
    """
    if not _is_enabled_for(logger, log_level):
        return

    parts = [
        f"YIELD {method_name}",
        f"item={item_number}",
    ]

    if final:
        parts.append("final=true")

    run_id_text = _get_run_id_text()

    if run_id_text:
        parts.append(run_id_text)

    parts.append(_get_result_metadata(result))

    if interval_duration_ms is not None:
        parts.append(f"interval_duration_ms={interval_duration_ms:.3f}")

    parts.append(f"elapsed_ms={_elapsed_ms(start_time):.3f}")

    _safe_log(
        logger,
        log_level,
        " ".join(parts),
    )


# ---------------------------------------------------------------------------
# Normal method decorator
# ---------------------------------------------------------------------------


def log_method(
    *,
    log_start: bool = True,
    log_result_metadata: bool = False,
    log_exceptions: bool = False,
    log_duration: bool = False,
    log_level: int = logging.INFO,
) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]:
    """
    Decorate a regular callable with lifecycle logging.

    Args:
        log_start:
            Whether to log the START event.

        log_result_metadata:
            Whether to log the returned value's type and, when available, length.

        log_exceptions:
            Whether to log exceptions and their traceback at ERROR level.

        log_duration:
            Whether to log total execution duration.

        log_level:
            Logging level for normal lifecycle messages.

    Returns:
        A decorator that wraps a callable with the configured logging.
    """

    def apply_logging(
        func: Callable[_P, _R],
    ) -> Callable[_P, _R]:

        logger = logging.getLogger(func.__module__)
        method_name = _get_method_name(func)

        @functools.wraps(func)
        def logged_method(
            *args: _P.args,
            **kwargs: _P.kwargs,
        ) -> _R:

            start_time = time.perf_counter()

            _log_start(
                logger=logger,
                log_level=log_level,
                method_name=method_name,
                log_start=log_start,
            )

            try:
                result = func(
                    *args,
                    **kwargs,
                )

            except Exception:

                _log_exception(
                    logger=logger,
                    method_name=method_name,
                    log_exceptions=log_exceptions,
                    start_time=start_time,
                )

                _log_end(
                    logger=logger,
                    log_level=log_level,
                    method_name=method_name,
                    status="failed",
                    start_time=start_time,
                    log_duration=log_duration,
                )

                raise

            extra_fields = []

            if _is_enabled_for(logger, log_level):
                if log_result_metadata:
                    extra_fields.append(_get_result_metadata(result))

            _log_end(
                logger=logger,
                log_level=log_level,
                method_name=method_name,
                status="completed",
                start_time=start_time,
                log_duration=log_duration,
                extra_fields=extra_fields,
            )

            return result

        return logged_method

    return apply_logging


# ---------------------------------------------------------------------------
# Generator decorator
# ---------------------------------------------------------------------------


def log_generator(
    *,
    log_start: bool = True,
    log_yields: bool = False,
    log_yields_every: int | None = None,
    log_final_yield: bool = False,
    log_yield_interval_duration: bool = False,
    log_generator_metadata: bool = False,
    log_exceptions: bool = False,
    log_duration: bool = False,
    log_level: int = logging.INFO,
) -> Callable[
    [Callable[_P, Iterator[_YieldT]]],
    Callable[_P, Iterator[_YieldT]],
]:
    """
    Decorate a generator callable with lifecycle and yield logging.

    Generator execution is lazy: creating the generator emits no events. The
    START event and duration timing begin when iteration first advances it.

    Args:
        log_start:
            Whether to log the START event.

        log_yields:
            Whether to log metadata for individual yielded items.

        log_yields_every:
            Log every Nth item when yield logging is enabled. For example, 100
            logs items 100, 200, 300, and so on. None logs each item.

        log_final_yield:
            Whether to log the final item after successful completion if it was
            not already logged by the interval.

        log_yield_interval_duration:
            Whether to log time since the previous logged item. With
            log_yields_every, this measures time between logged checkpoints.

        log_generator_metadata:
            Whether to log `items_yielded` and, when available,
            `yielded_type` at the END event.

        log_exceptions:
            Whether to log exceptions and the number of items yielded before
            failure.

        log_duration:
            Whether to log total generator execution duration.

        log_level:
            Logging level for normal lifecycle messages.

    Returns:
        A decorator that wraps a generator with the configured logging.

    Raises:
        ValueError: If the yield interval is not greater than zero, or an option
            requiring yield logging is enabled while `log_yields` is false.
    """

    if log_yields_every is not None and log_yields_every <= 0:
        raise ValueError("log_yields_every must be greater than zero")

    if log_final_yield and not log_yields:
        raise ValueError("log_final_yield requires log_yields=True")

    if log_yield_interval_duration and not log_yields:
        raise ValueError("log_yield_interval_duration " "requires log_yields=True")

    def apply_logging(
        func: Callable[_P, Iterator[_YieldT]],
    ) -> Callable[_P, Iterator[_YieldT]]:

        logger = logging.getLogger(func.__module__)
        method_name = _get_method_name(func)

        @functools.wraps(func)
        def logged_generator(
            *args: _P.args,
            **kwargs: _P.kwargs,
        ) -> Iterator[_YieldT]:

            start_time = time.perf_counter()

            previous_logged_yield_time = start_time

            _log_start(
                logger=logger,
                log_level=log_level,
                method_name=method_name,
                log_start=log_start,
            )

            count = 0
            last_yielded_result: Any = None
            yielded_type: type[Any] | None = None
            mixed_yield_types = False
            has_yielded = False
            last_logged_yield_count = 0

            status = "completed"

            try:

                for result in func(
                    *args,
                    **kwargs,
                ):

                    count += 1
                    has_yielded = True
                    last_yielded_result = result

                    result_type = type(result)
                    if yielded_type is None:
                        yielded_type = result_type
                    elif result_type is not yielded_type:
                        mixed_yield_types = True

                    should_log_yield = log_yields and (
                        log_yields_every is None or count % log_yields_every == 0
                    )

                    if should_log_yield and _is_enabled_for(logger, log_level):

                        interval_duration_ms = None
                        if log_yield_interval_duration:
                            now = time.perf_counter()
                            interval_duration_ms = (
                                now - previous_logged_yield_time
                            ) * 1_000
                            previous_logged_yield_time = now

                        _log_yield(
                            logger=logger,
                            log_level=log_level,
                            method_name=method_name,
                            item_number=count,
                            start_time=start_time,
                            result=result,
                            interval_duration_ms=interval_duration_ms,
                        )

                        last_logged_yield_count = count

                    yield result

            except GeneratorExit:

                status = "closed"

                raise

            except Exception:

                status = "failed"

                _log_exception(
                    logger=logger,
                    method_name=method_name,
                    log_exceptions=log_exceptions,
                    start_time=start_time,
                    items_yielded=count,
                )

                raise

            finally:

                # -----------------------------------------------------------
                # Optionally log the final yielded item
                #
                # Only valid when the generator completed normally.
                # -----------------------------------------------------------

                if (
                    status == "completed"
                    and log_final_yield
                    and log_yields
                    and has_yielded
                    and count != last_logged_yield_count
                    and _is_enabled_for(logger, log_level)
                ):

                    _log_yield(
                        logger=logger,
                        log_level=log_level,
                        method_name=method_name,
                        item_number=count,
                        start_time=start_time,
                        result=last_yielded_result,
                        final=True,
                    )

                # -----------------------------------------------------------
                # END
                # -----------------------------------------------------------

                extra_fields = []

                if log_generator_metadata and _is_enabled_for(logger, log_level):
                    extra_fields.append(f"items_yielded={count}")
                    if yielded_type is not None:
                        yielded_type_name = (
                            "mixed" if mixed_yield_types else yielded_type.__name__
                        )
                        extra_fields.append(f"yielded_type={yielded_type_name}")

                _log_end(
                    logger=logger,
                    log_level=log_level,
                    method_name=method_name,
                    status=status,
                    start_time=start_time,
                    log_duration=log_duration,
                    extra_fields=extra_fields,
                )

        return logged_generator

    return apply_logging
