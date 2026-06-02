import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from db import connect


DEFAULT_INPUT_PATH = Path(__file__).resolve().parents[1] / "module_2" / "llm_extend_applicant_data.json"

# PostgreSQL table shape mirrors the assignment questions and keeps both downloaded
# fields and LLM-standardized fields available for comparison.
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS applicants (
    p_id integer PRIMARY KEY,
    program text,
    comments text,
    date_added date,
    url text UNIQUE,
    status text,
    term text,
    us_or_international text,
    gpa double precision,
    gre double precision,
    gre_v double precision,
    gre_aw double precision,
    degree text,
    llm_generated_program text,
    llm_generated_university text
);
"""


INSERT_SQL = """
INSERT INTO applicants (
    p_id, program, comments, date_added, url, status, term, us_or_international,
    gpa, gre, gre_v, gre_aw, degree, llm_generated_program, llm_generated_university
) VALUES (
    %(p_id)s, %(program)s, %(comments)s, %(date_added)s, %(url)s, %(status)s,
    %(term)s, %(us_or_international)s, %(gpa)s, %(gre)s, %(gre_v)s, %(gre_aw)s,
    %(degree)s, %(llm_generated_program)s, %(llm_generated_university)s
)
ON CONFLICT (url) DO UPDATE SET
    program = EXCLUDED.program,
    comments = EXCLUDED.comments,
    date_added = EXCLUDED.date_added,
    status = EXCLUDED.status,
    term = EXCLUDED.term,
    us_or_international = EXCLUDED.us_or_international,
    gpa = EXCLUDED.gpa,
    gre = EXCLUDED.gre,
    gre_v = EXCLUDED.gre_v,
    gre_aw = EXCLUDED.gre_aw,
    degree = EXCLUDED.degree,
    llm_generated_program = EXCLUDED.llm_generated_program,
    llm_generated_university = EXCLUDED.llm_generated_university;
"""


def load_json(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def parse_date(value: Optional[str]) -> Optional[str]:
    """Accept the date formats produced by the scraper and normalize them for PostgreSQL."""
    if not value:
        return None
    for date_format in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, date_format).date().isoformat()
        except ValueError:
            continue
    return None


def parse_float(value: Any) -> Optional[float]:
    """Extract a numeric value from fields that may include labels or extra text."""
    if value in (None, ""):
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    if not match:
        return None
    return float(match.group(0))


def first_present(record: Dict[str, Any], *keys: str) -> Optional[str]:
    """Return the first populated value from alternate scraper/LLM field names."""
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def normalize_record(record: Dict[str, Any], p_id: int) -> Dict[str, Any]:
    """Convert one JSON applicant record into the columns expected by PostgreSQL."""
    program = first_present(record, "program_name_cleaned", "program_name")
    university = first_present(record, "university_cleaned", "university")
    combined_program = " - ".join(part for part in (university, program) if part)

    llm_program = first_present(record, "llm_generated_program", "program_name_cleaned", "program_name")
    llm_university = first_present(
        record,
        "llm_generated_university",
        "university_cleaned",
        "university",
    )

    return {
        "p_id": p_id,
        "program": combined_program or None,
        "comments": first_present(record, "comments"),
        "date_added": parse_date(first_present(record, "date_added")),
        "url": first_present(record, "entry_url", "url") or f"generated:{p_id}",
        "status": first_present(record, "applicant_status", "status"),
        "term": first_present(record, "term"),
        "us_or_international": first_present(record, "student_origin", "us_or_international"),
        "gpa": parse_float(record.get("gpa")),
        "gre": parse_float(record.get("gre_score") or record.get("gre")),
        "gre_v": parse_float(record.get("gre_v_score") or record.get("gre_v")),
        "gre_aw": parse_float(record.get("gre_aw")),
        "degree": first_present(record, "degree"),
        "llm_generated_program": llm_program,
        "llm_generated_university": llm_university,
    }


def load_applicants(input_path: Path, reset: bool = False) -> int:
    records = load_json(input_path)
    normalized_records = [normalize_record(record, index + 1) for index, record in enumerate(records)]

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE_SQL)
            if reset:
                cur.execute("TRUNCATE applicants;")
            # executemany keeps the load logic simple while still using parameterized SQL.
            cur.executemany(INSERT_SQL, normalized_records)
        conn.commit()

    return len(normalized_records)


def main() -> None:
    parser = argparse.ArgumentParser(description="Load cleaned Grad Cafe JSON into PostgreSQL.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--reset", action="store_true", help="Clear applicants before loading.")
    args = parser.parse_args()

    count = load_applicants(args.input, reset=args.reset)
    print(f"Loaded {count:,} applicant records into PostgreSQL.")


if __name__ == "__main__":
    main()
