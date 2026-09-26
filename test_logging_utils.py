import logging
from collections.abc import Generator, Iterator
from typing import Any, cast
from unittest.mock import patch

import pytest

import logging_utils
from logging_utils import (
    _elapsed_ms,
    _format_value,
    _get_result_metadata,
    _get_run_id_text,
    _is_enabled_for,
    _normalise_names,
    _safe_log,
    _validate_max_length,
    configure_logging,
    get_run_id,
    log_generator,
    log_method,
    run_context,
)


@pytest.mark.parametrize(
    ("start_time", "current_time", "expected_ms"),
    [
        (10.0, 10.0, 0.0),
        (10.0, 10.125, 125.0),
        (5.0, 5.75, 750.0),
    ],
)
def test_elapsed_ms(start_time: float, current_time: float, expected_ms: float) -> None:
    with patch("logging_utils.time.perf_counter", return_value=current_time):
        assert _elapsed_ms(start_time) == pytest.approx(expected_ms)


def test_configure_logging_adds_only_one_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root_logger = logging.Logger("test-root")
    original_get_logger = logging_utils.logging.getLogger

    def get_logger(*args: Any) -> logging.Logger:
        if args:
            return original_get_logger(*args)
        return root_logger

    monkeypatch.setattr(logging_utils.logging, "getLogger", get_logger)

    configure_logging(logging.DEBUG)
    first_handler = root_logger.handlers[0]
    configure_logging(logging.WARNING)

    assert root_logger.level == logging.WARNING
    assert root_logger.handlers == [first_handler]
    assert isinstance(first_handler, logging.StreamHandler)


def test_run_context_restores_nested_values_after_exception() -> None:
    original_run_id = get_run_id()

    with run_context("outer"):
        assert get_run_id() == "outer"
        with pytest.raises(RuntimeError):
            with run_context("inner"):
                assert get_run_id() == "inner"
                raise RuntimeError("stop")
        assert get_run_id() == "outer"

    assert get_run_id() == original_run_id


def test_normalise_names_is_case_insensitive() -> None:
    assert _normalise_names({"Password", "API_KEY"}) == {"password", "api_key"}


@pytest.mark.parametrize("value", [0, -1])
def test_validate_max_length_rejects_non_positive_values(value: int) -> None:
    with pytest.raises(ValueError, match="max_length must be greater than zero"):
        _validate_max_length("max_length", value)


def test_format_value_truncates_to_the_requested_length() -> None:
    formatted = _format_value("x" * 40, 20)

    assert len(formatted) == 20
    assert formatted.endswith("... [TRUNCATED]")
    assert len(_format_value("value", 5)) == 5


def test_format_value_contains_repr_failure() -> None:
    class BadRepr:
        def __repr__(self) -> str:
            raise RuntimeError("repr failed")

    assert _format_value(BadRepr(), 100) == "<unable to represent: RuntimeError>"


def test_result_metadata_only_calls_len_on_exact_builtin_types() -> None:
    class SizedList(list):
        def __len__(self) -> int:
            raise AssertionError("custom __len__ must not run")

    assert _get_result_metadata([1, 2]) == "type=list length=2"
    assert _get_result_metadata(SizedList([1, 2])) == "type=SizedList"

    released_view = memoryview(b"data")
    released_view.release()
    assert _get_result_metadata(released_view) == "type=memoryview"


def test_get_run_id_text_formats_and_contains_bad_values() -> None:
    class BadFormatString(str):
        def __format__(self, format_spec: str) -> str:
            raise RuntimeError("format failed")

    assert _get_run_id_text() == ""
    with run_context("run-1"):
        assert _get_run_id_text() == "run_id=run-1"
    with run_context(BadFormatString("run-2")):
        assert _get_run_id_text() == "run_id=<unavailable>"


def test_is_enabled_for_contains_logger_errors() -> None:
    class BadLevelLogger(logging.Logger):
        def isEnabledFor(self, level: int) -> bool:
            raise RuntimeError("level check failed")

    assert not _is_enabled_for(BadLevelLogger("bad-level"), logging.INFO)


def test_safe_log_contains_logger_errors() -> None:
    class BadLogger(logging.Logger):
        def log(
            self, level: int, message: object, *args: object, **kwargs: object
        ) -> None:
            raise RuntimeError("handler failed")

    logger = BadLogger("bad-log")
    _safe_log(cast(logging.Logger, logger), logging.INFO, "message")
    _safe_log(
        cast(logging.Logger, logger),
        logging.ERROR,
        "failure",
        exc_info=True,
    )


def test_log_method_redacts_arguments_and_logs_result(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)

    @log_method(log_args=True, log_result=True, log_result_metadata=True)
    def process(token: str, item: str) -> list[str]:
        return [item]

    assert process("hidden-token", "visible") == ["visible"]
    assert "token': '[REDACTED]'" in caplog.text
    assert "hidden-token" not in caplog.text
    assert (
        "END test_log_method_redacts_arguments_and_logs_result.<locals>.process "
        "status=completed type=list length=1 result=['visible']"
    ) in caplog.text


