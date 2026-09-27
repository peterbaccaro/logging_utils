from typing import Any, Iterator

from utils.logging_utils_simple import log_generator


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
        log_yields=True,
        log_yields_every=100,
        log_final_yield=True,
        log_yield_interval_duration=True,
        log_generator_metadata=True,
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
