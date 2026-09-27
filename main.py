from __future__ import annotations

from etl.example_databricks_task_factory import ExampleDatabricksTaskFactory
from etl.types.etl_config import EtlConfig
from utils.logging_utils_simple import configure_logging


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

    orchestrator = ExampleDatabricksTaskFactory.create(config)

    result = orchestrator.run()

    print(f"ETL completed: {result}")


if __name__ == "__main__":
    main()
