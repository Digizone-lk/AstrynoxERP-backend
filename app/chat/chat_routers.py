from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.user import User
from app.chat.chat_service import process_message
from app.chat.chat_schemas import ChatRequest, ChatResponse
from app.dependencies import get_sales_or_admin

router = APIRouter(prefix="/api/chat", tags=["chatbot"])

@router.post("/message", response_model=ChatResponse, status_code=status.HTTP_200_OK)
def send_message(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_sales_or_admin)
):
    result = process_message(db, current_user.org_id, payload.message, payload.history)

    return result