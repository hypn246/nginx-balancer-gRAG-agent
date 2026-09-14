import os
import dotenv
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langgraph.types import Command
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
import db, auth

from agent import grag_agent
from grag import GraphRAG, select_llm

dotenv.load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

CONNECTION_KWARGS = {
    "autocommit": True,
    "prepare_threshold": 0,
    "row_factory": dict_row,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_schema()
    print("Table ok")
    with ConnectionPool(
            conninfo=DATABASE_URL,
            min_size=1,
            max_size=10,
            max_idle=120,
            kwargs=CONNECTION_KWARGS,
            check=ConnectionPool.check_connection,
    ) as pool:
        checkpointer = PostgresSaver(pool)
        checkpointer.setup()

        shared_llm = select_llm(os.getenv("LLM_CHAT"))
        graph_rag_instance = GraphRAG(llm=shared_llm)
        app.state.agent = grag_agent(llm=shared_llm, grag=graph_rag_instance, checkpointer=checkpointer)

        yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://172.31.128.1:3000",
        "https://nlb-web-deployment.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class CreateChatRequest(BaseModel):
    title: str | None = None


class AgentRequest(BaseModel):
    chat_id: str
    message: str


class ApprovalRequest(BaseModel):
    approved: bool


# @app.post("/auth/register")
# async def register(request: RegisterRequest):
#     if db.get_user_by_username(request.username):
#         raise HTTPException(status_code=400, detail="Username already taken")

#     password_hash = auth.hash_password(request.password)
#     user_id = db.create_user(request.username, password_hash)
#     token = auth.create_token(user_id)
#     return {"user_id": user_id, "token": token}


@app.post("/auth/login")
async def login(request: LoginRequest):
    user = db.get_user_by_username(request.username)
    if not user or not auth.verify_password(request.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = auth.create_token(user["id"])
    return {"user_id": user["id"], "token": token}


@app.post("/chats")
async def create_chat(request: CreateChatRequest, user_id: int = Depends(auth.get_current_user)):
    chat_id = db.create_chat(user_id, request.title or "New Chat")
    return {"chat_id": chat_id}


@app.get("/chats")
async def list_chats(user_id: int = Depends(auth.get_current_user)):
    return {"chats": db.get_chats_for_user(user_id)}


@app.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str, http_request: Request, user_id: int = Depends(auth.get_current_user)):
    owner_id = db.get_chat_owner(chat_id)
    if owner_id is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    if owner_id != user_id:
        raise HTTPException(status_code=403, detail="Not your chat")

    db.delete_chat(chat_id)
    try:
        http_request.app.state.agent.checkpointer.delete_thread(chat_id)
    except Exception:
        pass

    return {"chat_id": chat_id, "deleted": True}


@app.get("/chats/{chat_id}/messages")
async def list_messages(chat_id: str, user_id: int = Depends(auth.get_current_user)):
    owner_id = db.get_chat_owner(chat_id)
    if owner_id is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    if owner_id != user_id:
        raise HTTPException(status_code=403, detail="Not your chat")

    return {"messages": db.get_messages_for_chat(chat_id)}


@app.post("/agent/run")
async def run_agent(request: AgentRequest, http_request: Request, user_id: int = Depends(auth.get_current_user)):
    owner_id = db.get_chat_owner(request.chat_id)
    if owner_id is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    if owner_id != user_id:
        raise HTTPException(status_code=403, detail="Not your chat")

    db.add_message(request.chat_id, "user", request.message)

    config = {"configurable": {"thread_id": request.chat_id}}
    initial_state = {"user_input": request.message}

    agent = http_request.app.state.agent
    result = agent.invoke(initial_state, config=config)

    interrupts = result.get("__interrupt__")
    if interrupts:
        return {"chat_id": request.chat_id, "interrupt": interrupts[0].value}

    response_text = result.get("response", "")
    db.add_message(request.chat_id, "assistant", response_text)
    return {"chat_id": request.chat_id, "response": response_text}


@app.post("/agent/{chat_id}/approve")
async def approve_agent(chat_id: str, request: ApprovalRequest, http_request: Request,
                        user_id: int = Depends(auth.get_current_user)):
    owner_id = db.get_chat_owner(chat_id)
    if owner_id is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    if owner_id != user_id:
        raise HTTPException(status_code=403, detail="Not your chat")

    config = {"configurable": {"thread_id": chat_id}}

    agent = http_request.app.state.agent
    result = agent.invoke(Command(resume=request.approved), config=config)

    interrupts = result.get("__interrupt__")
    if interrupts:
        return {"chat_id": chat_id, "interrupt": interrupts[0].value}

    response_text = result.get("response", "")
    db.add_message(chat_id, "assistant", response_text)
    return {"chat_id": chat_id, "response": response_text}