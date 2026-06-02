from pathlib import Path

from pdf_utils import write_simple_pdf
from query_data import run_all_queries


def build_paragraphs() -> list[str]:
    results = {result["key"]: result["answer"] for result in run_all_queries()}

    return [
        (
            "Grad Cafe data is useful for learning SQL because it contains many real-looking "
            "application records, but it is not a representative sample of all graduate school "
            "applicants. The site depends on anonymous self-submission, so the data can overrepresent "
            "people who are especially motivated to report good news, bad news, or unusual outcomes. "
            "It can also contain missing values, inconsistent labels, duplicate-looking entries, "
            "rounding, exaggeration, or mistakes because there is no admissions office verifying each "
            "GPA, GRE score, school name, program, or decision status. Those limits mean the SQL "
            "answers should be read as patterns in the submitted Grad Cafe records, not as official "
            "statistics about graduate admissions."
        ),
        (
            "The latest SQL run reinforces those limitations. In the current database, "
            f"{results['fall_2026_count']} records are Fall 2026 entries, "
            f"{results['fall_2026_acceptance_percent']} percent of Fall 2026 entries are acceptances, "
            f"and {results['original_question_comments']} percent of all rows include comments. "
            f"The metric averages are {results['metric_averages']}, but the raw GRE field mixes "
            "different reporting scales, so that unfiltered GRE average should be interpreted with "
            "extra caution. Similar selection and formatting effects can affect acceptance rates, "
            "GPA averages, and school-specific counts. The data is still valuable for exploratory "
            "analysis, but the results describe anonymous self-reported entries, not verified "
            "admissions outcomes."
        ),
    ]


def main() -> None:
    output_path = Path(__file__).resolve().parent / "limitations.pdf"
    write_simple_pdf(output_path, "Limitations of Anonymous Grad Cafe Data", build_paragraphs())
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
