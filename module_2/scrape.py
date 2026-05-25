import argparse
import json
import re
import ssl
import time
from html import unescape
from pathlib import Path
from typing import Dict, Iterable, List, Optional
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
USER_AGENT = "jhu-software-concepts-module-2/1.0"


class ScrapeStopError(RuntimeError):
    """Raised when the scraper should stop politely and keep partial results."""


class GradCafeScraper:
    """Polite Grad Cafe scraper that checks robots.txt before collecting data."""

    def __init__(
        self,
        target_records: int = DEFAULT_TARGET_RECORDS,
        delay_seconds: float = DEFAULT_DELAY_SECONDS,
        output_path: str = "data/raw_applicant_data.json",
        use_selenium: bool = False,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
    ):
        self.target_records = target_records
        self.delay_seconds = delay_seconds
        self.output_path = Path(output_path)
        self.use_selenium = use_selenium
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
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
        seen_raw_entries = set()
        page = 1

        while len(records) < self.target_records:
            url = self.build_url(page=page)
            print(f"Fetching page {page}: {url}")

            try:
                html = self._get_rendered_html(url) if self.use_selenium else self._request_text(url)
            except ScrapeStopError as exc:
                print(f"{exc} Saving {len(records)} records collected so far.")
                self.save_data(records)
                break

            page_records = list(self._parse_page(html, url))

            if not page_records:
                print("No applicant records found on this page; stopping.")
                break

            for record in page_records:
                raw_text = record.get("raw_text") or ""
                if raw_text and raw_text not in seen_raw_entries:
                    records.append(record)
                    seen_raw_entries.add(raw_text)
                if len(records) >= self.target_records:
                    break

            page += 1
            self.save_data(records)
            time.sleep(self.delay_seconds)

        return records

    def save_data(self, records: List[Dict[str, Optional[str]]]) -> None:
        """Save raw scraped records as valid JSON."""
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(json.dumps(records, indent=2), encoding="utf-8")

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


def save_data(records: List[Dict[str, Optional[str]]], output_path: str = "data/raw_applicant_data.json") -> None:
    GradCafeScraper(output_path=output_path).save_data(records)


def load_data(input_path: str = "data/raw_applicant_data.json") -> List[Dict[str, Optional[str]]]:
    return json.loads(Path(input_path).read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape public Grad Cafe applicant data.")
    parser.add_argument("--target", type=int, default=DEFAULT_TARGET_RECORDS)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS)
    parser.add_argument("--output", default="data/raw_applicant_data.json")
    parser.add_argument("--selenium", action="store_true")
    parser.add_argument("--check-robots-only", action="store_true")
    parser.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES)
    parser.add_argument("--backoff", type=float, default=DEFAULT_BACKOFF_SECONDS)
    args = parser.parse_args()

    scraper = GradCafeScraper(
        target_records=args.target,
        delay_seconds=args.delay,
        output_path=args.output,
        use_selenium=args.selenium,
        max_retries=args.max_retries,
        backoff_seconds=args.backoff,
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
