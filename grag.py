import json
import os
import re
import time
from typing import Any, Optional, List
from dotenv import load_dotenv
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.messages.ai import AIMessage
from neo4j import GraphDatabase
from langchain.rate_limiters import InMemoryRateLimiter

rate_limiter = InMemoryRateLimiter(
    requests_per_second=0.15,  
    check_every_n_seconds=0.15,
    max_bucket_size=1, 
)

from config import BATCH_SIZE, MAX_CONCURRENCY
load_dotenv()

class Base:
    def __init__(self, driver=None):
        self._owns_driver = driver is None
        self.driver = driver or self.create_driver()

    @staticmethod
    def create_driver():
        uri = os.getenv("NEO4J_URI")
        username = os.getenv("NEO4J_USERNAME")
        password = os.getenv("NEO4J_PASSWORD")

        if not uri or not username or not password:
            raise ValueError(
                "NEO4J_URI, NEO4J_USERNAME and NEO4J_PASSWORD must be set."
            )

        return GraphDatabase.driver(uri, auth=(username, password))

    def close(self):
        if self._owns_driver and self.driver is not None:
            self.driver.close()
            self.driver = None

def select_llm(provider, model=None):
    provider = (provider or "").strip()
    md=""
    if provider.lower() == "ollama":
        try:
            if not model:
                model = os.getenv("OLLAMA")
            from langchain_ollama import ChatOllama
            return ChatOllama(model=model)
        except:
            raise ValueError("OLLAMA environment variable is not set.")

    if provider.lower() == "gemini":
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is not set.")

        from langchain_google_genai import ChatGoogleGenerativeAI
        md=model if model else os.getenv("GEMINI_MODEL")
        print(f"Selected {provider} /w model: {md}")
        return ChatGoogleGenerativeAI(
            model=md,
            api_key=api_key,
            rate_limiter=rate_limiter
        )
        
    if provider.lower() == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set.")
        from langchain_openai import ChatOpenAI
        md=model if model else os.getenv("OPENAI_MODEL")
        print(f"Selected {provider} /w model: {md}")
        return ChatOpenAI(
            # model=os.getenv("GPT_MODEL", "gpt-4o-mini-2024-07-18"),
            model=md,
            api_key=api_key,
        )

    raise ValueError(f"Unknown LLM provider: {provider}")

def _content_to_text(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "content"):
        content = value.content
        if isinstance(content, list):
            return "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        value = content
    return str(value)

def _parse_map_json(text: str, default: dict) -> dict:
    """JSON parsing MAP-stage LLM output"""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        parsed, _ = json.JSONDecoder().raw_decode(text)
        return parsed
    except json.JSONDecodeError:
        print(f"CAUSION: could not parse JSON, using default. Raw text: {text[:200]}")
        return default

def _coerce_score(value: Any, default: int = 0) -> int:
    """ relevant_score to int. LLM sometimes returns string like '90'"""
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        match = re.search(r"-?\d+", value)
        if match:
            return int(match.group())
    return default

