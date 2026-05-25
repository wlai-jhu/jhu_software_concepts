import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional


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


def load_data(path: str) -> List[Dict[str, Optional[str]]]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def field_counts(records: List[Dict[str, Optional[str]]]) -> Dict[str, int]:
    return {
        field: sum(record.get(field) is not None for record in records)
        for field in REQUIRED_FIELDS
    }


def validate_file(path: str, expected_count: int) -> bool:
    records = load_data(path)
    print(f"{path}: {len(records)} records")
    for field, count in field_counts(records).items():
        print(f"  {field}: {count}")

    missing_fields = [
        field
        for field in REQUIRED_FIELDS
        if any(field not in record for record in records)
    ]
    if missing_fields:
        print(f"  Missing required keys: {', '.join(missing_fields)}")
        return False

    if len(records) < expected_count:
        print(f"  Expected at least {expected_count} records.")
        return False

    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Module 2 JSON deliverables.")
    parser.add_argument("--expected-count", type=int, default=50000)
    parser.add_argument("files", nargs="*", default=["applicant_data.json", "llm_extend_applicant_data.json"])
    args = parser.parse_args()

    all_valid = True
    for path in args.files:
        all_valid = validate_file(path, args.expected_count) and all_valid

    if not all_valid:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
