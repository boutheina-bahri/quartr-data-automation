from typing import Any

import pytest

from src.sec_client import SECClient


def test_get_latest_10k_uses_latest_exact_form_and_matching_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = object.__new__(SECClient)
    request_urls: list[str] = []
    payload = {
        "filings": {
            "recent": {
                "form": ["10-K", "10-K/A", "10-K"],
                "accessionNumber": [
                    "0000000001-23-000001",
                    "0000000001-25-000001",
                    "0000000001-24-000001",
                ],
                "primaryDocument": [
                    "older.htm",
                    "amended.htm",
                    "latest.htm",
                ],
                "filingDate": ["2023-02-01", "2025-02-01", "2024-02-01"],
                "reportDate": ["2022-12-31", "2024-12-31", "2023-12-31"],
            }
        }
    }

    def fake_get_json(url: str) -> dict[str, Any]:
        request_urls.append(url)
        return payload

    monkeypatch.setattr(client, "_get_json", fake_get_json)

    filing = client.get_latest_10k_by_cik("Example Corporation", "0000000001")

    assert request_urls == [
        "https://data.sec.gov/submissions/CIK0000000001.json"
    ]
    assert filing.company_name == "Example Corporation"
    assert filing.form == "10-K"
    assert filing.accession_number == "0000000001-24-000001"
    assert filing.primary_document == "latest.htm"
    assert filing.filing_date == "2024-02-01"
    assert filing.report_date == "2023-12-31"
    assert filing.url.endswith("/000000000124000001/latest.htm")
