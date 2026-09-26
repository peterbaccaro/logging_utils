"""Utilities for logging application and generator lifecycle events."""

import contextvars
import functools
import inspect
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
# Constants
# ---------------------------------------------------------------------------

_REDACTED = "[REDACTED]"

_DEFAULT_REDACT_ARGS = {
    "password",
    "passwd",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "authorization",
}


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


def _normalise_names(names: set[str]) -> set[str]:
    """Normalize names for case-insensitive comparison.

    Args:
        names: Names to normalize.

    Returns:
        A set containing the lowercase names.
    """
    return {name.lower() for name in names}


def _validate_max_length(
    name: str,
    value: int,
) -> None:
    """Validate a maximum length configuration value.

    Args:
        name: Configuration option name used in the error message.
        value: Maximum length to validate.

    Raises:
        ValueError: If value is not greater than zero.
    """
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")


def _format_value(
    value: Any,
    max_length: int,
) -> str:
    """
    Return a bounded representation of a value.

    Args:
        value: Object to represent.
        max_length: Maximum number of characters in the returned string.

    Returns:
        The object's representation, truncated to at most max_length characters.
    """
    try:
        result = repr(value)
    except Exception as exc:
        return f"<unable to represent: {type(exc).__name__}>"

    if len(result) <= max_length:
        return result

    suffix = "... [TRUNCATED]"

    if max_length <= len(suffix):
        return suffix[:max_length]

    return f"{result[:max_length - len(suffix)]}" f"{suffix}"


def _get_result_metadata(result: Any) -> str:
    """
    Return useful metadata about a result without logging its contents.

    Args:
        result: Object whose type and length are inspected.

    Returns:
        A string containing the object's type and, when available, its length.
    """
    result_type = type(result).__name__

    try:
        result_length = len(result)
    except Exception:
        result_length = None

    metadata = f"type={result_type}"

    if result_length is not None:
        metadata += f" length={result_length}"

    return metadata


def _format_duration(
    start_time: float,
) -> str:
    """Format total elapsed time in milliseconds.

    Args:
        start_time: Start time from ``time.perf_counter()``.

    Returns:
        Elapsed time as a ``duration_ms`` log field.
    """
    duration_ms = (time.perf_counter() - start_time) * 1_000

    return f"duration_ms={duration_ms:.3f}"


def _format_elapsed(
    start_time: float,
) -> str:
    """Format elapsed time since operation start.

    Args:
        start_time: Start time from ``time.perf_counter()``.

    Returns:
        Elapsed time as an ``elapsed_ms`` log field.
    """
    elapsed_ms = (time.perf_counter() - start_time) * 1_000

    return f"elapsed_ms={elapsed_ms:.3f}"


def _get_run_id_text() -> str:
    """Return the current correlation ID as a log field.

    Returns:
        The ID as a ``run_id`` field, or an empty string when unset.
    """
    run_id = get_run_id()

    if run_id is None:
        return ""

    return f"run_id={run_id}"


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
    if not log_exceptions or not logger.isEnabledFor(logging.ERROR):
        return

    parts = [
        f"EXCEPTION {method_name}",
    ]

    run_id_text = _get_run_id_text()

    if run_id_text:
        parts.append(run_id_text)

    if items_yielded is not None:
        parts.append(f"items_yielded={items_yielded}")

    parts.append(_format_duration(start_time))

    try:
        logger.exception(
            " ".join(parts),
            exc_info=True,
        )
    except Exception:
        # Logging must never mask the original exception.
        pass


