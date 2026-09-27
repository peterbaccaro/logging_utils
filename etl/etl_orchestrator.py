from typing import Any

from etl.components.source_reader import SourceReader
from etl.components.source_to_target_transformer import SourceToTargetTransformer
from etl.components.target_writer import TargetWriter
from utils.logging_utils_simple import log_method


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
