import unittest
from unittest.mock import Mock, patch

from app.ai_analysis import (
    FALLBACK_INSIGHT,
    build_finance_insight_prompt,
    format_query_results_for_prompt,
    format_supporting_context_for_prompt,
    generate_finance_insight_with_gemini,
    generate_fallback_finance_insight,
    parse_gemini_text_response,
)


class FinanceInsightPromptTests(unittest.TestCase):
    def test_formats_columns_and_rows_for_prompt(self):
        formatted = format_query_results_for_prompt(
            columns=["category", "total_spent"],
            rows=[["dining", 42.5], ["groceries", 18.25]],
        )

        self.assertIn('"category": "dining"', formatted)
        self.assertIn('"total_spent": 42.5', formatted)

    def test_build_prompt_includes_finance_rules_and_context(self):
        prompt = build_finance_insight_prompt(
            user_question="How much did I spend on dining?",
            sql_query="SELECT spending_category, SUM(amount) FROM transactions",
            query_results='[{"category": "dining", "total_spent": 42.5}]',
            supporting_context='[{"merchant_name": "Starbucks", "description": "Coffee and breakfast"}]',
        )

        self.assertIn("You are a helpful personal finance analysis assistant.", prompt)
        self.assertIn("How much did I spend on dining?", prompt)
        self.assertIn("Only use the data provided above.", prompt)
        self.assertIn("SELECT spending_category", prompt)
        self.assertIn("Starbucks", prompt)
        self.assertIn("explain likely drivers", prompt)

    def test_formats_supporting_context_for_prompt(self):
        formatted = format_supporting_context_for_prompt([
            {
                "merchant_name": "Trader Joes",
                "amount": -91.75,
                "spending_category": "groceries",
                "description": "Bought weekly groceries.",
            }
        ])

        self.assertIn('"merchant_name": "Trader Joes"', formatted)
        self.assertIn('"description": "Bought weekly groceries."', formatted)

    def test_parse_gemini_text_response_returns_candidate_text(self):
        body = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "Dining was your largest returned category."},
                        ],
                    },
                },
            ],
        }

        self.assertEqual(parse_gemini_text_response(body), "Dining was your largest returned category.")

    def test_parse_gemini_text_response_falls_back_for_missing_text(self):
        self.assertEqual(parse_gemini_text_response({"candidates": []}), FALLBACK_INSIGHT)

    def test_generate_finance_insight_uses_gemini_api_key_header(self):
        response = Mock()
        response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Dining was the only returned category."}]}}],
        }
        response.raise_for_status.return_value = None

        with (
            patch.dict("os.environ", {"GEMINI_API_URL": "https://example.test/models/{model}:generateContent"}),
            patch("app.ai_analysis.requests.post", return_value=response) as post,
        ):
            insight = generate_finance_insight_with_gemini(
                user_question="How much did I spend on dining?",
                sql_query="SELECT * FROM transactions",
                columns=["category"],
                rows=[["dining"]],
                api_key="test-key",
            )

        self.assertEqual(insight, "Dining was the only returned category.")
        self.assertEqual(post.call_args.kwargs["headers"], {"x-goog-api-key": "test-key"})

    def test_generate_finance_insight_uses_gemini_config_from_environment(self):
        response = Mock()
        response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Used environment config."}]}}],
        }
        response.raise_for_status.return_value = None

        with (
            patch.dict(
                "os.environ",
                {
                    "GEMINI_API_URL": "https://example.test/models/{model}:generateContent",
                    "GEMINI_MODEL": "gemini-env-model",
                },
            ),
            patch("app.ai_analysis.requests.post", return_value=response) as post,
        ):
            insight = generate_finance_insight_with_gemini(
                user_question="How much did I spend on dining?",
                sql_query="SELECT * FROM transactions",
                columns=["category"],
                rows=[["dining"]],
                api_key="test-key",
            )

        self.assertEqual(insight, "Used environment config.")
        self.assertEqual(
            post.call_args.args[0],
            "https://example.test/models/gemini-env-model:generateContent",
        )

    def test_generate_finance_insight_uses_explicit_model_override(self):
        response = Mock()
        response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Used custom model."}]}}],
        }
        response.raise_for_status.return_value = None

        with (
            patch.dict("os.environ", {"GEMINI_API_URL": "https://example.test/models/{model}:generateContent"}),
            patch("app.ai_analysis.requests.post", return_value=response) as post,
        ):
            insight = generate_finance_insight_with_gemini(
                user_question="How much did I spend on dining?",
                sql_query="SELECT * FROM transactions",
                columns=["category"],
                rows=[["dining"]],
                api_key="test-key",
                model="custom-model",
            )

        self.assertEqual(insight, "Used custom model.")
        self.assertEqual(
            post.call_args.args[0],
            "https://example.test/models/custom-model:generateContent",
        )

    def test_generate_finance_insight_requires_gemini_api_url_from_environment(self):
        with patch.dict("os.environ", {"GEMINI_API_URL": ""}):
            with self.assertRaises(ValueError) as context:
                generate_finance_insight_with_gemini(
                    user_question="How much did I spend on dining?",
                    sql_query="SELECT * FROM transactions",
                    columns=["category"],
                    rows=[["dining"]],
                    api_key="test-key",
                )

        self.assertEqual(str(context.exception), "GEMINI_API_URL must be set")

    def test_generate_finance_insight_requires_https_gemini_api_url(self):
        with patch.dict("os.environ", {"GEMINI_API_URL": "http://example.test/models/{model}:generateContent"}):
            with self.assertRaises(ValueError) as context:
                generate_finance_insight_with_gemini(
                    user_question="How much did I spend on dining?",
                    sql_query="SELECT * FROM transactions",
                    columns=["category"],
                    rows=[["dining"]],
                    api_key="test-key",
                )

        self.assertEqual(str(context.exception), "GEMINI_API_URL must be an HTTPS URL")

    def test_generate_finance_insight_requires_model_placeholder_in_gemini_api_url(self):
        with patch.dict("os.environ", {"GEMINI_API_URL": "https://example.test/models/gemini:generateContent"}):
            with self.assertRaises(ValueError) as context:
                generate_finance_insight_with_gemini(
                    user_question="How much did I spend on dining?",
                    sql_query="SELECT * FROM transactions",
                    columns=["category"],
                    rows=[["dining"]],
                    api_key="test-key",
                )

        self.assertEqual(str(context.exception), "GEMINI_API_URL must include {model}")

    def test_generate_finance_insight_uses_explicit_model_override(self):
        response = Mock()
        response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Used explicit model."}]}}],
        }
        response.raise_for_status.return_value = None

        with (
            patch.dict("os.environ", {"GEMINI_API_URL": "https://example.test/models/{model}:generateContent"}),
            patch("app.ai_analysis.requests.post", return_value=response) as post,
        ):
            insight = generate_finance_insight_with_gemini(
                user_question="How much did I spend on dining?",
                sql_query="SELECT * FROM transactions",
                columns=["category"],
                rows=[["dining"]],
                api_key="test-key",
                model="custom-model",
            )

        self.assertEqual(insight, "Used explicit model.")
        self.assertEqual(post.call_args.args[0], "https://example.test/models/custom-model:generateContent")

    def test_generate_finance_insight_rejects_invalid_model_name(self):
        with patch.dict("os.environ", {"GEMINI_API_URL": "https://example.test/models/{model}:generateContent"}):
            with self.assertRaises(ValueError) as context:
                generate_finance_insight_with_gemini(
                    user_question="How much did I spend on dining?",
                    sql_query="SELECT * FROM transactions",
                    columns=["category"],
                    rows=[["dining"]],
                    api_key="test-key",
                    model="../metadata",
                )

        self.assertEqual(str(context.exception), "GEMINI_MODEL contains invalid characters")

    def test_generate_finance_insight_falls_back_without_api_key(self):
        insight = generate_finance_insight_with_gemini(
            user_question="How much did I spend on dining?",
            sql_query="SELECT * FROM transactions",
            columns=[],
            rows=[],
            api_key="",
        )

        self.assertEqual(insight, "No matching data was found. Try asking about a specific category, merchant, budget, or time period.")

    def test_fallback_finance_insight_explains_null_aggregate_as_no_matching_data(self):
        insight = generate_fallback_finance_insight(
            user_question="How much did I spend on food?",
            columns=["total_spending"],
            rows=[[None]],
            supporting_context=[],
        )

        self.assertEqual(insight, "No matching data was found. Try asking about a specific category, merchant, budget, or time period.")

    def test_fallback_finance_insight_uses_supporting_context_for_aggregate(self):
        insight = generate_fallback_finance_insight(
            user_question="How much did I spend on groceries?",
            columns=["total_spending"],
            rows=[[-250.0]],
            supporting_context=[
                {
                    "merchant_name": "Trader Joes",
                    "amount": -100.0,
                    "description": "Weekly groceries and pantry staples.",
                },
                {
                    "merchant_name": "Whole Foods",
                    "amount": -80.0,
                    "description": "Produce and household groceries.",
                },
            ],
        )

        self.assertIn("Trader Joes", insight)
        self.assertIn("Whole Foods", insight)


if __name__ == "__main__":
    unittest.main()
