import logging
from typing import Any, Iterator

from utils.logging_utils_simple import log_generator

logger = logging.getLogger(__name__)


class AcmeApiService:
    """
    Reads pages of records from a source REST API.
    """

    def __init__(
        self,
        source_name: str,
        batch_size: int,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than zero")

        self.source_name = source_name
        self.batch_size = batch_size

    @log_generator(
        log_yields=True,
        log_yields_every=1,
        log_final_yield=True,
        log_yield_interval_duration=True,
    )
    def get_customers_iter(self) -> Iterator[list[dict[str, Any]]]:
        """
        Read pages of records from the source REST API.

        Each yielded list represents one page from the source API and contains
        at most ``batch_size`` records.
        """
        logger.info("Starting to read customer pages from source API: %s", self.source_name)

        for page_start in range(1, 237, self.batch_size):
            page_end = min(page_start + self.batch_size, 237)
            yield [
                {
                    "source_id": record_id,
                    "customer": f"Customer {record_id}",
                    "amount": record_id * 10.50,
                    "currency": "GBP",
                }
                for record_id in range(page_start, page_end)
            ]
