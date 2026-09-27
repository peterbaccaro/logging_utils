from typing import Any

from etl.components.acme_api_service import AcmeApiService
from etl.components.source_to_target_transformer import SourceToTargetTransformer
from etl.components.target_writer import TargetWriter
from utils.logging_utils_simple import log_method


class ExampleDatabricksTask:
    """
    Coordinates the ETL process.

    The orchestrator should contain the workflow rather than the
    implementation details of reading, transforming or writing.
    """

    def __init__(
        self,
        api_service: AcmeApiService,
        transformer: SourceToTargetTransformer,
        target_writer: TargetWriter,
    ) -> None:
        self.api_service = api_service
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
        customer_pages = self.api_service.get_customers_iter()

        # Source -> Target transformation
        target_records = self.transformer.transform(customer_pages)

        # Target
        result = self.target_writer.write(target_records)

        return result
