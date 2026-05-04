import json
import os
from typing import Any

import requests


GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
FALLBACK_INSIGHT = "I found the data, but couldn’t generate an AI explanation for it."


def format_query_results_for_prompt(columns: list[str], rows: list[list[Any]]) -> str:
    """Convert SQL result columns/rows into compact JSON for Gemini."""
    records = [
        {column: row[index] if index < len(row) else None for index, column in enumerate(columns)}
        for row in rows
    ]
    return json.dumps(records, ensure_ascii=False, default=str)


def format_supporting_context_for_prompt(supporting_context: list[dict[str, Any]] | None) -> str:
    """Convert representative transaction rows into compact JSON for Gemini."""
    return json.dumps(supporting_context or [], ensure_ascii=False, default=str)


def build_finance_insight_prompt(
    user_question: str,
    sql_query: str,
    query_results: str,
    supporting_context: str = "[]",
) -> str:
    return f"""
You are a helpful personal finance analysis assistant.

The user asked:
<user_question>
{user_question}
</user_question>

The generated SQL query was:
<sql_query>
{sql_query}
</sql_query>

The database returned these rows:
<query_results>
{query_results}
</query_results>

Supporting transaction context:
<supporting_transactions>
{supporting_context}
</supporting_transactions>

Your task:
Explain what this result means in clear, concise natural language before the raw data is shown to the user. Use the supporting transactions to explain likely drivers behind totals when they are relevant.

Rules:
- Only use the data provided above.
- Treat the supporting transaction context as part of the provided data.
- Do not invent numbers, categories, merchants, time periods, or trends.
- If the result is empty, say that no matching data was found and suggest a more specific query.
- Do not mention backend implementation details unless useful.
- Do not say "based on the SQL query" unless necessary.
- Keep the response to 2-5 sentences.
- If there is an obvious insight, highlight it.
- If the result contains totals, rankings, categories, or budget comparisons, explain the key takeaway.
- If supporting transactions include descriptions, merchants, or unusually large purchases, use them to explain why the total may be high or low.
""".strip()


def parse_gemini_text_response(body: dict[str, Any]) -> str:
    try:
        text = body["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        return FALLBACK_INSIGHT

    normalized = " ".join(str(text).strip().split())
    return normalized or FALLBACK_INSIGHT


def generate_fallback_finance_insight(
    *,
    user_question: str,
    columns: list[str],
    rows: list[list[Any]],
    supporting_context: list[dict[str, Any]] | None = None,
) -> str:
    """Return a deterministic explanation when Gemini is unavailable."""
    if not rows:
        return "No matching data was found. Try asking about a specific category, merchant, budget, or time period."

    non_null_values = [
        value
        for row in rows
        for value in row
        if value is not None
    ]
    if not non_null_values:
        return "No matching data was found. Try asking about a specific category, merchant, budget, or time period."

    if supporting_context:
        merchants = []
        descriptions = []
        for item in supporting_context[:5]:
            merchant = item.get("merchant_name")
            if merchant and merchant not in merchants:
                merchants.append(str(merchant))
            description = item.get("description")
            if description:
                descriptions.append(str(description))

        merchant_text = ", ".join(merchants[:3])
        detail_text = f" The largest matching transactions include {merchant_text}." if merchant_text else ""
        if descriptions:
            detail_text += f" Context from the transaction descriptions points to: {descriptions[0]}"

        if len(rows) == 1 and len(columns) == 1:
            return f"The query returned {columns[0]}: {rows[0][0]}.{detail_text}"
        return f"I found matching transaction context for this question.{detail_text}"

    if len(rows) == 1 and len(columns) == 1:
        return f"The query returned {columns[0]}: {rows[0][0]}."

    return FALLBACK_INSIGHT


def generate_finance_insight_with_gemini(
    *,
    user_question: str,
    sql_query: str,
    columns: list[str],
    rows: list[list[Any]],
    supporting_context: list[dict[str, Any]] | None = None,
    api_key: str | None = None,
    model: str = GEMINI_MODEL,
    timeout_s: int = 30,
) -> str:
    """Generate a concise natural-language explanation for already-returned SQL results."""
    resolved_key = api_key if api_key is not None else os.getenv("GEMINI_API_KEY", "")
    gemini_api_key = resolved_key.strip()
    if not gemini_api_key:
        return generate_fallback_finance_insight(
            user_question=user_question,
            columns=columns,
            rows=rows,
            supporting_context=supporting_context,
        )

    query_results = format_query_results_for_prompt(columns=columns, rows=rows)
    supporting_transactions = format_supporting_context_for_prompt(supporting_context)
    prompt = build_finance_insight_prompt(
        user_question=user_question,
        sql_query=sql_query,
        query_results=query_results,
        supporting_context=supporting_transactions,
    )
    url = GEMINI_API_URL.format(model=model)
    payload: dict[str, Any] = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
        },
    }

    response = requests.post(url, headers={"x-goog-api-key": gemini_api_key}, json=payload, timeout=timeout_s)
    response.raise_for_status()
    return parse_gemini_text_response(response.json())
