"""
main.py

Example ETL application using the logging decorators.

Architecture:

    main.py
       |
       v
    EtlFactory
       |
       +----> SourceReader
       |
       +----> SourceToTargetTransformer
       |
       +----> TargetWriter
       |
       v
    EtlOrchestrator
       |
       +----> read()
       |
       +----> transform()
       |
       +----> write()
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Iterator

from logging_utils import (configure_logging, log_generator, log_method)

# ============================================================================
# Configuration
# ============================================================================


@dataclass(frozen=True)
class EtlConfig:
    """ETL runtime configuration."""

    environment: str
    source_name: str
    target_name: str
    batch_size: int = 100


# ============================================================================
# Source Reader
# ============================================================================


class SourceReader:
    """
    Reads records from the source system.

    In a real implementation this could call:
        - REST API
        - Azure SQL
        - MongoDB
        - SFTP
        - another data source
    """

    def __init__(
        self,
        source_name: str,
        batch_size: int,
    ) -> None:
        self.source_name = source_name
        self.batch_size = batch_size

    @log_generator(
        log_args=True,
        log_yields=True,
        log_yields_every=100,
        log_yield_result=False,
        log_final_yield=True,
        log_yield_interval_duration=True,
        log_result_metadata=True,
        log_exceptions=True,
        log_duration=True,
    )
    def read(self) -> Iterator[dict[str, Any]]:
        """
        Read records from the source.

        A generator is used so records can be processed incrementally
        instead of loading everything into memory.
        """

        # Example source data.
        # In reality this could be paginated API requests.
        for record_id in range(1, 237):

            yield {
                "source_id": record_id,
                "customer": f"Customer {record_id}",
                "amount": record_id * 10.50,
                "currency": "GBP",
            }


# ============================================================================
# Source -> Target Transformer
# ============================================================================


class SourceToTargetTransformer:
    """
    Transforms source records into the target data model.
    """

    @log_generator(
        log_yields=True,
        log_yields_every=100,
        log_final_yield=True,
        log_yield_interval_duration=True,
        log_result_metadata=True,
        log_exceptions=True,
        log_duration=True,
    )
    def transform(
        self,
        records: Iterator[dict[str, Any]],
    ) -> Iterator[dict[str, Any]]:
        """
        Transform source records one at a time.
        """

        for record in records:

            yield {
                "id": record["source_id"],
                "customer_name": record["customer"],
                "amount_gbp": record["amount"],
                "source_currency": record["currency"],
            }


# ============================================================================
# Target Writer
# ============================================================================


class TargetWriter:
    """
    Writes transformed records to the target system.
    """

    def __init__(
        self,
        target_name: str,
        batch_size: int,
    ) -> None:
        self.target_name = target_name
        self.batch_size = batch_size

    @log_method(
        log_args=False,
        log_result_metadata=True,
        log_exceptions=True,
        log_duration=True,
    )
    def write(
        self,
        records: Iterator[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Write records to the target.

        The example batches records before writing.

        A real implementation could write to:
            - Delta
            - Azure SQL
            - MongoDB
            - another REST API
        """

        batch: list[dict[str, Any]] = []
        records_written = 0
        batches_written = 0

        for record in records:

            batch.append(record)

            if len(batch) >= self.batch_size:

                self._write_batch(batch)

                records_written += len(batch)
                batches_written += 1

                batch.clear()

        # Write remaining records.
        if batch:
            self._write_batch(batch)

            records_written += len(batch)
            batches_written += 1

        return {
            "target": self.target_name,
            "records_written": records_written,
            "batches_written": batches_written,
        }

    @log_method(
        log_args=False,
        log_result_metadata=True,
        log_exceptions=True,
        log_duration=True,
    )
    def _write_batch(
        self,
        batch: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Write one batch.

        Replace this implementation with the actual target write.
        """

        # Example only.
        return {
            "records": len(batch),
        }


# ============================================================================
# ETL Orchestrator
# ============================================================================


class EtlOrchestrator:
    """
    Coordinates the ETL process.

    The orchestrator should contain the workflow rather than the
    implementation details of reading, transforming or writing.
    """

    def __init__(
        self,
        source_reader: SourceReader,
        transformer: SourceToTargetTransformer,
        target_writer: TargetWriter,
    ) -> None:
        self.source_reader = source_reader
        self.transformer = transformer
        self.target_writer = target_writer

    @log_method(
        log_start=True,
        log_args=False,
        log_result_metadata=True,
        log_exceptions=True,
        log_duration=True,
    )
    def run(self) -> dict[str, Any]:
        """
        Execute the complete ETL pipeline.
        """

        # Source
        source_records = self.source_reader.read()

        # Source -> Target transformation
        target_records = self.transformer.transform(source_records)

        # Target
        result = self.target_writer.write(target_records)

        return result


# ============================================================================
# ETL Factory
# ============================================================================


class EtlFactory:
    """
    Creates and wires the ETL components.

    This keeps construction/configuration separate from orchestration.
    """

    @staticmethod
    @log_method(
        log_args=True,
        log_result_metadata=True,
        log_exceptions=True,
        log_duration=True,
        redact_args={"password", "token", "secret"},
    )
    def create(
        config: EtlConfig,
    ) -> EtlOrchestrator:

        source_reader = SourceReader(
            source_name=config.source_name,
            batch_size=config.batch_size,
        )

        transformer = SourceToTargetTransformer()

        target_writer = TargetWriter(
            target_name=config.target_name,
            batch_size=config.batch_size,
        )

        return EtlOrchestrator(
            source_reader=source_reader,
            transformer=transformer,
            target_writer=target_writer,
        )


# ============================================================================
# Main
# ============================================================================


def main() -> None:
    """
    Application entry point.
    """

    configure_logging()

    # In a real Databricks implementation this could come from:
    #   - job parameters
    #   - widgets
    #   - environment configuration
    #   - ETL control tables
    config = EtlConfig(
        environment="dev",
        source_name="source_api",
        target_name="target_delta",
        batch_size=100,
    )

    # Generate one correlation/run ID for the complete ETL execution.
    # run_id = str(uuid.uuid4())

    # set_run_id(run_id)
    # set_run_id("")

    orchestrator = EtlFactory.create(config)

    result = orchestrator.run()

    print(f"ETL completed: {result}")


if __name__ == "__main__":
    main()
