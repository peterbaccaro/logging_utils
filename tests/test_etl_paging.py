from collections.abc import Iterator

import pytest

from etl.components.acme_api_service import AcmeApiService
from etl.components.source_to_target_transformer import SourceToTargetTransformer
from etl.components.target_writer import TargetWriter


@pytest.mark.parametrize(
    ("batch_size", "expected_page_lengths"),
    [
        (100, [100, 100, 36]),
        (200, [200, 36]),
        (300, [236]),
    ],
)
def test_acme_api_service_yields_customer_pages_in_record_order(
    batch_size: int,
    expected_page_lengths: list[int],
) -> None:
    api_service = AcmeApiService("source_api", batch_size)

    pages = list(api_service.get_customers_iter())

    assert all(isinstance(page, list) for page in pages)
    assert [len(page) for page in pages] == expected_page_lengths
    assert [record["source_id"] for page in pages for record in page] == list(range(1, 237))


def test_acme_api_service_rejects_non_positive_batch_size() -> None:
    with pytest.raises(ValueError, match="batch_size must be greater than zero"):
        AcmeApiService("source_api", 0)


def test_transformer_flattens_pages_and_transforms_each_record() -> None:
    pages: Iterator[list[dict[str, object]]] = iter(
        [
            [
                {
                    "source_id": 1,
                    "customer": "Ada",
                    "amount": 10.5,
                    "currency": "GBP",
                },
                {
                    "source_id": 2,
                    "customer": "Linus",
                    "amount": 21.0,
                    "currency": "GBP",
                },
            ],
            [
                {
                    "source_id": 3,
                    "customer": "Grace",
                    "amount": 31.5,
                    "currency": "GBP",
                }
            ],
        ]
    )

    records = list(SourceToTargetTransformer().transform(pages))

    assert records == [
        {
            "id": 1,
            "customer_name": "Ada",
            "amount_gbp": 10.5,
            "source_currency": "GBP",
        },
        {
            "id": 2,
            "customer_name": "Linus",
            "amount_gbp": 21.0,
            "source_currency": "GBP",
        },
        {
            "id": 3,
            "customer_name": "Grace",
            "amount_gbp": 31.5,
            "source_currency": "GBP",
        },
    ]


def test_paged_source_runs_through_transformer_and_writer() -> None:
    api_service = AcmeApiService("source_api", batch_size=100)
    transformer = SourceToTargetTransformer()
    writer = TargetWriter("target_delta", batch_size=75)

    result = writer.write(transformer.transform(api_service.get_customers_iter()))

    assert result == {
        "target": "target_delta",
        "records_written": 236,
        "batches_written": 4,
    }
