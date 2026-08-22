"""
grobid_client.py
----------------
Thin HTTP client for a running GROBID service (the Docker container).

GROBID does the heavy lifting we used to do badly by hand: it drops running headers,
page footers and page numbers, reconstructs reading order, dehyphenates line breaks,
and returns a structured TEI-XML tree (title, abstract, labelled sections, figure and
table captions, and a separate <back> for references). We POST each PDF to
`/api/processFulltextDocument` and hand the TEI to the parser.

Start the service (CRF-only image, fine on CPU, ~300 MB) with:

    docker run --rm --init -p 8070:8070 lfoppiano/grobid:0.8.0

or the official image:

    docker run --rm --init -p 8070:8070 grobid/grobid:0.8.1

Then check:  python -m core.clean_index.build_index --health
"""

import requests
from pathlib import Path


class GrobidError(RuntimeError):
    """Raised when GROBID cannot parse a PDF or the service is unreachable."""


class GrobidClient:
    def __init__(self, base_url: str = "http://localhost:8070", timeout: int = 300):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def is_alive(self) -> bool:
        """True if the GROBID service answers its health endpoint."""
        try:
            r = requests.get(f"{self.base_url}/api/isalive", timeout=10)
            return r.status_code == 200 and "true" in r.text.lower()
        except requests.RequestException:
            return False

    def process_fulltext(self, pdf_path: str) -> str:
        """
        Return the TEI-XML string for one PDF, or raise GrobidError.

        We ask GROBID NOT to consolidate citations (we discard references anyway) but
        to segment the header cleanly. Coordinates and sentence segmentation are off to
        keep the TEI compact.
        """
        pdf_path = str(pdf_path)
        if not Path(pdf_path).exists():
            raise GrobidError(f"PDF not found: {pdf_path}")

        url = f"{self.base_url}/api/processFulltextDocument"
        data = {
            "consolidateHeader": "0",
            "consolidateCitations": "0",
            "includeRawAffiliations": "0",
            "segmentSentences": "0",
        }
        try:
            with open(pdf_path, "rb") as fh:
                resp = requests.post(
                    url,
                    files={"input": (Path(pdf_path).name, fh, "application/pdf")},
                    data=data,
                    timeout=self.timeout,
                )
        except requests.RequestException as e:
            raise GrobidError(f"GROBID request failed for {pdf_path}: {e}") from e

        if resp.status_code != 200:
            raise GrobidError(
                f"GROBID returned {resp.status_code} for {pdf_path}: "
                f"{resp.text[:200]}"
            )
        if not resp.text or "<TEI" not in resp.text:
            raise GrobidError(f"GROBID returned no TEI for {pdf_path}")
        return resp.text