def _log_start(
    *,
    logger: logging.Logger,
    log_level: int,
    method_name: str,
    signature: inspect.Signature,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    log_start: bool,
    log_args: bool,
    redact_args: set[str],
    max_arg_length: int,
) -> None:
    """Log an operation's start event and optionally its arguments.

    Args:
        logger: Logger used to record the event.
        log_level: Level for the start event.
        method_name: Qualified name of the operation.
        signature: Callable signature used to bind arguments.
        args: Positional arguments passed to the operation.
        kwargs: Keyword arguments passed to the operation.
        log_start: Whether to emit a start event.
        log_args: Whether to include argument values.
        redact_args: Lowercase parameter names whose values must be redacted.
        max_arg_length: Maximum length for each formatted argument value.
    """

    if not log_start or not logger.isEnabledFor(log_level):
        return

    parts = [
        f"START {method_name}",
    ]

    run_id_text = _get_run_id_text()

    if run_id_text:
        parts.append(run_id_text)

    if log_args:
        try:
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()

            parameters = {}

            for name, value in bound.arguments.items():

                if name in {"self", "cls"}:
                    continue

                if name.lower() in redact_args:
                    parameters[name] = _REDACTED
                else:
                    parameters[name] = _format_value(
                        value,
                        max_arg_length,
                    )

            parts.append(f"parameters={parameters}")

        except Exception as exc:
            parts.append("parameters=" f"<unable to format: {type(exc).__name__}>")

    logger.log(
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
    if not logger.isEnabledFor(log_level):
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
        parts.append(_format_duration(start_time))

    logger.log(
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
    log_yield_result: bool,
    max_yield_length: int,
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
        result: Yielded value to describe and optionally include.
        log_yield_result: Whether to include the bounded value representation.
        max_yield_length: Maximum length of the value representation.
        interval_duration_ms: Time since the previous logged yield, if enabled.
        final: Whether this is the final yield event.
    """
    if not logger.isEnabledFor(log_level):
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

    if log_yield_result:
        parts.append(f"result={_format_value(result, max_yield_length)}")

    if interval_duration_ms is not None:
        parts.append(f"interval_duration_ms={interval_duration_ms:.3f}")

    parts.append(_format_elapsed(start_time))

    logger.log(
        log_level,
        " ".join(parts),
    )


# ---------------------------------------------------------------------------
# Normal method decorator
# ---------------------------------------------------------------------------


def log_method(
    *,
    log_start: bool = True,
    log_args: bool = False,
    log_result: bool = False,
    log_result_metadata: bool = False,
    log_exceptions: bool = True,
    log_duration: bool = False,
    log_level: int = logging.INFO,
    redact_args: set[str] | None = None,
    max_arg_length: int = 2_000,
    max_result_length: int = 2_000,
) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]:
    """
    Decorate a regular callable with lifecycle logging.

    Args:
        log_start:
            Whether to log the START event.

        log_args:
            Whether to log method arguments, with sensitive names redacted.

        log_result:
            Whether to log the bounded representation of the returned value.

        log_result_metadata:
            Whether to log the returned value's type and, when available, length.

        log_exceptions:
            Whether to log exceptions and their traceback at ERROR level.
            Enabled by default.

        log_duration:
            Whether to log total execution duration.

        log_level:
            Logging level for normal lifecycle messages.

        redact_args:
            Additional parameter names to redact, matched case-insensitively
            and added to the default sensitive names.

        max_arg_length:
            Maximum length of each logged argument representation.

        max_result_length:
            Maximum length of the logged result representation.

    Returns:
        A decorator that wraps a callable with the configured logging.

    Raises:
        ValueError: If either maximum length is not greater than zero.
    """

    _validate_max_length(
        "max_arg_length",
        max_arg_length,
    )

    _validate_max_length(
        "max_result_length",
        max_result_length,
    )

    # Custom redaction names EXTEND the defaults.
    redact_args_normalised = _normalise_names(
        _DEFAULT_REDACT_ARGS | (set() if redact_args is None else set(redact_args))
    )

    def apply_logging(
        func: Callable[_P, _R],
    ) -> Callable[_P, _R]:

        logger = logging.getLogger(func.__module__)
        signature = inspect.signature(func)

        @functools.wraps(func)
        def logged_method(
            *args: _P.args,
            **kwargs: _P.kwargs,
        ) -> _R:

            method_name = _get_method_name(func)
            start_time = time.perf_counter()

            _log_start(
                logger=logger,
                log_level=log_level,
                method_name=method_name,
                signature=signature,
                args=args,
                kwargs=kwargs,
                log_start=log_start,
                log_args=log_args,
                redact_args=redact_args_normalised,
                max_arg_length=max_arg_length,
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

            if logger.isEnabledFor(log_level):
                if log_result_metadata:
                    extra_fields.append(_get_result_metadata(result))

                if log_result:
                    extra_fields.append(f"result={_format_value(
                        result,
                        max_result_length,
                    )}")

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
    log_args: bool = False,
    log_yields: bool = False,
    log_yields_every: int | None = None,
    log_yield_result: bool = False,
    log_final_yield: bool = False,
    log_yield_interval_duration: bool = False,
    log_result_metadata: bool = False,
    log_exceptions: bool = True,
    log_duration: bool = False,
    log_level: int = logging.INFO,
    redact_args: set[str] | None = None,
    max_arg_length: int = 2_000,
    max_yield_length: int = 2_000,
) -> Callable[
    [Callable[_P, Iterator[_YieldT]]],
    Callable[_P, Iterator[_YieldT]],
]:
    """
    Decorate a generator callable with lifecycle and yield logging.

    Args:
        log_start:
            Whether to log the START event.

        log_args:
            Whether to log generator arguments, with sensitive names redacted.

        log_yields:
            Whether to enable logging of individual yielded items.

        log_yields_every:
            Log every Nth item when yield logging is enabled. For example, 100
            logs items 100, 200, 300, and so on. None logs each item.

        log_yield_result:
            Whether to include the bounded representation of each logged item.

        log_final_yield:
            Whether to log the final item after successful completion if it was
            not already logged by the interval.

        log_yield_interval_duration:
            Whether to log time since the previous logged item. With
            log_yields_every, this measures time between logged checkpoints.

        log_result_metadata:
            Whether to log generator metadata and the number of items yielded
            at the END event.

        log_exceptions:
            Whether to log exceptions and the number of items yielded before
            failure. Enabled by default.

        log_duration:
            Whether to log total generator execution duration.

        log_level:
            Logging level for normal lifecycle messages.

        redact_args:
            Additional parameter names to redact, matched case-insensitively
            and added to the default sensitive names.

        max_arg_length:
            Maximum length of each logged argument representation.

        max_yield_length:
            Maximum length of each logged yielded-value representation.

    Returns:
        A decorator that wraps a generator with the configured logging.

    Raises:
        ValueError: If a maximum length is not greater than zero, the yield
            interval is not greater than zero, or a yield logging option is
            enabled while ``log_yields`` is false.
    """

    if log_yields_every is not None and log_yields_every <= 0:
        raise ValueError("log_yields_every must be greater than zero")

    if log_yield_result and not log_yields:
        raise ValueError("log_yield_result requires log_yields=True")

    if log_final_yield and not log_yields:
        raise ValueError("log_final_yield requires log_yields=True")

    if log_yield_interval_duration and not log_yields:
        raise ValueError("log_yield_interval_duration " "requires log_yields=True")

    _validate_max_length(
        "max_arg_length",
        max_arg_length,
    )

    _validate_max_length(
        "max_yield_length",
        max_yield_length,
    )

    # Custom redaction names EXTEND the defaults.
    redact_args_normalised = _normalise_names(
        _DEFAULT_REDACT_ARGS | (set() if redact_args is None else set(redact_args))
    )

    def apply_logging(
        func: Callable[_P, Iterator[_YieldT]],
    ) -> Callable[_P, Iterator[_YieldT]]:

        logger = logging.getLogger(func.__module__)
        signature = inspect.signature(func)

        @functools.wraps(func)
        def logged_generator(
            *args: _P.args,
            **kwargs: _P.kwargs,
        ) -> Iterator[_YieldT]:

            method_name = _get_method_name(func)
            start_time = time.perf_counter()

            previous_logged_yield_time = start_time

            _log_start(
                logger=logger,
                log_level=log_level,
                method_name=method_name,
                signature=signature,
                args=args,
                kwargs=kwargs,
                log_start=log_start,
                log_args=log_args,
                redact_args=redact_args_normalised,
                max_arg_length=max_arg_length,
            )

            count = 0
            last_yielded_result: Any = None
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

                    should_log_yield = log_yields and (
                        log_yields_every is None or count % log_yields_every == 0
                    )

                    if should_log_yield and logger.isEnabledFor(log_level):

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
                            log_yield_result=log_yield_result,
                            max_yield_length=max_yield_length,
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
                    and logger.isEnabledFor(log_level)
                ):

                    _log_yield(
                        logger=logger,
                        log_level=log_level,
                        method_name=method_name,
                        item_number=count,
                        start_time=start_time,
                        result=last_yielded_result,
                        log_yield_result=log_yield_result,
                        max_yield_length=max_yield_length,
                        final=True,
                    )

                # -----------------------------------------------------------
                # END
                # -----------------------------------------------------------

                extra_fields = []

                if log_result_metadata and logger.isEnabledFor(log_level):
                    extra_fields.extend(
                        [
                            "result_type=generator",
                            f"items_yielded={count}",
                        ]
                    )

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
