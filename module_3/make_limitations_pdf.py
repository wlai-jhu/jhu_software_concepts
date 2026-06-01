from pathlib import Path

from pdf_utils import write_simple_pdf


PARAGRAPHS = [
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
        "The analysis results may look surprising when compared with national or institutional "
        "standards because the people who report to Grad Cafe are probably not distributed like "
        "the full applicant population. For example, an average GRE quantitative score from Grad "
        "Cafe can be much higher than a broader benchmark if applicants with strong scores are "
        "more willing to disclose them, if international STEM applicants are overrepresented, or "
        "if users without scores leave the field blank and are excluded from averages. In my "
        "cleaned dataset, 31,430 of 50,000 records are Fall 2026 entries, about 37.08 percent "
        "of those Fall 2026 entries are acceptances, and about 47.73 percent of all rows include "
        "comments. The modern-scale GRE quantitative subset averages about 165.81, while the raw "
        "GRE field contains mixed scales that make an unfiltered average misleading. Similar "
        "selection and formatting effects can affect acceptance rates, GPA averages, and "
        "school-specific counts. The data is still valuable for exploratory analysis, but the "
        "limitations make careful wording important: the results describe anonymous self-reported "
        "entries, not verified admissions outcomes."
    ),
]


def main() -> None:
    output_path = Path(__file__).resolve().parent / "limitations.pdf"
    write_simple_pdf(output_path, "Limitations of Anonymous Grad Cafe Data", PARAGRAPHS)
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
