from typing import Any, Iterator

from utils.logging_utils_simple import log_method


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

    @log_method()
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

    @log_method()
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
