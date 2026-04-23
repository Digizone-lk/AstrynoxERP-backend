from sqlalchemy.orm import Session
from app.core.config import settings 
from openai import OpenAI
from app.chat.chat_tools import TOOL_DEFINITIONS, execute_tool
from datetime import date
import json

MAX_TOOL_CALLS = 5
today = date.today().isoformat()

client = OpenAI(api_key=settings.OPENAI_API_KEY)

def process_message(db: Session, org_id, user_message: str, history: list) -> dict:
    
    loop_count = 0
    
    if not history or history[0]["role"] != "system":
        history.insert(0,{
            "role": "system",
            "content": f"You are a helpful assistant for a business. Today's date is {today}. Answer based on the data provided to you. "
        })
    
    history.append({
        "role": "user",
        "content": user_message
        })
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=history,
        tools=TOOL_DEFINITIONS
    )

    response_message = response.choices[0].message

    while response_message.tool_calls and loop_count < MAX_TOOL_CALLS:
        loop_count += 1

        history.append(json.loads(response_message.model_dump_json()))

        for tool_call in response_message.tool_calls:
            tool_name = tool_call.function.name
            tool_parameters = json.loads(tool_call.function.arguments)
        
            #get the 1st llm call result message 
            result = execute_tool(tool_name, tool_parameters, db, org_id)

            #add 1st call response to the history
            history.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result)
                })

        #get for 2nd llm call for nlp answer
        response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=history,
        tools=TOOL_DEFINITIONS,
        )

        response_message = response.choices[0].message
    
    #append the final response for the user message
    history.append({
        "role": "assistant",
        "content": response_message.content})

    return {
        "response": response_message.content, 
        "history": history
        }