from typing import Any, Iterator

from etl.components.acme_api_service import AcmeApiService
from etl.components.source_to_target_transformer import SourceToTargetTransformer
from etl.components.target_writer import TargetWriter
from etl.example_databricks_task import ExampleDatabricksTask
from etl.types.etl_config import EtlConfig
from utils.logging_utils_simple import log_method


class ExampleDatabricksTaskFactory:
    """
    Creates and wires the tasks for a Databricks job.

    This keeps construction/configuration separate from orchestration.
    """

    @staticmethod
    @log_method(
        log_exceptions=True,
    )
    def create(
        config: EtlConfig,
    ) -> ExampleDatabricksTask:

        api_service = AcmeApiService(
            source_name=config.source_name,
            batch_size=config.batch_size,
        )

        transformer = SourceToTargetTransformer()

        target_writer = TargetWriter(
            target_name=config.target_name,
            batch_size=config.batch_size,
        )

        return ExampleDatabricksTask(
            api_service=api_service,
            transformer=transformer,
            target_writer=target_writer,
        )
