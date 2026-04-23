from pydantic import BaseModel

class ChatRequest(BaseModel):
    message: str
    history: list

class ChatResponse(BaseModel):
    response: str
    history: list