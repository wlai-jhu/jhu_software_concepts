import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set

from clean import clean_data, load_data, save_data


DEFAULT_INPUT_PATH = "data/raw_applicant_data.json"
DEFAULT_OUTPUT_PATH = "llm_extend_applicant_data.json"
DEFAULT_LLM_INPUT_PATH = "data/llm_input.json"
DEFAULT_LLM_OUTPUT_PATH = "data/llm_output.jsonl"
LLM_APP_PATH = Path("llm_hosting/app.py")


def prepare_llm_input(
    records: List[Dict[str, Optional[str]]],
    llm_input_path: str = DEFAULT_LLM_INPUT_PATH,
    llm_output_path: str = DEFAULT_LLM_OUTPUT_PATH,
    resume: bool = False,
) -> None:
    """Create the JSON format expected by llm_hosting/app.py."""
    completed_indexes = _completed_llm_indexes(llm_output_path) if resume else set()
    rows = []
    for index, record in enumerate(records):
        if index in completed_indexes:
            continue
        program = record.get("program_name") or ""
        university = record.get("university") or ""
        combined_program = ", ".join(part for part in [program, university] if part)
        rows.append(
            {
                "record_index": index,
                "program": combined_program,
                "original_program_name": program,
                "original_university": university,
            }
        )

    Path(llm_input_path).parent.mkdir(parents=True, exist_ok=True)
    Path(llm_input_path).write_text(json.dumps(rows, indent=2), encoding="utf-8")


def run_llm_standardizer(
    llm_input_path: str = DEFAULT_LLM_INPUT_PATH,
    llm_output_path: str = DEFAULT_LLM_OUTPUT_PATH,
    append: bool = False,
) -> None:
    """Run the assignment-provided local LLM standardizer."""
    if not LLM_APP_PATH.exists():
        raise FileNotFoundError("Expected module_2/llm_hosting/app.py to exist.")

    Path(llm_output_path).parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(LLM_APP_PATH),
        "--file",
        llm_input_path,
        "--out",
        llm_output_path,
    ]
    if append:
        command.append("--append")
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as exc:
        install_command = f"{sys.executable} -m pip install -r llm_hosting/requirements.txt"
        raise RuntimeError(
            "The local LLM standardizer failed. If the error mentions a missing module "
            f"such as Flask, huggingface_hub, or llama_cpp, run: {install_command}"
        ) from exc


def merge_llm_output(
    records: List[Dict[str, Optional[str]]],
    llm_output_path: str = DEFAULT_LLM_OUTPUT_PATH,
) -> List[Dict[str, Optional[str]]]:
    """Merge JSONL LLM output back into scraper records by record_index."""
    merged = [dict(record) for record in records]
    if not Path(llm_output_path).exists():
        return merged
    with Path(llm_output_path).open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            llm_row = json.loads(line)
            index = llm_row.get("record_index")
            if not isinstance(index, int) or index < 0 or index >= len(merged):
                continue
            merged[index]["llm_generated_program"] = llm_row.get("llm-generated-program")
            merged[index]["llm_generated_university"] = llm_row.get("llm-generated-university")
    return merged


def _completed_llm_indexes(llm_output_path: str = DEFAULT_LLM_OUTPUT_PATH) -> Set[int]:
    """Read completed record indexes from an existing JSONL output file."""
    completed: Set[int] = set()
    path = Path(llm_output_path)
    if not path.exists():
        return completed
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            index = row.get("record_index")
            if isinstance(index, int):
                completed.add(index)
    return completed


def clean_data_with_llm(
    input_path: str = DEFAULT_INPUT_PATH,
    output_path: str = DEFAULT_OUTPUT_PATH,
    skip_llm_run: bool = False,
    resume_llm: bool = False,
) -> List[Dict[str, Optional[str]]]:
    """Run local LLM standardization, merge results, and save extended applicant data."""
    records = load_data(input_path)
    prepare_llm_input(records, resume=resume_llm)
    if not skip_llm_run:
        run_llm_standardizer(append=resume_llm)
    merged_records = merge_llm_output(records)
    cleaned_records = clean_data(merged_records)

    for record in cleaned_records:
        if record.get("llm_generated_program"):
            record["program_name_cleaned"] = record["llm_generated_program"]
        elif not record.get("llm_generated_program"):
            record["llm_generated_program"] = record.get("program_name_cleaned")
        if record.get("llm_generated_university"):
            record["university_cleaned"] = record["llm_generated_university"]
        elif not record.get("llm_generated_university"):
            record["llm_generated_university"] = record.get("university_cleaned")

    save_data(cleaned_records, output_path)
    return cleaned_records


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean Grad Cafe data with local LLM standardization.")
    parser.add_argument("--input", default=DEFAULT_INPUT_PATH)
    parser.add_argument("--output", default=DEFAULT_OUTPUT_PATH)
    parser.add_argument(
        "--skip-llm-run",
        action="store_true",
        help="Merge an existing data/llm_output.jsonl instead of running the model again.",
    )
    parser.add_argument(
        "--resume-llm",
        action="store_true",
        help="Skip already completed record indexes in data/llm_output.jsonl and append new LLM output.",
    )
    args = parser.parse_args()

    records = clean_data_with_llm(
        input_path=args.input,
        output_path=args.output,
        skip_llm_run=args.skip_llm_run,
        resume_llm=args.resume_llm,
    )
    print(f"Saved {len(records)} LLM-cleaned records to {args.output}")


if __name__ == "__main__":
    main()