class GraphRAG(Base):
    PROMPT_TEMPLATE = PromptTemplate.from_template(
        """
You are an expert DevOps and NGINX load-balancing assistant.

Use:
- CURRENT SERVER METRICS / QUESTION as the source of truth for the current state.
- RETRIEVED GRAPHRAG KNOWLEDGE as supporting inferencing to analysis stradegy for Nginx.
If graph evidence is insufficient, explicitly state that limitation in the analysis.

CURRENT SERVER METRICS / QUESTION:
{question}

RETRIEVED GRAPHRAG KNOWLEDGE:
{context}

TASK:
- Analyze the observed server status base on their own metrics and identify the load-balancing problem.
- Recommend exactly one NGINX load-balancing method.
- Explain why it fits the observed conditions based on retrieved evidence and metrics status
- Generate a syntactically valid NGINX upstream configuration base on the load-balancing suggested above and using host/IP values from the question.

Expected output:
{{
  "analysis": "string",
  "recommended_method": "string",
  "explanation": "string",
  "nginx_configuration": "string"
}}

nginx_configuration must contain ONLY plain NGINX configuration text.
"""
    )

    def __init__(self, llm, driver=None):
        super().__init__(driver=driver)
        self.llm=llm
        self.map_prompt = PromptTemplate.from_template(
            """
You are the mapping stage of a GraphRAG retrieval pipeline for NGINX load balancing.

Do NOT answer the user's question.
Combine all information of summaries from the COMMUNITY RETRIEVED. And give score base on how it is useful for deciding the NGINX load-balancing strategy for the CURRENT QUERY.

CURRENT QUERY:
{question}

COMMUNITY RETRIEVED:
{summaries}

RULES:
- Remove duplicates and vague repetition summaries.
- Score must be a integer value between 0 to 100.
- Return 0 and an empty string "" when nothing in the batch is useful.
- Do not invent facts. Prefer a small number of specific insight.
- Remove all conversational preamble, special symbol, markdown headers, notes and intro style "This ... talk about ..." at the beginning of the resul
OUTPUT:
Expected JSON output, following this example exactly (relevant_score is a plain number, never in quotes):
{{
  "relevant_score": 85,
  "batch_summary": "Example: the retrieved communities cover NGINX upstream directives and health check tuning relevant to the current server metrics."
}}

"""
        )
        self.map_chain = self.map_prompt | self.llm | StrOutputParser()
        self.reduce_prompt = PromptTemplate.from_template(
            """
You are the REDUCE stage of a GraphRAG retrieval pipeline for NGINX load balancing.

Summaries content in all the MAP SUMMARIES

MAP SUMMARIES:
{map}

RULES:
- Use ONLY content in the MAP SUMMARIES
- Do not invent server values, IPs, ports, configuration values, or NGINX behavior.
- Remove all conversational preamble, special symbol, markdown headers and symbol, notes and intro style "This ... talk about ..." at the beginning of the resul to fit python dict
- Make sure the context not too short, that it should self-contained enough for the final model to reason about the recommendation.

OUTPUT:
Return only text. 
No Markdown fences.
Do NOT include any introductory sentences, conversational preamble, markdown headers, or notes.
"""
        )
        self.reduce_chain = self.reduce_prompt | self.llm | StrOutputParser()
        self.final_chain = self.PROMPT_TEMPLATE | self.llm | StrOutputParser()

    def _debug_print(self, stage: str, batch_no: int, raw: Any, normalized: Any = None):
        print(f"\n{'=' * 18} {stage} DEBUG | batch={batch_no} {'=' * 18}")
        print("--- RAW LLM OUTPUT ---")
        print(type(raw))
        print(_content_to_text(raw))
        if normalized:
            print("+++ NORM OUPUT +++")
            print(type(normalized))
            print(normalized)

    def load_community_summaries(self) -> list[dict]:
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (c:__Community__)
                RETURN c.id AS id,
                       c.title AS title,
                       c.summary AS summary
                """
            )
            reports = []
            for record in result:
                reports.append({
                    "id": record["id"],
                    "title": record["title"],
                    "summary": record["summary"],
                })
            return reports

    def query(self, question: str, batch_size: int = 5, top_k: int = 5) -> str:
        if(BATCH_SIZE):
            batch_size=BATCH_SIZE
        print("\n--- 1. Fetching Community Reports ---")
        reports = self.load_community_summaries()

        if not reports:
            print("No community reports found in Neo4j. Run --build first.")
            return json.dumps({
                "analysis": "No community knowledge base found.",
                "recommended_method": "",
                "explanation": "",
                "nginx_configuration": "",
            }, indent=4, ensure_ascii=False)

        print(f"Loaded {len(reports)} community reports. Batching...")
        
        # Slices repors into batch_size
        report_batches = [
            reports[i : i + batch_size]
            for i in range(0, len(reports), batch_size)
        ]

        print(f"--- 2. Executing map Stage over {len(report_batches)} batches ---")
        t = time.time()
        map_inputs = [
            {
                "question": question,
                "summaries": json.dumps(batch, ensure_ascii=False),
            }
            for batch in report_batches
        ]
        try:
            raw_results = self.map_chain.batch(
                map_inputs,
                config={"max_concurrency": MAX_CONCURRENCY},
            )
        except Exception as e:
            print(f"Map batch execution failed: {e}")
            raw_results = []
            
        all_summaries = []

        for idx, raw in enumerate(raw_results, start=1):
            text = _content_to_text(raw)
            parsed = _parse_map_json(text, default={"relevant_score": 0, "batch_summary": text})
            parsed["relevant_score"] = _coerce_score(parsed.get("relevant_score", 0))
            # self._debug_print("MAP", idx, raw, parsed)
            all_summaries.append(parsed)

        print(
            f"Map complete: {len(all_summaries)} batch_summaries "
            f"from {len(raw_results)} batches."
        )
        t2 = round(time.time() - t, 1)

        print(f"--- 3. Ranking batch_summaries by relevant_score; selecting Top-{top_k} ---")
        all_summaries.sort(
            key=lambda item: item.get("relevant_score", 0),
            reverse=True,
        )
        top_summaries = all_summaries[:max(1, top_k)]
        #print(f"Result from top_k: {top_summaries}")

        print("--- 4. Executing REDUCE Stage ---")
        if top_summaries:
            raw_reduce = self.reduce_chain.invoke({
                "map": json.dumps(top_summaries, ensure_ascii=False),
            })
            # jic norm didn't work here
            parsed_reduced = _content_to_text(raw_reduce).strip()
            # self._debug_print("REDUCE", 1, raw_reduce, parsed_reduced)
        else:
            parsed_reduced = "No extra context added"
        #print(f"Right now, CONTEXT will be: {parsed_reduced}")

        print("--- 5. Generating Final GraphRAG Response ---")
        final_raw = self.final_chain.invoke({
            "question": question,
            "context": parsed_reduced,
        })
        
        # final_chain ends = StrOutputParser => final_raw is plain text.
        print(f"Total map time: {t2}s")
        fin = _content_to_text(final_raw)
        #print(fin)
        return fin

    def chit_chat(self, ques):
        return self.llm.invoke(ques).content
    
import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GraphRAG CLI")
    parser.add_argument("--grag", action="store_true", help="Chat using GraphRAG")
    parser.add_argument("--chat", action="store_true", help="Chat using GraphRAG")

    args = parser.parse_args()
    try:
        if args.grag:
            grag = GraphRAG(llm=select_llm(os.getenv("LLM_RETRIEVER")))
            q = input("Type your question (gRAG): ")
            grag.query(q)
        if args.chat:
            grag = GraphRAG(llm=select_llm(os.getenv("LLM_RETRIEVER")))
            q = input("Type your question: ")
            grag.chit_chats(q)
        else:
            parser.print_help()
    finally:
        grag.close()