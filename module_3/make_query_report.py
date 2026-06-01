from pathlib import Path

from pdf_utils import write_simple_pdf
from query_data import run_all_queries


def main() -> None:
    paragraphs = []
    for index, result in enumerate(run_all_queries(), start=1):
        paragraphs.append(f"{index}. {result['question']}")
        paragraphs.append(f"Answer: {result['answer']}")
        paragraphs.append(f"Query used: {result['sql']}")
        paragraphs.append(f"Why this query: {result['explanation']}")

    output_path = Path(__file__).resolve().parent / "analysis_results.pdf"
    write_simple_pdf(output_path, "Grad Cafe SQL Query Results", paragraphs)
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
