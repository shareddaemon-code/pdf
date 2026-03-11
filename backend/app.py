import os
import uuid
import base64
from datetime import datetime

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from db import Base, engine, get_db
from models import User, Chat, Message
from schemas import (
    SignupRequest,
    LoginRequest,
    TokenResponse,
    UserResponse,
    ChatCreateRequest,
    ChatListResponse,
    ChatDetailResponse,
    AskChatResponse,
)
from auth import hash_password, verify_password, create_access_token, decode_access_token

load_dotenv()

Base.metadata.create_all(bind=engine)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-5-nano")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

security = HTTPBearer(
    bearerFormat="JWT",
    description="Paste your JWT token here",
)

app = FastAPI(title="PDF Chat Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://pdf-theta-lovat.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials
    payload = decode_access_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


def save_uploaded_pdf(file: UploadFile, chat_id: int) -> tuple[str, str]:
    original_name = file.filename or "document.pdf"
    ext = os.path.splitext(original_name)[1].lower()

    if ext != ".pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    safe_name = f"chat_{chat_id}_{uuid.uuid4().hex}.pdf"
    relative_path = os.path.join(UPLOAD_DIR, safe_name)
    absolute_path = os.path.abspath(relative_path)

    return original_name, absolute_path


async def write_pdf_to_disk(file: UploadFile, absolute_path: str) -> None:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded PDF is empty")

    with open(absolute_path, "wb") as f:
        f.write(content)


def build_openrouter_messages(chat: Chat, question: str) -> list[dict]:
    if not chat.pdf_path or not os.path.exists(chat.pdf_path):
        raise HTTPException(status_code=400, detail="PDF not found for this chat")

    with open(chat.pdf_path, "rb") as f:
        pdf_bytes = f.read()

    pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")
    pdf_data_url = f"data:application/pdf;base64,{pdf_base64}"

    messages = []

    for msg in chat.messages:
        messages.append(
            {
                "role": msg.role,
                "content": msg.content,
            }
        )

    messages.append(
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "You are continuing a conversation about the uploaded PDF. "
                        "Answer the user's latest question using the PDF and prior chat context. "
                        "If the answer is not clearly present in the document, say so.\n\n"
                        f"Latest question: {question}"
                    ),
                },
                {
                    "type": "file",
                    "file": {
                        "filename": chat.pdf_filename or "document.pdf",
                        "file_data": pdf_data_url,
                    },
                },
            ],
        }
    )

    return messages


async def call_openrouter(payload: dict) -> dict:
    if not OPENROUTER_API_KEY:
        raise HTTPException(status_code=500, detail="Missing OPENROUTER_API_KEY")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=300) as client:
        response = await client.post(
            OPENROUTER_URL,
            headers=headers,
            json=payload,
        )

    if response.status_code != 200:
        try:
            err = response.json()
        except Exception:
            err = response.text
        raise HTTPException(status_code=500, detail=f"OpenRouter error: {err}")

    return response.json()


def extract_answer(data: dict) -> str:
    answer = ""
    choices = data.get("choices", [])

    if choices:
        message = choices[0].get("message", {})
        content = message.get("content", "")

        if isinstance(content, str):
            answer = content
        elif isinstance(content, list):
            parts = []
            for item in content:
                if item.get("type") == "text":
                    parts.append(item.get("text", ""))
            answer = "\n".join(parts).strip()

    return answer or "No answer returned."


@app.get("/")
def root():
    return {"message": "PDF chat backend is running"}


@app.get("/health")
def health_check():
    return {"ok": True}


@app.post("/auth/signup", response_model=TokenResponse)
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == payload.email.lower()).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    user = User(
        name=payload.name.strip(),
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    access_token = create_access_token(user.id, user.email)
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    access_token = create_access_token(user.id, user.email)
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/auth/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@app.get("/chats", response_model=list[ChatListResponse])
def list_chats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    chats = (
        db.query(Chat)
        .filter(Chat.user_id == current_user.id)
        .order_by(Chat.updated_at.desc(), Chat.id.desc())
        .all()
    )
    return chats


@app.post("/chats", response_model=ChatListResponse)
def create_chat(
    payload: ChatCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    title = (payload.title or "New Chat").strip() or "New Chat"

    chat = Chat(
        title=title,
        user_id=current_user.id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return chat


@app.get("/chats/{chat_id}", response_model=ChatDetailResponse)
def get_chat(
    chat_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    chat = (
        db.query(Chat)
        .filter(Chat.id == chat_id, Chat.user_id == current_user.id)
        .first()
    )

    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    return chat


@app.post("/chats/{chat_id}/ask", response_model=AskChatResponse)
async def ask_chat(
    chat_id: int,
    question: str = Form(...),
    file: UploadFile | None = File(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    chat = (
        db.query(Chat)
        .filter(Chat.id == chat_id, Chat.user_id == current_user.id)
        .first()
    )

    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    if not question.strip():
        raise HTTPException(status_code=400, detail="Question is required")

    if file is not None:
        original_name, absolute_path = save_uploaded_pdf(file, chat.id)
        await write_pdf_to_disk(file, absolute_path)

        chat.pdf_filename = original_name
        chat.pdf_path = absolute_path

        if chat.title == "New Chat":
            chat.title = os.path.splitext(original_name)[0][:80]

    if not chat.pdf_path:
        raise HTTPException(status_code=400, detail="Please upload a PDF for this chat first")

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": build_openrouter_messages(chat, question),
    }

    data = await call_openrouter(payload)
    answer = extract_answer(data)

    user_message = Message(
        chat_id=chat.id,
        role="user",
        content=question,
        created_at=datetime.utcnow(),
    )
    assistant_message = Message(
        chat_id=chat.id,
        role="assistant",
        content=answer,
        created_at=datetime.utcnow(),
    )

    db.add(user_message)
    db.add(assistant_message)

    chat.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(chat)

    return {
        "id": chat.id,
        "title": chat.title,
        "pdf_filename": chat.pdf_filename,
        "question": question,
        "answer": answer,
        "messages": chat.messages,
        "model": OPENROUTER_MODEL,
    }