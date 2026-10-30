"""Small SEC EDGAR client for looking up companies and their latest 10-K."""

from __future__ import annotations

import base64
import logging
import mimetypes
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin, urlsplit

import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data"
_CORPORATE_SUFFIXES = {
    "co",
    "company",
    "corp",
    "corporation",
    "group",
    "inc",
    "incorporated",
    "limited",
    "llc",
    "lp",
    "ltd",
    "plc",
    "reit",
}


class SECClientError(Exception):
    """Base exception for SEC client errors."""


class SECConfigurationError(SECClientError):
    """Raised when the SEC client is not configured correctly."""


class SECRequestError(SECClientError):
    """Raised when an SEC request fails or returns invalid JSON."""


class SECDataError(SECClientError):
    """Raised when SEC data is malformed or incomplete."""


class CompanyNotFoundError(SECClientError):
    """Raised when the SEC company mapping does not contain a company name."""


class AmbiguousCompanyError(SECClientError):
    """Raised when a company name matches multiple SEC registrants."""


class FilingNotFoundError(SECClientError):
    """Raised when a company has no recent 10-K filing."""


@dataclass(frozen=True)
class Filing:
    """Metadata and archive URL for a 10-K filing."""

    company_name: str
    cik: str
    form: str
    accession_number: str
    primary_document: str
    filing_date: str | None
    report_date: str | None
    acceptance_datetime: str | None
    primary_document_description: str | None
    url: str


