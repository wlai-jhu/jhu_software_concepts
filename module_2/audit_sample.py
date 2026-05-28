import argparse
import html
import json
import math
import random
import re
from pathlib import Path
from statistics import NormalDist
from typing import Dict, List, Optional, Sequence, Tuple


REQUIRED_FIELDS = [
    "program_name",
    "university",
    "comments",
    "date_added",
    "entry_url",
    "applicant_status",
    "acceptance_date",
    "rejection_date",
    "term",
    "student_origin",
    "gre_score",
    "gre_v_score",
    "degree",
    "gpa",
    "gre_aw",
    "raw_text",
]

VALID_STATUSES = {"Accepted", "Rejected", "Waitlisted", "Interview"}
TERM_PATTERN = re.compile(r"^(Fall|Spring|Summer|Winter)\s+\d{4}$")
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
HTML_ENTITY_PATTERN = re.compile(r"&(?:[a-zA-Z]+|#[0-9]+|#x[0-9a-fA-F]+);")


def load_data(path: str) -> List[Dict[str, Optional[str]]]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_data(records: Sequence[Dict[str, Optional[str]]], output_path: str) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(list(records), indent=2), encoding="utf-8")


def sample_size(population_size: int, confidence: float, margin: float) -> int:
    """Return the finite-population sample size for a worst-case 50% defect rate."""
    if population_size <= 0:
        return 0
    if not 0 < confidence < 1:
        raise ValueError("confidence must be between 0 and 1.")
    if not 0 < margin < 1:
        raise ValueError("margin must be between 0 and 1.")

    z_score = NormalDist().inv_cdf(1 - (1 - confidence) / 2)
    p = 0.5
    initial_size = (z_score**2 * p * (1 - p)) / margin**2
    adjusted_size = initial_size / (1 + ((initial_size - 1) / population_size))
    return min(population_size, math.ceil(adjusted_size))


def audit_records(records: Sequence[Dict[str, Optional[str]]]) -> Tuple[int, List[str]]:
    issues: List[str] = []
    defect_count = 0

    for sample_number, record in enumerate(records, start=1):
        record_issues = _record_issues(record)
        if record_issues:
            defect_count += 1
            label = record.get("entry_url") or f"sample #{sample_number}"
            for issue in record_issues:
                issues.append(f"{label}: {issue}")

    return defect_count, issues


def _record_issues(record: Dict[str, Optional[str]]) -> List[str]:
    issues: List[str] = []

    for field in REQUIRED_FIELDS:
        if field not in record:
            issues.append(f"missing key {field}")

    if not _clean_present(record.get("program_name")):
        issues.append("program_name is missing")
    if not _clean_present(record.get("university")):
        issues.append("university is missing")
    if not _clean_present(record.get("raw_text")):
        issues.append("raw_text is missing")

    entry_url = record.get("entry_url")
    if not entry_url or "/result/" not in str(entry_url):
        issues.append("entry_url does not look like a Grad Cafe result link")

    status = record.get("applicant_status")
    if status not in VALID_STATUSES:
        issues.append(f"unexpected applicant_status {status!r}")
    if status == "Accepted" and not record.get("acceptance_date"):
        issues.append("accepted record is missing acceptance_date")
    if status == "Rejected" and not record.get("rejection_date"):
        issues.append("rejected record is missing rejection_date")

    term = record.get("term")
    if term and not TERM_PATTERN.match(str(term)):
        issues.append(f"term has unexpected format {term!r}")

    for field in _string_fields(record):
        value = record.get(field)
        if isinstance(value, str) and _contains_html(value):
            issues.append(f"{field} contains possible HTML markup or entity")

    _check_numeric_range(record, "gpa", 0.0, 4.3, issues)
    _check_numeric_range(record, "gre_score", 130.0, 340.0, issues)
    _check_numeric_range(record, "gre_v_score", 130.0, 170.0, issues)
    _check_numeric_range(record, "gre_aw", 0.0, 6.0, issues)

    if "program_name_cleaned" in record and not _clean_present(record.get("program_name_cleaned")):
        issues.append("program_name_cleaned is missing")
    if "university_cleaned" in record and not _clean_present(record.get("university_cleaned")):
        issues.append("university_cleaned is missing")

    return issues


