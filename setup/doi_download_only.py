#!/usr/bin/env python3
import argparse
import os
import re
import time
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from random import uniform
from typing import Dict, List, Optional
from urllib.parse import unquote, urljoin

import requests

# Repo root = parent of setup/. Anchors data paths so this works from any CWD.
ROOT = Path(__file__).resolve().parent.parent


def canonicalize_doi(doi: str) -> str:
    d = unquote((doi or "").strip())
    d = d.replace("https://doi.org/", "").replace("http://doi.org/", "")
    d = re.sub(r"/v\d+/(review\d*|decision\d*|response\d*|author[-_]?reply\d*)$", "", d, flags=re.IGNORECASE)
    d = re.sub(r"/v\d+$", "", d, flags=re.IGNORECASE)
    return d.strip()


def doi_to_filename(doi: str) -> str:
    return re.sub(r"[^\w\-_.]", "_", doi)


def read_dois(path: str) -> List[str]:
    out = []
    seen = set()
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            doi = canonicalize_doi(line.strip())
            if not doi:
                continue
            key = doi.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(doi)
    return out


def write_lines(path: str, lines: List[str]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")


def append_line(path: str, line: str) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def build_session(user_agent: str, cookies_file: str = "") -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": user_agent})
    if cookies_file:
        jar = MozillaCookieJar()
        jar.load(cookies_file, ignore_discard=True, ignore_expires=True)
        s.cookies.update(jar)
    return s


def get_unpaywall_record(doi: str, email: str, session: requests.Session) -> Optional[Dict]:
    url = f"https://api.unpaywall.org/v2/{doi}?email={email}"
    try:
        r = session.get(url, timeout=20)
        if r.status_code == 200:
            return r.json()
        return None
    except Exception:
        return None


def get_openalex_record(doi: str, session: requests.Session) -> Optional[Dict]:
    url = "https://api.openalex.org/works"
    params = {"filter": f"doi:https://doi.org/{doi}", "per-page": 1}
    try:
        r = session.get(url, params=params, timeout=20)
        if r.status_code != 200:
            return None
        results = r.json().get("results", [])
        return results[0] if results else None
    except Exception:
        return None


def unique_keep_order(items: List[str]) -> List[str]:
    out = []
    seen = set()
    for x in items:
        if not x:
            continue
        k = x.strip()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(k)
    return out


def extract_unpaywall_urls(rec: Dict) -> List[str]:
    if not rec:
        return []
    urls: List[str] = []
    best = rec.get("best_oa_location") or {}
    if best.get("url_for_pdf"):
        urls.append(best["url_for_pdf"])
    for loc in rec.get("oa_locations", []) or []:
        if loc.get("url_for_pdf"):
            urls.append(loc["url_for_pdf"])
    return unique_keep_order(urls)


def extract_openalex_urls(rec: Dict) -> List[str]:
    if not rec:
        return []
    urls: List[str] = []

    primary = rec.get("primary_location") or {}
    if isinstance(primary, dict):
        if primary.get("pdf_url"):
            urls.append(primary["pdf_url"])
        if primary.get("landing_page_url"):
            urls.append(primary["landing_page_url"])

    for loc in rec.get("locations", []) or []:
        if not isinstance(loc, dict):
            continue
        if loc.get("pdf_url"):
            urls.append(loc["pdf_url"])
        if loc.get("landing_page_url"):
            urls.append(loc["landing_page_url"])

    return unique_keep_order(urls)


def extract_pdf_links_from_html(landing_url: str, session: requests.Session) -> List[str]:
    """
    Lightweight HTML fallback: find likely PDF links from landing pages.
    """
    try:
        r = session.get(landing_url, timeout=25)
        if r.status_code != 200:
            return []
        html = r.text or ""
        hrefs = re.findall(r"href=[\"']([^\"']+)[\"']", html, flags=re.IGNORECASE)
        candidates: List[str] = []
        for h in hrefs:
            h_low = h.lower()
            if ".pdf" in h_low or "/pdf" in h_low or "download" in h_low:
                candidates.append(urljoin(landing_url, h))
        return unique_keep_order(candidates)
    except Exception:
        return []


def resolve_doi_landing_url(doi: str, session: requests.Session) -> Optional[str]:
    """
    Resolve DOI to final landing page via doi.org redirects.
    """
    url = f"https://doi.org/{doi}"
    try:
        r = session.get(url, timeout=25, allow_redirects=True)
        if r.status_code == 200 and r.url:
            return r.url
    except Exception:
        return None
    return None


def elsevier_direct_pdf_urls_from_doi(doi: str, session: requests.Session) -> List[str]:
    """
    Elsevier-specific shortcut:
    DOI -> resolve landing URL -> extract PII -> build ScienceDirect PDF URLs.
    """
    if not (doi or "").lower().startswith("10.1016/"):
        return []
    landing = resolve_doi_landing_url(doi, session)
    if not landing:
        return []

    # Common patterns:
    # .../science/article/pii/S0306261924013849
    # .../retrieve/pii/S0306261924013849
    m = re.search(r"/(?:science/article/pii|retrieve/pii)/([A-Za-z0-9]+)", landing, flags=re.IGNORECASE)
    if not m:
        # fallback to last path token
        m2 = re.search(r"/([A-Za-z0-9]+)(?:\\?.*)?$", landing)
        if not m2:
            return []
        pii = m2.group(1)
    else:
        pii = m.group(1)

    return unique_keep_order(
        [
            f"https://www.sciencedirect.com/science/article/pii/{pii}/pdf",
            f"https://www.sciencedirect.com/science/article/pii/{pii}/pdfft",
        ]
    )


def sciencedirect_pdf_fallback_urls(landing_url: str) -> List[str]:
    """
    Try common ScienceDirect direct-PDF URL shapes from article landing URLs.
    """
    lu = (landing_url or "").lower()
    if "sciencedirect.com" not in lu and "linkinghub.elsevier.com" not in lu:
        return []
    out: List[str] = []
    # Example landing:
    # https://www.sciencedirect.com/science/article/pii/S0960148124001234
    m = re.search(r"/science/article/pii/([A-Za-z0-9]+)", landing_url, flags=re.IGNORECASE)
    if not m:
        # Elsevier linkinghub style:
        # https://linkinghub.elsevier.com/retrieve/pii/S0306261924013849
        m = re.search(r"/retrieve/pii/([A-Za-z0-9]+)", landing_url, flags=re.IGNORECASE)
    if m:
        pii = m.group(1)
        out.append(f"https://www.sciencedirect.com/science/article/pii/{pii}/pdfft")
        out.append(f"https://www.sciencedirect.com/science/article/pii/{pii}/pdf")
    return unique_keep_order(out)


def build_candidate_pdf_urls(doi: str, email: str, session: requests.Session) -> List[str]:
    """
    Try multiple metadata sources to improve PDF discovery:
    1) Unpaywall direct PDF URLs
    2) OpenAlex PDF/landing URLs
    3) Extract PDF links from landing pages
    """
    urls: List[str] = []

    # Elsevier direct-PDF shortcut first (as requested)
    urls.extend(elsevier_direct_pdf_urls_from_doi(doi, session))

    up = get_unpaywall_record(doi, email, session)
    urls.extend(extract_unpaywall_urls(up))

    oa = get_openalex_record(doi, session)
    oa_urls = extract_openalex_urls(oa)
    urls.extend(oa_urls)

    # DOI resolver fallback (helps when metadata APIs don't expose direct PDF URL)
    landing = resolve_doi_landing_url(doi, session)
    if landing:
        urls.append(landing)
        urls.extend(sciencedirect_pdf_fallback_urls(landing))

    for u in oa_urls:
        if u.lower().endswith(".pdf") or "/pdf" in u.lower():
            continue
        urls.extend(extract_pdf_links_from_html(u, session))

    if landing and not (landing.lower().endswith(".pdf") or "/pdf" in landing.lower()):
        urls.extend(extract_pdf_links_from_html(landing, session))

    return unique_keep_order(urls)


def download_pdf_from_candidates(
    doi: str,
    candidate_urls: List[str],
    output_dir: str,
    session: requests.Session,
    attempted_urls_file: str,
) -> bool:
    os.makedirs(output_dir, exist_ok=True)
    pdf_path = os.path.join(output_dir, f"{doi_to_filename(doi)}.pdf")

    if os.path.exists(pdf_path):
        append_line(attempted_urls_file, f"{doi}\t-\t-\t-\talready_exists")
        return True

    for pdf_url in candidate_urls:
        try:
            r = session.get(pdf_url, timeout=35, allow_redirects=True)
            content_type = (r.headers.get("Content-Type") or "").lower()
            if r.status_code == 200 and ("pdf" in content_type or r.url.lower().endswith(".pdf")):
                with open(pdf_path, "wb") as f:
                    f.write(r.content)
                append_line(
                    attempted_urls_file,
                    f"{doi}\t{pdf_url}\t{r.status_code}\t{content_type}\tsuccess",
                )
                return True
            append_line(
                attempted_urls_file,
                f"{doi}\t{pdf_url}\t{r.status_code}\t{content_type}\tnot_pdf_or_bad_status",
            )
        except Exception:
            append_line(attempted_urls_file, f"{doi}\t{pdf_url}\t-\t-\trequest_exception")
            continue
    return False


def main() -> None:
    p = argparse.ArgumentParser(description="Download OA PDFs from a DOI list (dois.txt)")
    p.add_argument("--email", required=True, help="Email for Unpaywall API")
    p.add_argument("--dois_file", default=str(ROOT / "dois.txt"), help="Input DOI list file")
    p.add_argument("--output_dir", default=str(ROOT / "PDFs"), help="Folder to save PDFs")
    p.add_argument("--oa_dois_file", default=str(ROOT / "oa_dois.txt"), help="DOIs that have OA PDF URLs")
    p.add_argument("--failed_dois_file", default=str(ROOT / "failed_dois.txt"), help="DOIs that failed with reason")
    p.add_argument("--downloaded_dois_file", default=str(ROOT / "downloaded_dois.txt"), help="DOIs successfully downloaded")
    p.add_argument("--cookies_file", default="", help="Optional Netscape cookies.txt for authenticated downloads (e.g., Wiley)")
    p.add_argument("--attempted_urls_file", default=str(ROOT / "attempted_urls.tsv"), help="Detailed URL attempts per DOI")
    p.add_argument("--min_delay", type=float, default=1.0)
    p.add_argument("--max_delay", type=float, default=3.0)
    args = p.parse_args()

    dois = read_dois(args.dois_file)
    if not dois:
        raise SystemExit(f"No DOIs found in {args.dois_file}")

    print(f"[INFO] Loaded DOIs: {len(dois)}")

    oa_dois: List[str] = []
    downloaded: List[str] = []
    failed: List[str] = []
    candidate_urls_map: Dict[str, List[str]] = {}

    # reset diagnostics file with header
    write_lines(args.attempted_urls_file, ["doi\turl\tstatus\tcontent_type\toutcome"])

    ua = f"doi-download-only/1.0 (mailto:{args.email})"
    try:
        session = build_session(ua, args.cookies_file)
    except Exception as e:
        raise SystemExit(f"Failed to load cookies file '{args.cookies_file}': {e}")

    if args.cookies_file:
        print(f"[INFO] Using cookies from: {args.cookies_file}")

    for doi in dois:
        candidate_urls = build_candidate_pdf_urls(doi, args.email, session)
        if not candidate_urls:
            failed.append(f"{doi}\tno_candidate_pdf_url")
            continue

        oa_dois.append(doi)
        candidate_urls_map[doi] = candidate_urls

    write_lines(args.oa_dois_file, oa_dois)
    print(f"[INFO] DOIs with candidate PDF URLs: {len(oa_dois)}")

    for doi in oa_dois:
        ok = download_pdf_from_candidates(
            doi,
            candidate_urls_map[doi],
            args.output_dir,
            session,
            args.attempted_urls_file,
        )
        if ok:
            downloaded.append(doi)
            print(f"✅ Downloaded: {doi}")
        else:
            failed.append(f"{doi}\tdownload_error")
            print(f"❌ Download failed: {doi}")
        time.sleep(uniform(args.min_delay, args.max_delay))

    write_lines(args.downloaded_dois_file, downloaded)
    write_lines(args.failed_dois_file, failed)

    print("\n[SUMMARY]")
    print(f"Total input DOIs: {len(dois)}")
    print(f"With candidate PDF URLs: {len(oa_dois)}")
    print(f"Downloaded PDFs: {len(downloaded)}")
    print(f"Failed entries: {len(failed)}")
    print(f"Saved PDFs folder: {args.output_dir}")
    print(f"Attempt diagnostics: {args.attempted_urls_file}")


if __name__ == "__main__":
    main()
