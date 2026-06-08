import re

import pytest
from bs4 import BeautifulSoup

from src.app import create_app
from src.query_data import ANALYSIS_QUESTIONS, format_result


@pytest.mark.analysis
def test_percentage_answers_are_formatted_with_two_decimals():
    question = next(item for item in ANALYSIS_QUESTIONS if item.key == "international_percent")

    answer = format_result(question, {"answer": 39.284}, [{"answer": 39.284}])

    assert answer == "39.28%"


@pytest.mark.analysis
def test_rendered_analysis_has_answer_labels_and_two_decimal_percentages():
    app = create_app(
        query_runner=lambda: [
            {
                "key": "international_percent",
                "question": "What percentage of entries are international students?",
                "sql": "SELECT 39.28;",
                "explanation": "Fixture result.",
                "rows": [{"answer": 39.28}],
                "answer": "39.28%",
            }
        ],
        testing=True,
    )

    response = app.test_client().get("/analysis")
    soup = BeautifulSoup(response.data, "html.parser")
    text = soup.get_text(" ")

    assert "Answer:" in text
    assert re.search(r"(?<!\d)\d+\.\d{2}%(?!\d)", text)


@pytest.mark.analysis
def test_analysis_formatter_covers_all_result_shapes():
    summary_question = next(item for item in ANALYSIS_QUESTIONS if item.value_field == "summary")
    table_question = next(item for item in ANALYSIS_QUESTIONS if item.value_field == "table")
    comparison_question = next(item for item in ANALYSIS_QUESTIONS if item.value_field == "comparison")
    count_question = next(item for item in ANALYSIS_QUESTIONS if item.key == "fall_2026_count")
    percent_question = next(item for item in ANALYSIS_QUESTIONS if item.key == "international_percent")

    assert format_result(
        summary_question,
        {"avg_gpa": 3.8, "avg_gre": 166, "avg_gre_v": 161, "avg_gre_aw": 4.5},
        [],
    ) == "GPA: 3.8, GRE Q: 166, GRE V: 161, GRE AW: 4.5"
    assert format_result(table_question, None, [{"status": None, "count": 2}]) == "Unknown: 2"
    assert "did not change" in format_result(
        comparison_question,
        {"downloaded_count": 1, "llm_count": 1, "changed": False},
        [],
    )
    assert format_result(count_question, None, []) == "No result"
    assert format_result(percent_question, {"answer": None}, [{"answer": None}]) == "No result"
