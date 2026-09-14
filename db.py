import os
import uuid
import dotenv
import psycopg

dotenv.load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chats (
    id UUID PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    chat_id UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);
"""


def init_schema():
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute(SCHEMA)


def create_user(username: str, password_hash: str) -> int:
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        row = conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (%s, %s) RETURNING id",
            (username, password_hash),
        ).fetchone()
        return row[0]


def get_user_by_username(username: str):
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        row = conn.execute(
            "SELECT id, username, password_hash FROM users WHERE username = %s",
            (username,),
        ).fetchone()
        if not row:
            return None
        return {"id": row[0], "username": row[1], "password_hash": row[2]}


def create_chat(user_id: int, title: str = "New Chat") -> str:
    chat_id = str(uuid.uuid4())
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO chats (id, user_id, title) VALUES (%s, %s, %s)",
            (chat_id, user_id, title),
        )
    return chat_id


def get_chats_for_user(user_id: int):
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        rows = conn.execute(
            "SELECT id, title, created_at FROM chats WHERE user_id = %s ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        return [{"id": str(r[0]), "title": r[1], "created_at": r[2]} for r in rows]


def delete_chat(chat_id: str):
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute("DELETE FROM chats WHERE id = %s", (chat_id,))


def get_chat_owner(chat_id: str):
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        row = conn.execute(
            "SELECT user_id FROM chats WHERE id = %s", (chat_id,)
        ).fetchone()
        return row[0] if row else None


def add_message(chat_id: str, role: str, content: str):
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO messages (chat_id, role, content) VALUES (%s, %s, %s)",
            (chat_id, role, content),
        )


def get_messages_for_chat(chat_id: str):
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        rows = conn.execute(
            "SELECT role, content, created_at FROM messages WHERE chat_id = %s ORDER BY created_at ASC",
            (chat_id,),
        ).fetchall()
        return [{"role": r[0], "content": r[1], "created_at": r[2]} for r in rows]