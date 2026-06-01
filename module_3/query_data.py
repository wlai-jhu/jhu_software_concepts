from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from db import connect, require_psycopg


@dataclass(frozen=True)
class AnalysisQuestion:
    key: str
    question: str
    sql: str
    explanation: str
    value_field: str = "answer"


ANALYSIS_QUESTIONS: List[AnalysisQuestion] = [
    AnalysisQuestion(
        "fall_2026_count",
        "How many entries applied for Fall 2026?",
        """
        SELECT COUNT(*) AS answer
        FROM applicants
        WHERE term = 'Fall 2026';
        """,
        "Counts every applicant row whose start term is exactly Fall 2026.",
    ),
    AnalysisQuestion(
        "international_percent",
        "What percentage of entries are international students?",
        """
        SELECT ROUND(
            100.0 * COUNT(*) FILTER (
                WHERE us_or_international NOT IN ('American', 'Other')
            ) / NULLIF(COUNT(*), 0),
            2
        ) AS answer
        FROM applicants;
        """,
        "Divides entries not marked American or Other by the full table count.",
    ),
    AnalysisQuestion(
        "metric_averages",
        "What are the average GPA, GRE, GRE V, and GRE AW values?",
        """
        SELECT
            ROUND(AVG(gpa)::numeric, 2) AS avg_gpa,
            ROUND(AVG(gre)::numeric, 2) AS avg_gre,
            ROUND(AVG(gre_v)::numeric, 2) AS avg_gre_v,
            ROUND(AVG(gre_aw)::numeric, 2) AS avg_gre_aw
        FROM applicants;
        """,
        "Uses AVG, which ignores NULL values, so only applicants who provided each metric contribute to that metric.",
        value_field="summary",
    ),
    AnalysisQuestion(
        "american_fall_2026_gpa",
        "What is the average GPA of American students in Fall 2026?",
        """
        SELECT ROUND(AVG(gpa)::numeric, 2) AS answer
        FROM applicants
        WHERE term = 'Fall 2026'
          AND us_or_international = 'American';
        """,
        "Filters to American Fall 2026 entries and averages non-missing GPA values.",
    ),
    AnalysisQuestion(
        "fall_2026_acceptance_percent",
        "What percent of Fall 2026 entries are acceptances?",
        """
        SELECT ROUND(
            100.0 * COUNT(*) FILTER (WHERE status = 'Accepted') / NULLIF(COUNT(*), 0),
            2
        ) AS answer
        FROM applicants
        WHERE term = 'Fall 2026';
        """,
        "Computes the accepted share among Fall 2026 entries.",
    ),
    AnalysisQuestion(
        "fall_2026_accepted_gpa",
        "What is the average GPA of accepted Fall 2026 applicants?",
        """
        SELECT ROUND(AVG(gpa)::numeric, 2) AS answer
        FROM applicants
        WHERE term = 'Fall 2026'
          AND status = 'Accepted';
        """,
        "Filters to accepted Fall 2026 entries and averages available GPAs.",
    ),
    AnalysisQuestion(
        "jhu_masters_cs_count",
        "How many entries applied to JHU for a master's degree in Computer Science?",
        """
        SELECT COUNT(*) AS answer
        FROM applicants
        WHERE degree ILIKE 'Masters'
          AND program ILIKE '%Computer Science%'
          AND (
              program ILIKE '%Johns Hopkins%'
              OR program ILIKE '%JHU%'
          );
        """,
        "Uses the downloaded program string to match JHU or Johns Hopkins, Computer Science, and Masters.",
    ),
    AnalysisQuestion(
        "target_school_phd_cs_acceptances",
        "How many 2026 acceptances applied to Georgetown, MIT, Stanford, or Carnegie Mellon for a CS PhD?",
        """
        SELECT COUNT(*) AS answer
        FROM applicants
        WHERE term ILIKE '%2026%'
          AND status = 'Accepted'
          AND degree ILIKE 'PhD'
          AND program ILIKE '%Computer Science%'
          AND (
              program ILIKE '%Georgetown University%'
              OR program ILIKE '%MIT%'
              OR program ILIKE '%Massachusetts Institute of Technology%'
              OR program ILIKE '%Stanford University%'
              OR program ILIKE '%Carnegie Mellon University%'
          );
        """,
        "Uses downloaded fields to count accepted 2026 CS PhD entries at the requested universities.",
    ),
    AnalysisQuestion(
        "target_school_phd_cs_acceptances_llm",
        "Does question 8 change when using LLM generated fields?",
        """
        WITH downloaded_fields AS (
            SELECT COUNT(*) AS count
            FROM applicants
            WHERE term ILIKE '%2026%'
              AND status = 'Accepted'
              AND degree ILIKE 'PhD'
              AND program ILIKE '%Computer Science%'
              AND (
                  program ILIKE '%Georgetown University%'
                  OR program ILIKE '%MIT%'
                  OR program ILIKE '%Massachusetts Institute of Technology%'
                  OR program ILIKE '%Stanford University%'
                  OR program ILIKE '%Carnegie Mellon University%'
              )
        ),
        llm_fields AS (
            SELECT COUNT(*) AS count
            FROM applicants
            WHERE term ILIKE '%2026%'
              AND status = 'Accepted'
              AND degree ILIKE 'PhD'
              AND llm_generated_program ILIKE '%Computer Science%'
              AND (
                  llm_generated_university ILIKE '%Georgetown University%'
                  OR llm_generated_university ILIKE '%MIT%'
                  OR llm_generated_university ILIKE '%Massachusetts Institute of Technology%'
                  OR llm_generated_university ILIKE '%Stanford University%'
                  OR llm_generated_university ILIKE '%Carnegie Mellon University%'
              )
        )
        SELECT
            downloaded_fields.count AS downloaded_count,
            llm_fields.count AS llm_count,
            downloaded_fields.count <> llm_fields.count AS changed
        FROM downloaded_fields, llm_fields;
        """,
        "Compares the downloaded-field count from question 8 with the same count using standardized LLM program and university fields.",
        value_field="comparison",
    ),
    AnalysisQuestion(
        "original_question_comments",
        "Original question: What percentage of entries include applicant comments?",
        """
        SELECT ROUND(
            100.0 * COUNT(*) FILTER (WHERE comments IS NOT NULL AND LENGTH(TRIM(comments)) > 0)
            / NULLIF(COUNT(*), 0),
            2
        ) AS answer
        FROM applicants;
        """,
        "Measures how often self-submitted rows include non-empty comments.",
    ),
    AnalysisQuestion(
        "original_question_statuses",
        "Original question: What are the most common applicant statuses?",
        """
        SELECT status, COUNT(*) AS count
        FROM applicants
        GROUP BY status
        ORDER BY count DESC, status
        LIMIT 5;
        """,
        "Groups entries by decision status and returns the five most frequent statuses.",
        value_field="table",
    ),
]