def _clean_present(value: Optional[str]) -> bool:
    return value is not None and str(value).strip() != ""


def _contains_html(value: str) -> bool:
    return bool(HTML_TAG_PATTERN.search(value) or HTML_ENTITY_PATTERN.search(value)) or html.unescape(value) != value


def _string_fields(record: Dict[str, Optional[str]]) -> List[str]:
    return [field for field, value in record.items() if isinstance(value, str)]


def _check_numeric_range(
    record: Dict[str, Optional[str]],
    field: str,
    low: float,
    high: float,
    issues: List[str],
) -> None:
    value = record.get(field)
    if value is None or value == "":
        return
    try:
        number = float(str(value))
    except ValueError:
        issues.append(f"{field} is not numeric: {value!r}")
        return
    if number < low or number > high:
        issues.append(f"{field} is outside expected range: {value!r}")


def wilson_interval(defects: int, sample_count: int, confidence: float) -> Tuple[float, float]:
    if sample_count == 0:
        return 0.0, 0.0
    z_score = NormalDist().inv_cdf(1 - (1 - confidence) / 2)
    proportion = defects / sample_count
    denominator = 1 + z_score**2 / sample_count
    center = (proportion + z_score**2 / (2 * sample_count)) / denominator
    half_width = (
        z_score
        * math.sqrt((proportion * (1 - proportion) + z_score**2 / (4 * sample_count)) / sample_count)
        / denominator
    )
    return max(0.0, center - half_width), min(1.0, center + half_width)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Randomly sample Module 2 JSON records for a 95% confidence quality audit."
    )
    parser.add_argument("--file", default="applicant_data.json", help="JSON file to audit.")
    parser.add_argument("--confidence", type=float, default=0.95, help="Confidence level, such as 0.95.")
    parser.add_argument("--margin", type=float, default=0.05, help="Target margin of error, such as 0.05.")
    parser.add_argument("--sample-size", type=int, default=None, help="Override calculated sample size.")
    parser.add_argument("--seed", type=int, default=20260528, help="Random seed for repeatable samples.")
    parser.add_argument(
        "--sample-output",
        default="data/audit_sample.json",
        help="Where to save sampled records for manual review.",
    )
    parser.add_argument("--examples", type=int, default=10, help="Maximum issues to print.")
    parser.add_argument("--fail-on-issues", action="store_true", help="Exit nonzero if sampled issues are found.")
    args = parser.parse_args()

    records = load_data(args.file)
    calculated_size = sample_size(len(records), args.confidence, args.margin)
    requested_size = args.sample_size or calculated_size
    if requested_size <= 0:
        raise SystemExit("Sample size must be greater than zero.")
    actual_size = min(len(records), requested_size)

    rng = random.Random(args.seed)
    sampled_records = rng.sample(records, actual_size)
    save_data(sampled_records, args.sample_output)

    defects, issues = audit_records(sampled_records)
    lower_bound, upper_bound = wilson_interval(defects, actual_size, args.confidence)

    print(f"Audited file: {args.file}")
    print(f"Population size: {len(records)}")
    print(f"Sample size: {actual_size}")
    print(f"Confidence level: {args.confidence:.0%}")
    print(f"Target margin of error: +/- {args.margin:.1%}")
    print(f"Random seed: {args.seed}")
    print(f"Sample saved to: {args.sample_output}")
    print(f"Sampled records with issues: {defects}")
    print(f"Sample issue rate: {defects / actual_size:.2%}")
    print(f"{args.confidence:.0%} confidence interval for issue rate: {lower_bound:.2%} to {upper_bound:.2%}")

    if issues:
        print("\nExample issues:")
        for issue in issues[: args.examples]:
            print(f"- {issue}")
        if len(issues) > args.examples:
            print(f"- ... {len(issues) - args.examples} more issues not shown")
    else:
        print("\nNo automated quality issues found in the random sample.")

    if args.fail_on_issues and defects:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
