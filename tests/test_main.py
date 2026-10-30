import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from src import main
from src.sec_client import CompanyNotFoundError


def test_configured_companies_trims_deduplicates_and_preserves_quoted_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main, "load_dotenv", lambda *_args, **_kwargs: None)
    monkeypatch.setenv(
        "SEC_COMPANIES",
        ' Apple, Meta ,, apple, "Example, Incorporated" ',
    )

    assert main._configured_companies() == [
        "Apple",
        "Meta",
        "Example, Incorporated",
    ]


def test_configured_companies_returns_empty_list_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main, "load_dotenv", lambda *_args, **_kwargs: None)
    monkeypatch.delenv("SEC_COMPANIES", raising=False)

    assert main._configured_companies() == []


def test_configured_companies_rejects_malformed_csv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main, "load_dotenv", lambda *_args, **_kwargs: None)
    monkeypatch.setenv("SEC_COMPANIES", 'Apple, "unfinished')

    with pytest.raises(ValueError, match="SEC_COMPANIES"):
        main._configured_companies()


def test_main_continues_after_company_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    processed: list[str] = []

    class FakeClient:
        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def get_cik_by_company_name(self, company_name: str) -> str:
            if company_name == "Unavailable":
                raise CompanyNotFoundError("Company not found")
            return "0000000001"

        def get_latest_10k_by_cik(self, company_name: str, cik: str):
            return SimpleNamespace(
                filing_date="2025-01-01",
                url="https://www.sec.gov/Archives/filing.htm",
            )

        def download_filing_content(self, _filing: object) -> str:
            return "<html>filing</html>"

        def embed_filing_images(self, content: str, _url: str) -> str:
            return content

    def fake_convert(_content: str, company_name: str, _output: object):
        processed.append(company_name)
        return tmp_path / f"{company_name}.pdf"

    monkeypatch.setattr(
        main, "_configured_companies", lambda: ["Unavailable", "Available"]
    )
    monkeypatch.setattr(main, "SECClient", FakeClient)
    monkeypatch.setattr(main, "convert_html_to_pdf", fake_convert)
    caplog.set_level(logging.INFO)

    assert main.main() == 1
    assert processed == ["Available"]
    assert "Failed to process Unavailable" in caplog.text
    assert "1 succeeded | 1 failed" in caplog.text
