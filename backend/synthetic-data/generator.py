"""Gemini API client and transaction generation."""

from google import genai

from config import API_KEY, MODEL_NAME, PROMPT_PATH


def load_prompt(prompt_path: str | None = None) -> str:
    """Load the transaction generation prompt from file."""
    path = prompt_path or PROMPT_PATH
    with open(path, "r") as f:
        return f.read()


def generate_transactions(prompt: str | None = None) -> str:
    """
    Call Gemini to generate synthetic transaction CSV.
    Returns raw CSV text.
    """
    if prompt is None:
        prompt = load_prompt()

    client = genai.Client(api_key=API_KEY)
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config={
            "response_mime_type": "text/plain",
        },
    )
    return response.text.strip()