def format_result(question: AnalysisQuestion, row: Optional[Dict[str, Any]], rows: List[Dict[str, Any]]) -> str:
    if question.value_field == "summary" and row:
        return (
            f"GPA: {row['avg_gpa']}, GRE Q: {row['avg_gre']}, "
            f"GRE V: {row['avg_gre_v']}, GRE AW: {row['avg_gre_aw']}"
        )
    if question.value_field == "table":
        return "; ".join(f"{item['status'] or 'Unknown'}: {item['count']}" for item in rows)
    if question.value_field == "comparison" and row:
        changed_text = "changed" if row["changed"] else "did not change"
        return (
            f"Downloaded fields: {row['downloaded_count']}; "
            f"LLM fields: {row['llm_count']}; result {changed_text}."
        )
    if not row:
        return "No result"
    return str(row.get("answer"))


def run_query(question: AnalysisQuestion) -> Dict[str, Any]:
    require_psycopg()
    dict_row = __import__("psycopg.rows", fromlist=["dict_row"]).dict_row
    with connect(row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(question.sql)
            rows = cur.fetchall()

    first_row = rows[0] if rows else None
    return {
        "key": question.key,
        "question": question.question,
        "sql": " ".join(question.sql.split()),
        "explanation": question.explanation,
        "rows": rows,
        "answer": format_result(question, first_row, rows),
    }


def run_all_queries() -> List[Dict[str, Any]]:
    return [run_query(question) for question in ANALYSIS_QUESTIONS]


def main() -> None:
    for index, result in enumerate(run_all_queries(), start=1):
        print(f"{index}. {result['question']}")
        print(f"   Answer: {result['answer']}")
        print(f"   Query: {result['sql']}")
        print()


if __name__ == "__main__":
    main()
