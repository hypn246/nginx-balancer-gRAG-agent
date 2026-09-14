import os
import dotenv
from langgraph.checkpoint.postgres import PostgresSaver
import db

dotenv.load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

def main():
    db.init_schema()
    print("App tables ready (users, chats, messages).")
    with PostgresSaver.from_conn_string(DATABASE_URL) as checkpointer:
        checkpointer.setup()
    print("LangGraph checkpoint tables ready.")

if __name__ == "__main__":
    main()
