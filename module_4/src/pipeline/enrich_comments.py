import argparse
import html
import json
import ssl
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib import request
from urllib.error import HTTPError, URLError

import certifi
from bs4 import BeautifulSoup


USER_AGENT = "jhu-software-concepts-module-2/1.0"
DEFAULT_PROGRESS_PATH = "data/comment_enrichment.progress.json"
DEFAULT_PARALLEL_PAGES = 16
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
    checkpoint_path: Optional[str] = None,
    save_every: int = 25,
    parallel_pages: int = DEFAULT_PARALLEL_PAGES,
) -> List[Dict[str, Optional[str]]]:
    """Fetch public result detail pages and add applicant notes when available."""
    progress_file = Path(progress_path)
    progress_file.parent.mkdir(parents=True, exist_ok=True)
    enriched_records = [dict(record) for record in records]
    pages_checked = 0
    index = max(0, start_index)
    parallel_pages = max(1, parallel_pages)
    next_checkpoint_at = max(1, save_every)

    while index < len(enriched_records):
        if max_detail_pages is not None and pages_checked >= max_detail_pages:
            break

        batch = _next_detail_batch(
            enriched_records,
            start_index=index,
            batch_size=parallel_pages,
            remaining_pages=None if max_detail_pages is None else max_detail_pages - pages_checked,
        )
        if not batch:
            break

        stop_requested = False
        for result_index, entry_url, comments, error in _fetch_comment_batch(batch):
            if error:
                print(f"Stopping comment enrichment at index {result_index}: {error}.")
                stop_requested = True
                continue

            pages_checked += 1
            if comments:
                enriched_records[result_index]["comments"] = comments
                print(f"Added comments for index {result_index}: {entry_url}")

        index = max(result_index for result_index, _entry_url in batch) + 1
        _save_progress(progress_file, next_index=index, pages_checked=pages_checked)
        if checkpoint_path and pages_checked >= next_checkpoint_at:
            save_data(enriched_records, checkpoint_path)
            while pages_checked >= next_checkpoint_at:
                next_checkpoint_at += max(1, save_every)

        if stop_requested:
            break

        time.sleep(delay_seconds)

    if checkpoint_path:
        save_data(enriched_records, checkpoint_path)
    return enriched_records


def _next_detail_batch(
    records: List[Dict[str, Optional[str]]],
    start_index: int,
    batch_size: int,
    remaining_pages: Optional[int],
) -> List[Tuple[int, str]]:
    batch = []
    index = start_index
    while index < len(records) and len(batch) < batch_size:
        if remaining_pages is not None and len(batch) >= remaining_pages:
            break

        record = records[index]
        entry_url = record.get("entry_url")
        if not record.get("comments") and entry_url and "/result/" in entry_url:
            batch.append((index, entry_url))
        index += 1
    return batch


def _fetch_comment_batch(
    batch: List[Tuple[int, str]],
) -> List[Tuple[int, str, Optional[str], Optional[str]]]:
    if len(batch) == 1:
        index, entry_url = batch[0]
        try:
            return [(index, entry_url, _fetch_public_notes(entry_url), None)]
        except (HTTPError, URLError) as exc:
            return [(index, entry_url, None, _format_fetch_error(exc))]

    results = []
    with ThreadPoolExecutor(max_workers=len(batch)) as executor:
        futures = {
            executor.submit(_fetch_public_notes, entry_url): (index, entry_url)
            for index, entry_url in batch
        }
        for future in as_completed(futures):
            index, entry_url = futures[future]
            try:
                results.append((index, entry_url, future.result(), None))
            except (HTTPError, URLError) as exc:
                results.append((index, entry_url, None, _format_fetch_error(exc)))
    return sorted(results, key=lambda row: row[0])


def _format_fetch_error(exc: HTTPError | URLError) -> str:
    if isinstance(exc, HTTPError):
        if exc.code in STOP_STATUS_CODES or exc.code >= 500:
            return f"HTTP {exc.code}"
        raise exc
    return str(exc)


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
    parser.add_argument(
        "--all-records",
        action="store_true",
        help="Check every eligible result page instead of stopping after --max-detail-pages.",
    )
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument(
        "--parallel-pages",
        type=int,
        default=DEFAULT_PARALLEL_PAGES,
        help="Fetch this many public result detail pages concurrently.",
    )
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--progress", default=DEFAULT_PROGRESS_PATH)
    parser.add_argument(
        "--save-every",
        type=int,
        default=25,
        help="Checkpoint the output JSON after this many detail pages are checked.",
    )
    args = parser.parse_args()

    start_index = _resume_index(args.progress) if args.resume else args.start_index
    max_detail_pages = None if args.all_records else args.max_detail_pages
    records = load_data(args.input)
    enriched_records = enrich_comments(
        records,
        max_detail_pages=max_detail_pages,
        delay_seconds=args.delay,
        start_index=start_index,
        progress_path=args.progress,
        checkpoint_path=args.output,
        save_every=args.save_every,
        parallel_pages=args.parallel_pages,
    )
    comment_count = sum(record.get("comments") is not None for record in enriched_records)
    print(f"Saved {len(enriched_records)} records to {args.output}; comments available for {comment_count} records.")


if __name__ == "__main__":
    main()
