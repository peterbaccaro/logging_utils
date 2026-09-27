from __future__ import annotations

from etl.example_databricks_task_factory import ExampleDatabricksTaskFactory
from etl.types.etl_config import EtlConfig
from utils.logging_utils_simple import configure_logging, run_context


def main() -> None:
    """
    Application entry point.
    """

    configure_logging()

    config = EtlConfig(
        environment="dev",
        source_name="source_api",
        target_name="target_delta",
        batch_size=100,
    )

    with run_context() as context:
        task = ExampleDatabricksTaskFactory.create(config)
        task_result = task.run()

    print(f"ETL completed: {task_result}")


if __name__ == "__main__":
    main()