def test_log_method_logs_exceptions_by_default(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)

    @log_method()
    def fail() -> None:
        raise ValueError("method failure")

    with pytest.raises(ValueError, match="method failure"):
        fail()

    assert (
        "EXCEPTION test_log_method_logs_exceptions_by_default.<locals>.fail"
        in caplog.text
    )
    assert (
        "END test_log_method_logs_exceptions_by_default.<locals>.fail status=failed"
        in caplog.text
    )


def test_log_method_can_disable_exception_logging(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)

    @log_method(log_exceptions=False)
    def fail() -> None:
        raise ValueError("method failure")

    with pytest.raises(ValueError, match="method failure"):
        fail()

    assert "EXCEPTION" not in caplog.text
    assert (
        "END test_log_method_can_disable_exception_logging.<locals>.fail status=failed"
        in caplog.text
    )


@pytest.mark.parametrize(
    ("max_arg_length", "max_result_length"),
    [(0, 2_000), (2_000, -1)],
)
def test_log_method_rejects_invalid_lengths(
    max_arg_length: int,
    max_result_length: int,
) -> None:
    with pytest.raises(ValueError):
        log_method(
            max_arg_length=max_arg_length,
            max_result_length=max_result_length,
        )


def test_log_generator_defers_start_until_iteration(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)

    @log_generator()
    def values():
        yield 1

    generated = values()
    assert "START" not in caplog.text
    assert next(generated) == 1
    assert (
        "START test_log_generator_defers_start_until_iteration.<locals>.values"
        in caplog.text
    )
    cast(Generator[int, None, None], generated).close()
    assert "status=closed" in caplog.text


def test_log_generator_logs_periodic_and_final_yields(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)

    @log_generator(
        log_yields=True,
        log_yields_every=2,
        log_yield_result=True,
        log_final_yield=True,
        log_yield_interval_duration=True,
        log_generator_metadata=True,
        log_duration=True,
    )
    def values() -> Iterator[int]:
        yield 1
        yield 2
        yield 3

    assert list(values()) == [1, 2, 3]
    messages = [record.getMessage() for record in caplog.records]
    yield_messages = [message for message in messages if message.startswith("YIELD ")]

    assert len(yield_messages) == 2
    assert "item=2" in yield_messages[0]
    assert "result=2" in yield_messages[0]
    assert "interval_duration_ms=" in yield_messages[0]
    assert "item=3 final=true" in yield_messages[1]
    assert "interval_duration_ms=" not in yield_messages[1]
    assert "items_yielded=3 yielded_type=int" in messages[-1]
    assert "duration_ms=" in messages[-1]


def test_log_generator_reports_mixed_and_empty_metadata(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)

    @log_generator(log_generator_metadata=True)
    def mixed() -> Iterator[int | str]:
        yield 1
        yield "two"

    @log_generator(log_generator_metadata=True)
    def empty() -> Iterator[None]:
        if False:
            yield None

    list(mixed())
    list(empty())
    end_messages = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("END ")
    ]

    assert "items_yielded=2 yielded_type=mixed" in end_messages[0]
    assert "items_yielded=0" in end_messages[1]
    assert "yielded_type=" not in end_messages[1]
    assert all("result_type=generator" not in message for message in end_messages)


def test_log_generator_logs_exceptions_and_yield_count(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)

    @log_generator(log_generator_metadata=True)
    def fail() -> Iterator[int]:
        yield 1
        raise RuntimeError("generator failure")

    with pytest.raises(RuntimeError, match="generator failure"):
        list(fail())

    assert "EXCEPTION test_log_generator_logs_exceptions_and_yield_count" in caplog.text
    assert "items_yielded=1" in caplog.text
    assert "status=failed items_yielded=1 yielded_type=int" in caplog.text


@pytest.mark.parametrize(
    "kwargs",
    [
        {"log_yields_every": 0},
        {"log_yield_result": True},
        {"log_final_yield": True},
        {"log_yield_interval_duration": True},
        {"max_arg_length": 0},
        {"max_yield_length": -1},
    ],
)
def test_log_generator_rejects_invalid_options(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        log_generator(**kwargs)


def test_logging_failures_do_not_change_wrapped_behavior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BadLogger(logging.Logger):
        def isEnabledFor(self, level: int) -> bool:
            return True

        def log(
            self, level: int, message: object, *args: object, **kwargs: object
        ) -> None:
            raise RuntimeError("logging failure")

    original_get_logger = logging_utils.logging.getLogger
    broken_logger = BadLogger("broken")

    def get_logger(*args: Any) -> logging.Logger:
        if args:
            return cast(logging.Logger, broken_logger)
        return original_get_logger()

    monkeypatch.setattr(logging_utils.logging, "getLogger", get_logger)

    @log_method(log_args=True, log_result=True, log_result_metadata=True)
    def method(value: object) -> object:
        return value

    @log_generator(log_yields=True, log_yield_result=True, log_generator_metadata=True)
    def generator() -> Iterator[list[int]]:
        yield [1]

    value = object()
    assert method(value) is value
    assert list(generator()) == [[1]]
