import argparse
import json
import re
from html import unescape
from pathlib import Path
from typing import Dict, List, Optional


DEFAULT_INPUT_PATH = "data/raw_applicant_data.json"
DEFAULT_OUTPUT_PATH = "applicant_data.json"


UNIVERSITY_FIXES = {
    "jhu": "Johns Hopkins University",
    "john hopkins": "Johns Hopkins University",
    "johns hopkins": "Johns Hopkins University",
    "umd": "University of Maryland",
    "univ of maryland": "University of Maryland",
}


def load_data(input_path: str = DEFAULT_INPUT_PATH) -> List[Dict[str, Optional[str]]]:
    return json.loads(Path(input_path).read_text(encoding="utf-8"))


def save_data(records: List[Dict[str, Optional[str]]], output_path: str = DEFAULT_OUTPUT_PATH) -> None:
    Path(output_path).write_text(json.dumps(records, indent=2), encoding="utf-8")


def clean_data(records: List[Dict[str, Optional[str]]]) -> List[Dict[str, Optional[str]]]:
    cleaned_records = []
    for record in records:
        cleaned = dict(record)
        cleaned["program_name_cleaned"] = _clean_program_name(record.get("program_name"))
        cleaned["university_cleaned"] = _clean_university_name(record.get("university"))
        cleaned["llm_generated_program"] = _clean_optional_text(record.get("llm_generated_program"))
        cleaned["llm_generated_university"] = _clean_optional_text(record.get("llm_generated_university"))
        cleaned["comments"] = _clean_optional_text(record.get("comments"))
        cleaned["raw_text"] = _clean_optional_text(record.get("raw_text"))
        cleaned_records.append(cleaned)
    return cleaned_records


def _clean_optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = unescape(str(value))
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _clean_program_name(value: Optional[str]) -> Optional[str]:
    text = _clean_optional_text(value)
    if not text:
        return None
    text = re.sub(r"\s*[-|]\s*", " - ", text)
    return text


def _clean_university_name(value: Optional[str]) -> Optional[str]:
    text = _clean_optional_text(value)
    if not text:
        return None
    key = re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()
    return UNIVERSITY_FIXES.get(key, text)


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean scraped Grad Cafe applicant data.")
    parser.add_argument("--input", default=DEFAULT_INPUT_PATH)
    parser.add_argument("--output", default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    records = load_data(args.input)
    cleaned_records = clean_data(records)
    save_data(cleaned_records, args.output)
    print(f"Saved {len(cleaned_records)} cleaned records to {args.output}")


if __name__ == "__main__":
    main()
