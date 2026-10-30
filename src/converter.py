"""Render SEC filing HTML to PDF with headless Chromium."""

from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)
_FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9_-]+")


class ConversionError(Exception):
    """Raised when filing content cannot be rendered or saved as a PDF."""


def convert_html_to_pdf(
    raw_html: str,
    company_name: str,
    output_directory: Path = Path("output"),
) -> Path:
    """Render raw HTML in Chromium and atomically save a professional PDF."""
    if not isinstance(raw_html, str) or not raw_html.strip():
        raise ValueError("filing content must be a non-empty string")
    if not isinstance(company_name, str) or not company_name.strip():
        raise ValueError("company_name must be a non-empty string")
    safe_name = _FILENAME_PATTERN.sub("_", company_name.strip()).strip("_-")
    if not safe_name:
        raise ValueError("company_name does not contain usable filename characters")
    if not isinstance(output_directory, Path):
        raise TypeError("output_directory must be a pathlib.Path")

    output_directory.mkdir(parents=True, exist_ok=True)
    target_path = output_directory / f"{safe_name}_10K.pdf"
    temporary_pdf_path: Path | None = None

    try:
        with tempfile.TemporaryDirectory(prefix="sec_filing_") as temporary_directory:
            html_path = Path(temporary_directory) / "filing.html"
            html_path.write_text(raw_html, encoding="utf-8")

            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{safe_name}_",
                suffix=".pdf",
                dir=output_directory,
                delete=False,
            ) as temporary_pdf:
                temporary_pdf_path = Path(temporary_pdf.name)

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                try:
                    page = browser.new_page()
                    page.goto(
                        html_path.as_uri(),
                        wait_until="load",
                        timeout=60_000,
                    )
                    page.emulate_media(media="print")
                    page.pdf(
                        path=str(temporary_pdf_path),
                        format="A4",
                        print_background=True,
                        prefer_css_page_size=True,
                        margin={
                            "top": "12mm",
                            "right": "10mm",
                            "bottom": "12mm",
                            "left": "10mm",
                        },
                    )
                finally:
                    browser.close()

        with temporary_pdf_path.open("rb+") as pdf_file:
            if pdf_file.read(5) != b"%PDF-":
                raise ConversionError(
                    f"Chromium produced invalid PDF output for {company_name}"
                )
            pdf_file.flush()
            os.fsync(pdf_file.fileno())
        os.replace(temporary_pdf_path, target_path)
        temporary_pdf_path = None
    except PlaywrightError as exc:
        logger.exception("Chromium rendering failed for %s", company_name)
        raise ConversionError(
            "Could not render the filing with Playwright. Install its Chromium "
            "browser with `python -m playwright install chromium`."
        ) from exc
    except OSError:
        logger.exception("Could not create or save PDF for %s", company_name)
        raise
    finally:
        if temporary_pdf_path is not None:
            try:
                temporary_pdf_path.unlink(missing_ok=True)
            except OSError:
                logger.exception(
                    "Could not remove temporary PDF file %s", temporary_pdf_path
                )

    return target_path
