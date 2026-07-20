import os
from openai import OpenAI


def generate_report(prompt: str) -> str:
    model = os.environ.get("OPENAI_MODEL", "gpt-5.6")

    client = OpenAI()

    response = client.responses.create(
        model=model,
        input=prompt
    )

    return response.output_text