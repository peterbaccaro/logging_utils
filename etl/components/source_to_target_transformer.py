from typing import Any, Iterator

from utils.logging_utils_simple import log_generator


class SourceToTargetTransformer:
    """
    Transforms source records into the target data model.
    """

    @log_generator(
        log_yields=True,
        log_yields_every=100,
        log_final_yield=True,
        log_yield_interval_duration=True,
    )
    def transform(
        self,
        pages: Iterator[list[dict[str, Any]]],
    ) -> Iterator[dict[str, Any]]:
        """
        Transform records from each source page one at a time.
        """

        for page in pages:
            for record in page:
                yield {
                    "id": record["source_id"],
                    "customer_name": record["customer"],
                    "amount_gbp": record["amount"],
                    "source_currency": record["currency"],
                }
