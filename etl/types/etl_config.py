from dataclasses import dataclass


@dataclass(frozen=True)
class EtlConfig:
    """ETL runtime configuration."""

    environment: str
    source_name: str
    target_name: str
    batch_size: int = 100