class SECClient:
    """Look up SEC company identifiers and recent 10-K filings.

    Requests are spaced by at least ``request_delay`` seconds per client.
    The default delay is 0.11 seconds, keeping request starts below the SEC's
    published maximum rate of 10 requests per second.
    """

    def __init__(
        self,
        *,
        request_delay: float = 0.11,
        timeout: float = 15.0,
        session: requests.Session | None = None,
    ) -> None:
        if request_delay < 0:
            raise ValueError("request_delay must be zero or greater")
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")

        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
        user_agent = os.getenv("SEC_USER_AGENT")
        if not user_agent or not user_agent.strip():
            raise SECConfigurationError(
                "SEC_USER_AGENT is required. Set it in the environment or in "
                "a .env file (for example: SEC_USER_AGENT=YourName "
                "your.email@domain.com)."
            )

        self._session = session if session is not None else requests.Session()
        self._session.headers.update(
            {
                "User-Agent": user_agent.strip(),
                "Accept-Encoding": "gzip, deflate",
            }
        )
        self._request_delay = request_delay
        self._timeout = timeout
        self._last_request_started: float | None = None
        self._request_lock = threading.Lock()
        self._company_records: list[tuple[str, str]] | None = None

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self._session.close()

    def __enter__(self) -> SECClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _get_json(self, url: str) -> dict[str, Any]:
        response = self._get_response(url)
        try:
            payload = response.json()
        except ValueError as exc:
            logger.exception("SEC returned invalid JSON: %s", url)
            raise SECRequestError(f"SEC returned invalid JSON for {url}") from exc

        if not isinstance(payload, dict):
            raise SECDataError(f"SEC returned an unexpected JSON structure for {url}")
        return payload

    def _get_response(self, url: str) -> requests.Response:
        with self._request_lock:
            if self._last_request_started is not None:
                elapsed = time.monotonic() - self._last_request_started
                wait = self._request_delay - elapsed
                if wait > 0:
                    time.sleep(wait)
            self._last_request_started = time.monotonic()

        try:
            response = self._session.get(url, timeout=self._timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.exception("SEC request failed: %s", url)
            raise SECRequestError(f"SEC request failed for {url}: {exc}") from exc

        return response

    def _load_company_records(self) -> list[tuple[str, str]]:
        if self._company_records is not None:
            return self._company_records

        payload = self._get_json(COMPANY_TICKERS_URL)
        records: list[tuple[str, str]] = []
        for entry in payload.values():
            if not isinstance(entry, dict):
                logger.warning("Skipping malformed SEC company ticker entry")
                continue
            cik_value = entry.get("cik_str")
            if isinstance(cik_value, bool) or not isinstance(cik_value, (int, str)):
                logger.warning("Skipping SEC company entry with no valid CIK")
                continue
            try:
                cik_number = int(cik_value)
            except ValueError:
                logger.warning("Skipping SEC company entry with invalid CIK")
                continue
            if cik_number <= 0 or cik_number > 9_999_999_999:
                logger.warning("Skipping SEC company entry with out-of-range CIK")
                continue
            title = entry.get("title")
            if isinstance(title, str) and title.strip():
                records.append((title.strip(), f"{cik_number:010d}"))

        if not records:
            raise SECDataError("SEC company ticker data contained no valid entries")
        self._company_records = records
        return records

    @staticmethod
    def _normalize_company_name(name: str) -> str:
        return " ".join(re.sub(r"[^a-z0-9]+", " ", name.casefold()).split())

    @classmethod
    def _canonical_company_name(cls, name: str) -> str:
        words = cls._normalize_company_name(name).split()
        if words and words[0] == "the":
            words = words[1:]
        while words and words[-1] in _CORPORATE_SUFFIXES:
            words.pop()
        return " ".join(words)

    def get_cik_by_company_name(self, company_name: str) -> str:
        """Resolve a company name against official SEC company titles."""
        if not isinstance(company_name, str) or not company_name.strip():
            raise ValueError("company_name must be a non-empty string")

        requested = self._normalize_company_name(company_name)
        records = self._load_company_records()

        exact_matches = {
            cik
            for title, cik in records
            if self._canonical_company_name(title)
            == self._canonical_company_name(company_name)
        }
        if exact_matches:
            matches = exact_matches
        else:
            matches = {
                cik
                for title, cik in records
                if f" {requested} " in f" {self._normalize_company_name(title)} "
            }

        if not matches:
            raise CompanyNotFoundError(
                f"Company {company_name!r} was not found in SEC company data"
            )
        if len(matches) > 1:
            raise AmbiguousCompanyError(
                f"Company name {company_name!r} matches multiple SEC registrants "
                f"(CIKs: {', '.join(sorted(matches))}); use a more specific name"
            )
        return matches.pop()

    @staticmethod
    def _metadata_value(
        recent_filings: dict[str, Any], field: str, index: int
    ) -> str | None:
        values = recent_filings.get(field)
        if not isinstance(values, list) or index >= len(values):
            return None
        value = values[index]
        return value if isinstance(value, str) and value else None

    @staticmethod
    def _filing_url(cik: str, accession_number: str, primary_document: str) -> str:
        if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession_number):
            raise SECDataError(
                f"SEC returned an invalid accession number: {accession_number!r}"
            )
        if (
            not primary_document
            or "\\" in primary_document
            or primary_document.startswith("/")
            or any(part in (".", "..") for part in primary_document.split("/"))
        ):
            raise SECDataError(
                f"SEC returned an unsafe primary document path: {primary_document!r}"
            )
        accession_path = accession_number.replace("-", "")
        document_path = quote(primary_document, safe="/-._~")
        return f"{ARCHIVES_URL}/{int(cik)}/{accession_path}/{document_path}"

    def get_latest_10k_by_cik(self, company_name: str, cik: str) -> Filing:
        """Fetch the latest exact ``10-K`` filing for a company CIK."""
        label = company_name.strip() if isinstance(company_name, str) else ""
        if not label:
            raise ValueError("company_name must be a non-empty string")
        if not isinstance(cik, str) or not re.fullmatch(r"\d{10}", cik):
            raise ValueError("cik must be a zero-padded 10-digit string")

        payload = self._get_json(SUBMISSIONS_URL.format(cik=cik))

        filings = payload.get("filings")
        recent = filings.get("recent") if isinstance(filings, dict) else None
        if not isinstance(recent, dict):
            raise SECDataError(f"SEC submissions data for CIK {cik} has no recent filings")

        forms = recent.get("form")
        accessions = recent.get("accessionNumber")
        documents = recent.get("primaryDocument")
        if (
            not isinstance(forms, list)
            or not isinstance(accessions, list)
            or not isinstance(documents, list)
        ):
            raise SECDataError(
                f"SEC submissions data for CIK {cik} is missing filing arrays"
            )
        if not (len(forms) == len(accessions) == len(documents)):
            raise SECDataError(
                f"SEC submissions filing arrays have inconsistent lengths for CIK {cik}"
            )

        candidates: list[tuple[str, int, str, str]] = []
        for index, (form, accession, document) in enumerate(
            zip(forms, accessions, documents)
        ):
            if form != "10-K":
                continue
            if not isinstance(accession, str) or not isinstance(document, str):
                logger.warning("Skipping malformed 10-K entry for CIK %s", cik)
                continue
            filing_date = self._metadata_value(recent, "filingDate", index) or ""
            candidates.append((filing_date, index, accession, document))

        if not candidates:
            raise FilingNotFoundError(
                f"No recent 10-K filing found for company {label}"
            )

        filing_date, index, accession, document = max(
            candidates, key=lambda candidate: (candidate[0], -candidate[1])
        )
        url = self._filing_url(cik, accession, document)
        filing = Filing(
            company_name=label,
            cik=cik,
            form="10-K",
            accession_number=accession,
            primary_document=document,
            filing_date=filing_date or None,
            report_date=self._metadata_value(recent, "reportDate", index),
            acceptance_datetime=self._metadata_value(
                recent, "acceptanceDateTime", index
            ),
            primary_document_description=self._metadata_value(
                recent, "primaryDocDescription", index
            ),
            url=url,
        )
        logger.debug(
            "Found latest 10-K for %s (CIK %s, filed %s)",
            label,
            cik,
            filing.filing_date or "date unavailable",
        )
        return filing

    def download_filing_content(self, filing: Filing) -> str:
        """Download a filing's primary document as decoded text."""
        expected_prefix = f"{ARCHIVES_URL}/"
        if not filing.url.startswith(expected_prefix):
            raise ValueError("filing URL must point to the SEC filing archives")

        response = self._get_response(filing.url)
        if not response.text.strip():
            raise SECDataError(f"SEC returned an empty filing for {filing.url}")
        return response.text

    def embed_filing_images(self, html: str, filing_url: str) -> str:
        """Embed SEC-hosted images while preserving all other HTML text."""
        if not isinstance(html, str) or not html.strip():
            raise ValueError("html must be a non-empty string")
        try:
            filing_parts = urlsplit(filing_url)
            filing_host = (filing_parts.hostname or "").lower()
        except ValueError as exc:
            raise ValueError("filing_url must be a valid HTTPS SEC URL") from exc
        if filing_parts.scheme.lower() != "https" or not _is_sec_host(filing_host):
            raise ValueError("filing_url must be an HTTPS URL on sec.gov")

        embedded: dict[str, str | None] = {}
        image_tag_pattern = re.compile(r"<img\b[^>]*>", re.IGNORECASE | re.DOTALL)
        source_pattern = re.compile(
            r"(?P<prefix>\bsrc\s*=\s*)(?P<quote>['\"])(?P<url>.*?)(?P=quote)",
            re.IGNORECASE | re.DOTALL,
        )

        def replace_image_tag(match: re.Match[str]) -> str:
            tag = match.group(0)
            source_match = source_pattern.search(tag)
            if source_match is None:
                return tag
            source = source_match.group("url").strip()
            if source.lower().startswith("data:image/"):
                return tag

            try:
                image_url = urljoin(filing_url, source)
                image_parts = urlsplit(image_url)
                image_host = (image_parts.hostname or "").lower()
            except ValueError:
                return ""
            if image_parts.scheme.lower() != "https" or not _is_sec_host(image_host):
                logger.warning("Removing non-SEC image reference: %s", source)
                return ""

            if image_url not in embedded:
                try:
                    response = self._get_response(image_url)
                except SECRequestError:
                    logger.warning("Could not retrieve SEC image: %s", image_url)
                    embedded[image_url] = None
                    return ""

                try:
                    final_host = (urlsplit(response.url).hostname or "").lower()
                except ValueError:
                    final_host = ""
                image_data = response.content
                media_type = (
                    response.headers.get("Content-Type", "")
                    .split(";", maxsplit=1)[0]
                    .strip()
                    .lower()
                )
                if not media_type.startswith("image/"):
                    guessed_type, _ = mimetypes.guess_type(image_parts.path)
                    media_type = guessed_type or ""
                if (
                    not _is_sec_host(final_host)
                    or not media_type.startswith("image/")
                    or not image_data
                    or len(image_data) > 20 * 1024 * 1024
                ):
                    logger.warning("SEC URL did not return a usable image: %s", image_url)
                    embedded[image_url] = None
                    return ""

                embedded[image_url] = (
                    f"data:{media_type};base64,"
                    f"{base64.b64encode(image_data).decode('ascii')}"
                )

            data_url = embedded[image_url]
            if data_url is None:
                return ""
            return (
                tag[: source_match.start("url")]
                + data_url
                + tag[source_match.end("url") :]
            )

        updated_html = image_tag_pattern.sub(replace_image_tag, html)
        logger.debug(
            "Embedded %d SEC filing image(s)",
            sum(value is not None for value in embedded.values()),
        )
        return updated_html


def _is_sec_host(hostname: str) -> bool:
    return hostname == "sec.gov" or hostname.endswith(".sec.gov")
