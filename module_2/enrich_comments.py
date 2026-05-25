import argparse
import html
import json
import ssl
import time
from pathlib import Path
from typing import Dict, List, Optional
from urllib import request
from urllib.error import HTTPError, URLError

import certifi
from bs4 import BeautifulSoup


USER_AGENT = "jhu-software-concepts-module-2/1.0"
DEFAULT_PROGRESS_PATH = "data/comment_enrichment.progress.json"
STOP_STATUS_CODES = {403, 429}


def load_data(input_path: str) -> List[Dict[str, Optional[str]]]:
    return json.loads(Path(input_path).read_text(encoding="utf-8"))


def save_data(records: List[Dict[str, Optional[str]]], output_path: str) -> None:
    Path(output_path).write_text(json.dumps(records, indent=2), encoding="utf-8")


def enrich_comments(
    records: List[Dict[str, Optional[str]]],
    max_detail_pages: Optional[int] = None,
    delay_seconds: float = 1.0,
    start_index: int = 0,
    progress_path: str = DEFAULT_PROGRESS_PATH,
) -> List[Dict[str, Optional[str]]]:
    """Fetch public result detail pages and add applicant notes when available."""
    progress_file = Path(progress_path)
    progress_file.parent.mkdir(parents=True, exist_ok=True)
    enriched_records = [dict(record) for record in records]
    pages_checked = 0

    for index in range(max(0, start_index), len(enriched_records)):
        if max_detail_pages is not None and pages_checked >= max_detail_pages:
            break

        record = enriched_records[index]
        if record.get("comments"):
            continue

        entry_url = record.get("entry_url")
        if not entry_url or "/result/" not in entry_url:
            continue

        try:
            comments = _fetch_public_notes(entry_url)
        except HTTPError as exc:
            if exc.code in STOP_STATUS_CODES or exc.code >= 500:
                print(f"Stopping comment enrichment at index {index}: HTTP {exc.code}.")
                break
            raise
        except URLError as exc:
            print(f"Stopping comment enrichment at index {index}: {exc}.")
            break

        pages_checked += 1
        if comments:
            record["comments"] = comments
            print(f"Added comments for index {index}: {entry_url}")

        _save_progress(progress_file, next_index=index + 1, pages_checked=pages_checked)
        time.sleep(delay_seconds)

    return enriched_records


def _fetch_public_notes(entry_url: str) -> Optional[str]:
    req = request.Request(entry_url, headers={"User-Agent": USER_AGENT})
    context = ssl.create_default_context(cafile=certifi.where())
    with request.urlopen(req, timeout=30, context=context) as response:
        status_code = getattr(response, "status", 200)
        if status_code in STOP_STATUS_CODES or status_code >= 500:
            raise HTTPError(entry_url, status_code, "Rejected detail request", response.headers, None)
        page_html = response.read().decode("utf-8", errors="replace")

    soup = BeautifulSoup(page_html, "html.parser")
    app = soup.find(id="app")
    if not app or not app.get("data-page"):
        return None

    data_page = json.loads(html.unescape(app["data-page"]))
    notes = data_page.get("props", {}).get("admission", {}).get("notes")
    return _clean_optional_text(notes)


def _clean_optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = html.unescape(str(value))
    text = " ".join(text.split())
    return text or None


def _save_progress(progress_file: Path, next_index: int, pages_checked: int) -> None:
    progress_file.write_text(
        json.dumps(
            {
                "next_index": next_index,
                "pages_checked_this_run": pages_checked,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _resume_index(progress_path: str) -> int:
    path = Path(progress_path)
    if not path.exists():
        return 0
    progress = json.loads(path.read_text(encoding="utf-8"))
    return int(progress.get("next_index", 0))


def main() -> None:
    parser = argparse.ArgumentParser(description="Politely enrich Grad Cafe records with public detail-page comments.")
    parser.add_argument("--input", default="applicant_data.json")
    parser.add_argument("--output", default="applicant_data.json")
    parser.add_argument("--max-detail-pages", type=int, default=100)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--progress", default=DEFAULT_PROGRESS_PATH)
    args = parser.parse_args()

    start_index = _resume_index(args.progress) if args.resume else args.start_index
    records = load_data(args.input)
    enriched_records = enrich_comments(
        records,
        max_detail_pages=args.max_detail_pages,
        delay_seconds=args.delay,
        start_index=start_index,
        progress_path=args.progress,
    )
    save_data(enriched_records, args.output)
    comment_count = sum(record.get("comments") is not None for record in enriched_records)
    print(f"Saved {len(enriched_records)} records to {args.output}; comments available for {comment_count} records.")


if __name__ == "__main__":
    main()
