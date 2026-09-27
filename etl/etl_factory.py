from typing import Any, Iterator

from etl.components.source_reader import SourceReader
from etl.components.source_to_target_transformer import SourceToTargetTransformer
from etl.components.target_writer import TargetWriter
from etl.etl_orchestrator import EtlOrchestrator
from etl.types.etl_config import EtlConfig

from utils.logging_utils_simple import log_method


class EtlFactory:
    """
    Creates and wires the ETL components.

    This keeps construction/configuration separate from orchestration.
    """

    @staticmethod
    @log_method(
        log_result_metadata=True,
        log_exceptions=True,
        log_duration=True,
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
