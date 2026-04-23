from sqlalchemy.orm import Session
from app.core.config import settings
from openai import OpenAI
from app.chat.chat_tools import TOOL_DEFINITIONS, execute_tool
from datetime import date
import json

MAX_TOOL_CALLS = 5
today = date.today().isoformat()

client = OpenAI(api_key=settings.OPENAI_API_KEY)

_SYSTEM_PROMPT = (
    f"You are a helpful assistant for a business. Today's date is {today}. "
    "Answer based on the data provided to you."
)

def process_message(db: Session, org_id, user_message: str, history: list) -> dict:

    # Strip any system/tool messages the client may have injected — the server
    # always controls the system prompt.  Allowing client-supplied system messages
    # would open a prompt-injection vector.
    safe_history = [
        msg for msg in history
        if msg.get("role") not in ("system", "tool")
    ]

    messages = [{"role": "system", "content": _SYSTEM_PROMPT}] + safe_history

    messages.append({"role": "user", "content": user_message})

    loop_count = 0
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        tools=TOOL_DEFINITIONS,
    )
    response_message = response.choices[0].message

    while response_message.tool_calls and loop_count < MAX_TOOL_CALLS:
        loop_count += 1

        messages.append(json.loads(response_message.model_dump_json()))

        for tool_call in response_message.tool_calls:
            tool_name = tool_call.function.name
            tool_parameters = json.loads(tool_call.function.arguments)

            result = execute_tool(tool_name, tool_parameters, db, org_id)

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result),
            })

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=TOOL_DEFINITIONS,
        )
        response_message = response.choices[0].message

    # If we hit the tool-call limit and the model still hasn't produced a text
    # reply, force a final completion with tool_choice="none" so we always
    # return a non-null response to the caller.
    if response_message.content is None:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=TOOL_DEFINITIONS,
            tool_choice="none",
        )
        response_message = response.choices[0].message

    messages.append({
        "role": "assistant",
        "content": response_message.content,
    })

    return {
        "response": response_message.content,
        "history": messages,
    }
