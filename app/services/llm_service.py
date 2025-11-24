import os
import re
import json
import openai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize OpenAI client
openai.api_key = os.getenv("OPENAI_API_KEY")

SYSTEM_PROMPT = """
You are an assistant that reads a description of a user interface and provides a concise sequence of steps
to accomplish the user's requested task. Return JSON with fields:
- steps: list of human-friendly steps
- highlights: optional list of regions {x,y,w,h,reason}
Instructions for steps:
- Include the relative position of important buttons or elements in simple terms like 'top-left', 'bottom-right', 'center', etc.
- Be concise and actionable
"""



def plan_actions(vision, ocr_items, user_question: str):
    prompt = SYSTEM_PROMPT + "\n\n" + json.dumps({
        "vision": vision,
        "ocr_items": ocr_items,
        "user_question": user_question
    }, indent=2)

    resp = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        max_tokens=600
    )
    text = resp.choices[0].message.content
    try:
        result = json.loads(text)
    except Exception:
        result = {"text": text}
    return result


