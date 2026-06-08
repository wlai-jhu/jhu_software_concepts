import argparse
import json
import re
import ssl
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from html import unescape
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple
from urllib import parse, request, robotparser
from urllib.error import HTTPError, URLError

import certifi
from bs4 import BeautifulSoup


BASE_URL = "https://www.thegradcafe.com"
DEFAULT_RESULTS_PATH = "/survey/"
DEFAULT_TARGET_RECORDS = 50000
DEFAULT_DELAY_SECONDS = 3.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_SECONDS = 10.0
DEFAULT_PARALLEL_PAGES = 16
USER_AGENT = "jhu-software-concepts-module-2/1.0"
DEFAULT_OUTPUT_PATH = "data/raw_applicant_data.json"


class ScrapeStopError(RuntimeError):
    """Raised when the scraper should stop politely and keep partial results."""


class GradCafeScraper:
    """Polite Grad Cafe scraper that checks robots.txt before collecting data."""

    def __init__(
        self,
        target_records: int = DEFAULT_TARGET_RECORDS,
        delay_seconds: float = DEFAULT_DELAY_SECONDS,
        output_path: str = DEFAULT_OUTPUT_PATH,
        use_selenium: bool = False,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
        start_page: int = 1,
        resume: bool = False,
        parallel_pages: int = DEFAULT_PARALLEL_PAGES,
        stop_on_existing: bool = False,
        stop_before_date: Optional[str] = None,
    ):
        self.target_records = target_records
        self.delay_seconds = delay_seconds
        self.output_path = Path(output_path)
        self.use_selenium = use_selenium
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.start_page = max(1, start_page)
        self.resume = resume
        self.parallel_pages = max(1, parallel_pages)
        self.stop_on_existing = stop_on_existing
        self.stop_before_date = self._parse_date_value(stop_before_date)
        self.progress_path = self.output_path.with_suffix(".progress.json")
        self.robot_parser = robotparser.RobotFileParser()
        self.robot_parser.set_url(parse.urljoin(BASE_URL, "/robots.txt"))

    def check_robots(self, evidence_path: str = "evidence/robots_check.txt") -> bool:
        """Fetch robots.txt, save evidence, and confirm the survey URL is allowed."""
        evidence_file = Path(evidence_path)
        evidence_file.parent.mkdir(parents=True, exist_ok=True)

        robots_url = parse.urljoin(BASE_URL, "/robots.txt")
        raw_text = self._request_text(robots_url)
        evidence_file.write_text(raw_text, encoding="utf-8")

        self.robot_parser.parse(raw_text.splitlines())
        target_url = self.build_url(page=1)
        return self.robot_parser.can_fetch(USER_AGENT, target_url)

    def build_url(self, page: int, search: str = "") -> str:
        """Build a Grad Cafe results URL with urllib."""
        query = {"page": page}
        if search:
            query["q"] = search
        return parse.urljoin(BASE_URL, DEFAULT_RESULTS_PATH) + "?" + parse.urlencode(query)

    def scrape_data(self) -> List[Dict[str, Optional[str]]]:
        """Pull applicant data from Grad Cafe until target_records or stop condition."""
        if not self.check_robots():
            raise PermissionError("robots.txt does not permit scraping the configured Grad Cafe URL.")

        records: List[Dict[str, Optional[str]]] = []
        if self.resume or self.stop_on_existing:
            records = self._deduplicate_records(self.load_existing_data())

        seen_record_keys = self._seen_record_keys(records)
        page = self._resume_page() if self.resume else self.start_page
        print(f"Starting scrape at page {page} with {len(records)} existing records.")

        while len(records) < self.target_records:
            batch_size = self.parallel_pages if not self.use_selenium else 1
            batch_pages = list(range(page, page + batch_size))
            print(f"Fetching pages {batch_pages[0]}-{batch_pages[-1]} with {batch_size} worker(s).")

            try:
                batch_results = self._fetch_page_batch(batch_pages)
            except ScrapeStopError as exc:
                print(f"{exc} Saving {len(records)} records collected so far.")
                self.save_data(records)
                self.save_progress(page=page - 1, record_count=len(records))
                break

            processed_any_records = False
            duplicate_records = 0
            new_records = 0
            last_processed_page = page - 1
            for result_page, page_records in batch_results:
                if not page_records:
                    print(f"No applicant records found on page {result_page}; stopping.")
                    self.save_data(records)
                    self.save_progress(page=last_processed_page, record_count=len(records))
                    return records

                if self._page_is_before_stop_date(page_records):
                    print(
                        f"Page {result_page} is older than cutoff date "
                        f"{self.stop_before_date.isoformat()}; stopping incremental scrape."
                    )
                    self.save_data(records)
                    self.save_progress(page=last_processed_page, record_count=len(records))
                    return records

                processed_any_records = True
                last_processed_page = result_page
                for record in page_records:
                    record_keys = self._record_keys(record)
                    if record_keys and not seen_record_keys.intersection(record_keys):
                        records.append(record)
                        seen_record_keys.update(record_keys)
                        new_records += 1
                    else:
                        duplicate_records += 1
                    if len(records) >= self.target_records:
                        break
                if len(records) >= self.target_records:
                    break

            if self.stop_on_existing and duplicate_records > 0 and new_records == 0:
                print(
                    "Existing records detected and no new records found in this batch; "
                    "stopping incremental scrape."
                )
                self.save_data(records)
                self.save_progress(page=last_processed_page, record_count=len(records))
                return records

            if not processed_any_records:
                break

            page = last_processed_page + 1
            self.save_data(records)
            self.save_progress(page=last_processed_page, record_count=len(records))
            time.sleep(self.delay_seconds)

        return records

    def save_data(self, records: List[Dict[str, Optional[str]]]) -> None:
        """Save raw scraped records as valid JSON."""
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        unique_records = self._deduplicate_records(records)
        self.output_path.write_text(json.dumps(unique_records, indent=2), encoding="utf-8")

    def load_existing_data(self) -> List[Dict[str, Optional[str]]]:
        """Load existing output records for resume mode."""
        if not self.output_path.exists():
            return []
        return json.loads(self.output_path.read_text(encoding="utf-8"))

    def save_progress(self, page: int, record_count: int) -> None:
        """Save the last successfully processed page for resume mode."""
        progress = {
            "last_successful_page": page,
            "next_page": page + 1,
            "record_count": record_count,
            "output_path": str(self.output_path),
        }
        self.progress_path.write_text(json.dumps(progress, indent=2), encoding="utf-8")

    def _fetch_page_batch(self, pages: List[int]) -> List[Tuple[int, List[Dict[str, Optional[str]]]]]:
        if len(pages) == 1:
            return [self._fetch_page_records(pages[0])]

        results: Dict[int, List[Dict[str, Optional[str]]]] = {}
        with ThreadPoolExecutor(max_workers=len(pages)) as executor:
            futures = {executor.submit(self._fetch_page_records, page): page for page in pages}
            for future in as_completed(futures):
                result_page, page_records = future.result()
                results[result_page] = page_records
        return [(page, results[page]) for page in sorted(results)]

    def _fetch_page_records(self, page: int) -> Tuple[int, List[Dict[str, Optional[str]]]]:
        url = self.build_url(page=page)
        print(f"Fetching page {page}: {url}")
        html = self._get_rendered_html(url) if self.use_selenium else self._request_text(url)
        return page, list(self._parse_page(html, url))

    def _resume_page(self) -> int:
        if self.progress_path.exists():
            progress = json.loads(self.progress_path.read_text(encoding="utf-8"))
            next_page = int(progress.get("next_page", self.start_page))
            return max(self.start_page, next_page)
        return self.start_page

    def _seen_record_keys(self, records: List[Dict[str, Optional[str]]]) -> Set[str]:
        seen_record_keys: Set[str] = set()
        for record in records:
            seen_record_keys.update(self._record_keys(record))
        return seen_record_keys

    def _record_keys(self, record: Dict[str, Optional[str]]) -> Set[str]:
        keys: Set[str] = set()
        entry_url = record.get("entry_url")
        if entry_url and "/result/" in entry_url:
            keys.add(f"url:{entry_url}")

        signature = self._record_signature(record)
        if signature:
            keys.add(f"sig:{signature}")

        raw_text = record.get("raw_text")
        if raw_text:
            keys.add(f"raw:{self._normalize_duplicate_value(raw_text)}")
        return keys

    def _record_signature(self, record: Dict[str, Optional[str]]) -> Optional[str]:
        """Build a conservative normalized fingerprint for re-entered applicant rows."""
        normalized = {
            "university": self._normalize_duplicate_value(record.get("university")),
            "program_name": self._normalize_duplicate_value(record.get("program_name")),
            "applicant_status": self._normalize_duplicate_value(record.get("applicant_status")),
            "acceptance_date": self._normalize_duplicate_value(record.get("acceptance_date")),
            "rejection_date": self._normalize_duplicate_value(record.get("rejection_date")),
            "term": self._normalize_duplicate_value(record.get("term")),
            "degree": self._normalize_duplicate_value(record.get("degree")),
            "student_origin": self._normalize_duplicate_value(record.get("student_origin")),
            "gpa": self._normalize_duplicate_value(record.get("gpa")),
            "gre_score": self._normalize_duplicate_value(record.get("gre_score")),
            "gre_v_score": self._normalize_duplicate_value(record.get("gre_v_score")),
            "gre_aw": self._normalize_duplicate_value(record.get("gre_aw")),
        }

        required_fields = ["university", "program_name", "applicant_status", "term"]
        if any(not normalized[field] for field in required_fields):
            return None

        academic_metric_fields = ["gpa", "gre_score", "gre_v_score", "gre_aw"]
        if not any(normalized[field] for field in academic_metric_fields):
            return None

        ordered_fields = required_fields + [
            "acceptance_date",
            "rejection_date",
            "degree",
            "student_origin",
            "gpa",
            "gre_score",
            "gre_v_score",
            "gre_aw",
        ]
        return "|".join(normalized[field] or "" for field in ordered_fields)

    def _normalize_duplicate_value(self, value: Optional[str]) -> str:
        if value is None:
            return ""
        text = unescape(str(value)).lower()
        text = re.sub(r"[^a-z0-9.]+", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def _parse_date_value(self, value: Optional[str]) -> Optional[date]:
        if not value:
            return None
        for date_format in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
            try:
                return datetime.strptime(value, date_format).date()
            except ValueError:
                continue
        return None

    def _page_is_before_stop_date(self, records: List[Dict[str, Optional[str]]]) -> bool:
        if self.stop_before_date is None:
            return False

        parsed_dates = [
            parsed_date
            for parsed_date in (self._parse_date_value(record.get("date_added")) for record in records)
            if parsed_date is not None
        ]
        return bool(parsed_dates) and max(parsed_dates) < self.stop_before_date

    def _deduplicate_records(
        self,
        records: List[Dict[str, Optional[str]]],
    ) -> List[Dict[str, Optional[str]]]:
        unique_records = []
        seen_record_keys: Set[str] = set()
        for record in records:
            record_keys = self._record_keys(record)
            if record_keys and seen_record_keys.intersection(record_keys):
                continue
            seen_record_keys.update(record_keys)
            unique_records.append(record)
        return unique_records

    def _request_text(self, url: str) -> str:
        req = request.Request(url, headers={"User-Agent": USER_AGENT})
        context = ssl.create_default_context(cafile=certifi.where())
        last_error: Optional[BaseException] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                with request.urlopen(req, timeout=30, context=context) as response:
                    status_code = getattr(response, "status", 200)
                    if status_code in {403, 429}:
                        raise ScrapeStopError(f"Stopping because the site returned HTTP {status_code}.")
                    if status_code >= 500:
                        raise HTTPError(url, status_code, "Server error", response.headers, None)
                    return response.read().decode("utf-8", errors="replace")
            except HTTPError as exc:
                last_error = exc
                if exc.code in {403, 429}:
                    raise ScrapeStopError(f"Stopping because the site returned HTTP {exc.code}.") from exc
                if exc.code >= 500:
                    if attempt < self.max_retries:
                        self._sleep_before_retry(url, attempt, exc.code)
                        continue
                    raise ScrapeStopError(
                        f"Stopping after {self.max_retries} attempts because the site returned HTTP {exc.code}."
                    ) from exc
                raise
            except URLError as exc:
                last_error = exc
                if attempt < self.max_retries:
                    self._sleep_before_retry(url, attempt, "network error")
                    continue
                raise ScrapeStopError(
                    f"Stopping after {self.max_retries} attempts because the request failed: {exc}."
                ) from exc

        raise ScrapeStopError(f"Stopping after repeated request failures: {last_error}")

    def _sleep_before_retry(self, url: str, attempt: int, reason) -> None:
        wait_seconds = self.backoff_seconds * attempt
        print(
            f"Request failed for {url} ({reason}); retry {attempt + 1}/{self.max_retries} "
            f"after {wait_seconds:.1f} seconds."
        )
        time.sleep(wait_seconds)

    def _get_rendered_html(self, url: str) -> str:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait

        options = Options()
        options.add_argument("--headless=new")
        options.add_argument(f"--user-agent={USER_AGENT}")

        driver = webdriver.Chrome(options=options)
        try:
            driver.get(url)
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            return driver.page_source
        finally:
            driver.quit()

    def _parse_page(self, html: str, page_url: str) -> Iterable[Dict[str, Optional[str]]]:
        soup = BeautifulSoup(html, "html.parser")
        table_records = list(self._parse_table_rows(soup, page_url))
        if table_records:
            yield from table_records
            return

        candidates = self._candidate_entries(soup)

        for candidate in candidates:
            text = self._clean_text(candidate.get_text(" ", strip=True))
            if not self._looks_like_applicant_entry(text):
                continue

            entry_link = self._entry_link(candidate, page_url)
            yield self._parse_entry(text, entry_link)

    def _parse_table_rows(self, soup: BeautifulSoup, page_url: str) -> Iterable[Dict[str, Optional[str]]]:
        rows = soup.select("tr")
        index = 0
        while index < len(rows):
            row = rows[index]
            cells = row.find_all("td", recursive=False)
            row_classes = row.get("class") or []

            if len(cells) < 4 or "tw-border-none" in row_classes:
                index += 1
                continue

            detail_text = ""
            if index + 1 < len(rows) and "tw-border-none" in (rows[index + 1].get("class") or []):
                detail_text = self._clean_text(rows[index + 1].get_text(" ", strip=True))
                index += 1

            yield self._parse_table_entry(row, detail_text, page_url)
            index += 1

    def _parse_table_entry(self, row, detail_text: str, page_url: str) -> Dict[str, Optional[str]]:
        cells = row.find_all("td", recursive=False)
        university = self._clean_text(cells[0].get_text(" ", strip=True)) if len(cells) > 0 else None
        program_cell = cells[1] if len(cells) > 1 else None
        program_text = self._clean_text(program_cell.get_text(" ", strip=True)) if program_cell else ""
        date_added = self._clean_text(cells[2].get_text(" ", strip=True)) if len(cells) > 2 else None
        decision_text = self._clean_text(cells[3].get_text(" ", strip=True)) if len(cells) > 3 else ""
        entry_url = self._entry_link(row, page_url)
        raw_text = self._clean_text(" ".join([university or "", program_text, date_added or "", decision_text, detail_text]))

        degree = self._extract_degree(program_text)
        program_name = self._remove_degree_from_program(program_text, degree)
        status = self._normalize_status(decision_text)
        decision_date = self._extract_written_decision_date(decision_text, date_added)

        return {
            "program_name": program_name,
            "university": university,
            "comments": None,
            "date_added": date_added,
            "entry_url": entry_url,
            "applicant_status": status,
            "acceptance_date": decision_date if status == "Accepted" else None,
            "rejection_date": decision_date if status == "Rejected" else None,
            "term": self._extract_term(detail_text),
            "student_origin": self._extract_student_origin(detail_text),
            "gre_score": self._extract_metric(raw_text, r"GRE\s*[:=]?\s*([0-9]{3})"),
            "gre_v_score": self._extract_metric(raw_text, r"GRE\s*V\s*[:=]?\s*([0-9]{2,3})"),
            "degree": degree,
            "gpa": self._extract_metric(raw_text, r"GPA\s*[:=]?\s*([0-4](?:\.[0-9]{1,2})?)"),
            "gre_aw": self._extract_metric(raw_text, r"(?:GRE\s*)?AW\s*[:=]?\s*([0-6](?:\.[0-9])?)"),
            "raw_text": raw_text,
        }

    def _candidate_entries(self, soup: BeautifulSoup) -> List:
        selectors = [
            "tr",
            "article",
            ".row",
            ".result",
            ".submission",
            ".applicant",
            "[class*=result]",
            "[class*=submission]",
        ]
        entries = []
        for selector in selectors:
            entries.extend(soup.select(selector))
        return entries

    def _parse_entry(self, raw_text: str, entry_url: Optional[str]) -> Dict[str, Optional[str]]:
        status = self._normalize_status(raw_text)
        return {
            "program_name": self._extract_program(raw_text),
            "university": self._extract_university(raw_text),
            "comments": self._extract_comments(raw_text),
            "date_added": self._extract_date_added(raw_text),
            "entry_url": entry_url,
            "applicant_status": status,
            "acceptance_date": self._extract_decision_date(raw_text) if status == "Accepted" else None,
            "rejection_date": self._extract_decision_date(raw_text) if status == "Rejected" else None,
            "term": self._extract_term(raw_text),
            "student_origin": self._extract_student_origin(raw_text),
            "gre_score": self._extract_metric(raw_text, r"GRE\s*[:=]?\s*([0-9]{3})"),
            "gre_v_score": self._extract_metric(raw_text, r"GRE\s*V\s*[:=]?\s*([0-9]{2,3})"),
            "degree": self._extract_degree(raw_text),
            "gpa": self._extract_metric(raw_text, r"GPA\s*[:=]?\s*([0-4](?:\.[0-9]{1,2})?)"),
            "gre_aw": self._extract_metric(raw_text, r"(?:GRE\s*)?AW\s*[:=]?\s*([0-6](?:\.[0-9])?)"),
            "raw_text": raw_text,
        }

    def _looks_like_applicant_entry(self, text: str) -> bool:
        lowered = text.lower()
        has_status = any(word in lowered for word in ["accepted", "rejected", "waitlisted", "wait list"])
        has_grad_signal = any(word in lowered for word in ["phd", "master", "ms", "ma", "gpa", "gre"])
        return has_status and has_grad_signal

    def _entry_link(self, candidate, page_url: str) -> Optional[str]:
        link = candidate.find("a", href=True)
        if not link:
            return page_url
        return parse.urljoin(BASE_URL, link["href"])

    def _clean_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", unescape(text)).strip()

    def _normalize_status(self, text: str) -> Optional[str]:
        lowered = text.lower()
        if "accepted" in lowered:
            return "Accepted"
        if "rejected" in lowered:
            return "Rejected"
        if "interview" in lowered:
            return "Interview"
        if "waitlisted" in lowered or "wait list" in lowered:
            return "Waitlisted"
        return None

    def _extract_program(self, text: str) -> Optional[str]:
        match = re.search(r"^(.+?)(?:\s+(?:Accepted|Rejected|Waitlisted)\b)", text, re.IGNORECASE)
        return match.group(1).strip(" -|") if match else None

    def _extract_university(self, text: str) -> Optional[str]:
        match = re.search(r"(?:at|from)\s+([A-Z][A-Za-z&.,' -]+?)(?:\s+(?:Accepted|Rejected|Waitlisted|PhD|Masters?|GPA|GRE)\b)", text)
        return match.group(1).strip(" -|") if match else None

    def _extract_comments(self, text: str) -> Optional[str]:
        match = re.search(r"(?:comment[s]?:)\s*(.+)$", text, re.IGNORECASE)
        return match.group(1).strip() if match else None

    def _extract_date_added(self, text: str) -> Optional[str]:
        return self._extract_metric(text, r"([0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4})")

    def _extract_decision_date(self, text: str) -> Optional[str]:
        return self._extract_metric(text, r"(?:Accepted|Rejected|Waitlisted).*?([0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4})")

    def _extract_term(self, text: str) -> Optional[str]:
        return self._extract_metric(text, r"\b((?:Fall|Spring|Summer|Winter)\s+[0-9]{4})\b")

    def _extract_student_origin(self, text: str) -> Optional[str]:
        lowered = text.lower()
        if "international" in lowered:
            return "International"
        if "american" in lowered or "domestic" in lowered:
            return "American"
        return None

    def _extract_degree(self, text: str) -> Optional[str]:
        lowered = text.lower()
        if "phd" in lowered or "ph.d" in lowered:
            return "PhD"
        if "master" in lowered or re.search(r"\bM[AS]\b", text):
            return "Masters"
        return None

    def _remove_degree_from_program(self, program_text: str, degree: Optional[str]) -> Optional[str]:
        if not program_text:
            return None
        cleaned = program_text
        if degree == "PhD":
            cleaned = re.sub(r"\bPh\.?D\b", "", cleaned, flags=re.IGNORECASE)
        elif degree == "Masters":
            cleaned = re.sub(r"\b(?:Masters?|M[AS])\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" -|")
        return cleaned or None

    def _extract_written_decision_date(self, decision_text: str, date_added: Optional[str]) -> Optional[str]:
        match = re.search(
            r"(?:Accepted|Rejected|Waitlisted)\s+on\s+([A-Za-z]{3,9}\s+[0-9]{1,2})",
            decision_text,
            re.IGNORECASE,
        )
        if not match:
            return None
        decision_date = match.group(1)
        year_match = re.search(r"\b([0-9]{4})\b", date_added or "")
        if year_match:
            return f"{decision_date}, {year_match.group(1)}"
        return decision_date

    def _extract_metric(self, text: str, pattern: str) -> Optional[str]:
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(1).strip() if match else None


def scrape_data(target_records: int = DEFAULT_TARGET_RECORDS, use_selenium: bool = False) -> List[Dict[str, Optional[str]]]:
    scraper = GradCafeScraper(target_records=target_records, use_selenium=use_selenium)
    return scraper.scrape_data()


def save_data(records: List[Dict[str, Optional[str]]], output_path: str = DEFAULT_OUTPUT_PATH) -> None:
    GradCafeScraper(output_path=output_path).save_data(records)


def load_data(input_path: str = DEFAULT_OUTPUT_PATH) -> List[Dict[str, Optional[str]]]:
    return json.loads(Path(input_path).read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape public Grad Cafe applicant data.")
    parser.add_argument("--target", type=int, default=DEFAULT_TARGET_RECORDS)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS)
    parser.add_argument("--output", default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--selenium", action="store_true")
    parser.add_argument("--check-robots-only", action="store_true")
    parser.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES)
    parser.add_argument("--backoff", type=float, default=DEFAULT_BACKOFF_SECONDS)
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--stop-on-existing",
        action="store_true",
        help="Stop an incremental scrape once a fetched batch only contains records already in the output dataset.",
    )
    parser.add_argument(
        "--parallel-pages",
        type=int,
        default=DEFAULT_PARALLEL_PAGES,
        help="Fetch this many survey pages concurrently.",
    )
    parser.add_argument(
        "--stop-before-date",
        help=(
            "Stop incremental scraping once a page's newest date_added is before this date "
            "(YYYY-MM-DD, May 27, 2026, or similar)."
        ),
    )
    args = parser.parse_args()

    scraper = GradCafeScraper(
        target_records=args.target,
        delay_seconds=args.delay,
        output_path=args.output,
        use_selenium=args.selenium,
        max_retries=args.max_retries,
        backoff_seconds=args.backoff,
        start_page=args.start_page,
        resume=args.resume,
        parallel_pages=args.parallel_pages,
        stop_on_existing=args.stop_on_existing,
        stop_before_date=args.stop_before_date,
    )

    allowed = scraper.check_robots()
    print(f"robots.txt allows configured scrape target: {allowed}")
    if args.check_robots_only:
        return
    if not allowed:
        raise PermissionError("robots.txt does not permit the configured scrape target.")

    records = scraper.scrape_data()
    scraper.save_data(records)
    print(f"Saved {len(records)} records to {args.output}")


if __name__ == "__main__":
    main()
