"""Sequentially download and convert configured SEC 10-K filings."""

from __future__ import annotations

import csv
import logging
import os
import re
from pathlib import Path

from dotenv import load_dotenv

from src.converter import ConversionError, convert_html_to_pdf
from src.sec_client import SECClient, SECClientError

logger = logging.getLogger(__name__)


def _configured_companies() -> list[str]:
    """Load company names from SEC_COMPANIES as a comma-separated list."""
    project_root = Path(__file__).resolve().parents[1]
    load_dotenv(project_root / ".env")

    company_names = os.getenv("SEC_COMPANIES", "")
    company_names = re.sub(r'"\s+(?=,|$)', '"', company_names.strip())
    try:
        rows = csv.reader([company_names], skipinitialspace=True, strict=True)
        names = next(rows)
    except csv.Error as exc:
        raise ValueError("SEC_COMPANIES must be a valid comma-separated list") from exc

    companies: list[str] = []
    seen: set[str] = set()
    for name in names:
        normalized = name.strip()
        key = normalized.casefold()
        if normalized and key not in seen:
            companies.append(normalized)
            seen.add(key)
    return companies


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S",
    )
    logger.info("Starting SEC 10-K download")

    try:
        companies = _configured_companies()
    except ValueError as exc:
        logger.error("%s", exc)
        return 1
    if not companies:
        logger.error(
            "No companies configured; set SEC_COMPANIES in the environment or .env"
        )
        return 1

    output_directory = Path("output")
    logger.info(
        "Queued %d company(ies) | PDF destination: %s",
        len(companies),
        output_directory,
    )

    try:
        client = SECClient()
    except (SECClientError, ValueError) as exc:
        logger.error("%s", exc)
        return 1

    failures: list[str] = []
    with client:
        for index, company_name in enumerate(companies):
            if index:
                logger.info("─" * 48)
            logger.info(
                "[%d/%d] %s",
                index + 1,
                len(companies),
                company_name,
            )
            try:
                logger.info("  Resolving company and latest 10-K")
                cik = client.get_cik_by_company_name(company_name)
                filing = client.get_latest_10k_by_cik(company_name, cik)
                logger.info("  Downloading filing")
                content = client.download_filing_content(filing)
                content = client.embed_filing_images(content, filing.url)
                logger.info("  Rendering PDF")
                output_path = convert_html_to_pdf(
                    content, company_name, output_directory
                )
                logger.info(
                    "  ✅ Complete | filed %s | saved to %s",
                    filing.filing_date or "date unavailable",
                    output_path,
                )
            except (SECClientError, ConversionError, OSError, ValueError) as exc:
                failures.append(company_name)
                logger.error("  ❌ Failed to process %s: %s", company_name, exc)

    if failures:
        logger.error(
            "⚠️  Run finished | %d succeeded | %d failed: %s",
            len(companies) - len(failures),
            len(failures),
            ", ".join(failures),
        )
        return 1
    logger.info("🎉 Run finished | %d succeeded | 0 failed", len(companies))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
