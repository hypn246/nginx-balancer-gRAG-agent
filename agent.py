import os
import re
import json
import time
import shutil
import dotenv

from typing import Dict, Any, Optional, Literal

from langchain_core.utils import print_text
from typing_extensions import TypedDict

from langgraph.types import interrupt, Command
from langchain_core.language_models import BaseChatModel
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from grag import GraphRAG, select_llm
from slack_service import send_slack_message

import requests

from config import PROMETHEUS_URL, NGINX_PATH
dotenv.load_dotenv()


def get_metrics(queries, url):
    results = {}
    for name, query in queries.items():
        response = requests.get(url, params={"query": query}, timeout=10)
        response.raise_for_status()
        data = response.json()
        results[name] = data["data"]
    return results


def _text(message) -> str:
    return message.content if hasattr(message, "content") else str(message)


def safe_normalize(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start = text.find("{")
    if start == -1:
        return {}
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
        return obj
    except json.JSONDecodeError:
        return {}


class AgentState(TypedDict):
    next_node: str
    user_input: str

    metrics: Dict[str, Any]
    has_anomalies: bool
    warning_msg: Optional[str]

    recommended_config: Optional[str]
    explanation: Optional[str]
    is_approved: Optional[bool]
    report: Optional[str]
    response: Optional[str]


def fresh_state(user_input: str) -> AgentState:
    return {
        "next_node": "",
        "user_input": user_input,
        "metrics": {},
        "has_anomalies": False,
        "warning_msg": None,
        "recommended_config": None,
        "explanation": None,
        "is_approved": None,
        "report": None,
        "response": None,
    }


ROUTER_PROMPT = """
You are the routing brain of an NGINX infrastructure monitoring agent.
Decide the single best action for the user's message below.

Actions:
- "collect_metrics": user's question starts with "/pro:" or wants a live check of his/her system with server metrics/status from assigned Prometheus URL.
- "grag_chat": user's question starts with "/grag:" or it's an NGINX / load-balancing / infrastructure question and wants used external knowledge base also known as gRAG.
- "chat": general conversation/ question, unrelated to infrastructure, unrelated to Nginx load balancing with metrics, or a question that does not need retrieval.
- "exit": user wants to end the session.

USER MESSAGE:
{user_input}

Respond ONLY with JSON in this exact format:
{{
  "action": "collect_metrics",
  "reason": "one short sentence"
}}
"""


class NginxAgentNodes:
    def __init__(self, llm: BaseChatModel, grag: GraphRAG):
        self.llm = llm
        self.grag = grag

    def invoke_node(self, state: AgentState) -> Dict[str, Any]:
        user_msg = state.get("user_input", "").strip()
        if not user_msg:
            return {"next_node": "direct_response", "response": "Please type a message."}

        raw = self.llm.invoke(ROUTER_PROMPT.format(user_input=user_msg))
        decision = safe_normalize(_text(raw))
        action = str(decision.get("action", "chat")).strip().lower()

        if action == "exit":
            return {"next_node": "exit_agent"}

        if action == "collect_metrics":
            return {"next_node": "collect_metrics"}

        if action == "grag_chat":
            response = self.grag.query(user_msg)
            return {"next_node": "direct_response", "response": response}

        response = self.grag.chit_chat(user_msg)
        return {"next_node": "direct_response", "response": response}

    def collect_node(self, state: AgentState) -> Dict[str, Any]:
        prometheus_url = PROMETHEUS_URL
        if not prometheus_url:
            return {
                "metrics": {},
                "has_anomalies": False,
                "warning_msg": None,
                "response": "PROMETHEUS_URL is not set, cannot collect metrics.",
            }

        queries = {
            "up": 'up{job="node-exporter"}',
            "cpu_percent": '100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)',
            "ram_percent": '100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)',
            "ram_total": "node_memory_MemTotal_bytes",
            "network_in": 'sum by(instance) (rate(node_network_receive_bytes_total{device!="lo"}[5m]))',
            "connections": "node_netstat_Tcp_CurrEstab",
            "http_requests": "sum by(instance) (rate(http_requests_total[5m]))",
        }

        result = get_metrics(queries=queries, url=f"{prometheus_url}/api/v1/query")
        metrics_json = json.dumps(result, ensure_ascii=False)

        prompt = f"""
Analyze this Prometheus data from an NGINX server fleet and decide if there is a performance anomaly.

Rules:
- Any metric above 60% usage is a medium anomaly. Above 80% is a high anomaly.
- If nothing crosses 60% usage, there is no anomaly.

Respond with only a JSON object, no other text. Here is a filled-in example of the exact format
to use when there IS an anomaly:
{{
  "has_anomalies": true,
  "level": "high",
  "warning_msg": "Server 10.0.0.5 CPU usage is at 92%, above the high threshold. Active connections are also elevated at 340.",
  "summary": "Server 10.0.0.5: CPU 92%, RAM 55%, connections 940, <apply this to other stat in metrics...>"
}}

And here is the format when there is NO anomaly:
{{
  "has_anomalies": false,
  "level": "none",
  "warning_msg": "",
  "summary": "Server 10.0.0.5: CPU 35%, RAM 40%, connections 80, <apply this to other stat in metrics...>"
}}

PROMETHEUS DATA:
{metrics_json}
"""

        raw = self.llm.invoke(prompt)
        parsed = safe_normalize(_text(raw))

        has_anomalies = bool(parsed.get("has_anomalies", False))
        warning_msg = parsed.get("warning_msg") if has_anomalies else None
        summary = parsed.get("summary", "")

        return {
            "metrics": result,
            "has_anomalies": has_anomalies,
            "warning_msg": warning_msg,
            "response": summary or "Metrics collected, no anomalies detected.",
        }

    def warning_node(self, state: AgentState) -> Dict[str, Any]:
        print("Warning detected")
        warning_msg = state.get("warning_msg") or "Anomaly detected in server metrics."
        formatted = f":rotating_light: *Infrastructure Warning*\n{warning_msg}"
        send_slack_message(formatted)
        return {"warning_msg": formatted}

    def suggest_node(self, state: AgentState) -> Dict[str, Any]:
        print("Using gRAG to give a solution")
        metrics = state.get("metrics", {})
        raw = self.grag.query(json.dumps(metrics, ensure_ascii=False))
        parsed = safe_normalize(raw)

        analysis = parsed.get("analysis", raw)
        recommended_method = parsed.get("recommended_method", "")
        explanation = parsed.get("explanation", "")
        nginx_configuration = parsed.get("nginx_configuration", "")

        return {
            "response": f"{analysis}\n{recommended_method}".strip(),
            "recommended_config": nginx_configuration,
            "explanation": explanation,
        }

    def approve_conf_node(self, state: AgentState) -> Dict[str, Any]:
        decision = interrupt(
            {
                "type": "approval_required",
                "question": "Apply this NGINX configuration?",
                "recommended_config": state.get("recommended_config"),
                "explanation": state.get("explanation"),
            }
        )
        approved = str(decision).strip().lower() in ("y", "yes", "true", "agree")
        return {"is_approved": approved}

    def report_node(self, state: AgentState) -> Dict[str, Any]:
        nginx_conf = (state.get("recommended_config", "") or "")
        upstream_text = nginx_conf.strip()
        conf_path = NGINX_PATH

        match = re.match(r"^upstream\s+(\S+)\s*\{", upstream_text.strip())
        if not match:
            raise ValueError("recommended_config must start with 'upstream <name> {'")
        name = match.group(1)

        if not conf_path:
            report_text = ":warning: NGINX_PATH is not set, config was not written."
            send_slack_message(report_text)
            return {"report": report_text}

        try:
            content = ""
            if os.path.exists(conf_path):
                shutil.copy2(conf_path, f"{conf_path}.bak.{int(time.time())}")
                with open(conf_path, "r", encoding="utf-8") as f:
                    content = f.read()
            http = re.search(r"\bhttp\s*\{", content)
            if not http:
                raise ValueError("NGINX config has no http block")

            start = http.end()
            depth, end = 1, None

            for i in range(start, len(content)):
                if content[i] == "{":
                    depth += 1
                elif content[i] == "}":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            if end is None:
                raise ValueError("Invalid http block")
            http_body = content[start:end]
            pattern = re.compile(r"(?ms)^[ \t]*upstream\s+" + re.escape(name) + r"\s*\{.*?^[ \t]*\}")
            if pattern.search(http_body):
                http_body = pattern.sub(upstream_text, http_body, count=1)
            else:
                http_body = http_body.rstrip() + "\n\n" + upstream_text + "\n"

            new_conf = content[:start] + http_body + content[end:]
            with open(conf_path, "w", encoding="utf-8") as f:
                f.write(new_conf)
            report_text = (
                f":white_check_mark: *NGINX config applied* to `{conf_path}`\n"
                f"""```nginx
                {nginx_conf}
                ```"""
            )
        except (OSError, ValueError) as e:
            report_text = f":x: Failed to write NGINX config: {e}"
        send_slack_message(report_text)
        return {"report": report_text}

    def response_node(self, state: AgentState) -> Dict[str, Any]:
        parts = []
        if state.get("warning_msg"):
            parts.append(state["warning_msg"])
        if state.get("response"):
            parts.append(state["response"])
        if state.get("recommended_config"):
            parts.append(f"Recommended NGINX config:\n{state['recommended_config']}")
        if state.get("explanation"):
            parts.append(f"Why:\n{state['explanation']}")
        if state.get("report"):
            parts.append(state["report"])
        if not parts:
            parts.append("No actions were required.")

        state["metrics"]=None
        state["has_anomalies"]= False
        state["warning_msg"]= None
        state["recommended_config"]= None
        state["explanation"]= None
        state["is_approved"]= None
        state["report"]= None
        return {"response": "\n\n".join(parts)}


def decide_invoke_tools(state: AgentState) -> Literal["collect_metrics", "direct_response", "exit_agent"]:
    return state.get("next_node", "collect_metrics")


def decide_collect_route(state: AgentState) -> Literal["anomaly", "ok"]:
    return "anomaly" if state.get("has_anomalies") else "ok"

def decide_grag_route(self, state: AgentState) -> Literal["YES", "NO"]:
    return "NO" if state.get("has_grags") else "YES"

def decide_approve_route(state: AgentState) -> Literal["YES", "NO"]:
    return "YES" if state.get("is_approved") else "NO"


def create_agent_graph(llm: BaseChatModel, grag: GraphRAG, checkpointer=None):
    nodes = NginxAgentNodes(llm=llm, grag=grag)

    workflow = StateGraph(AgentState)
    workflow.add_node("Invoke", nodes.invoke_node)
    workflow.add_node("Collect", nodes.collect_node)
    workflow.add_node("Warning", nodes.warning_node)
    workflow.add_node("Suggest", nodes.suggest_node)
    workflow.add_node("Approve", nodes.approve_conf_node)
    workflow.add_node("Report", nodes.report_node)
    workflow.add_node("Responding", nodes.response_node)

    workflow.set_entry_point("Invoke")
    workflow.add_conditional_edges(
        "Invoke",
        decide_invoke_tools,
        {
            "collect_metrics": "Collect",
            "direct_response": "Responding",
            "exit_agent": END,
        },
    )
    workflow.add_conditional_edges(
        "Collect",
        decide_collect_route,
        {
            "anomaly": "Warning",
            "ok": "Responding",
        },
    )
    workflow.add_edge("Warning", "Suggest")
    workflow.add_edge("Suggest", "Approve")
    workflow.add_conditional_edges(
        "Approve",
        decide_approve_route,
        {
            "YES": "Report",
            "NO": "Responding",
        },
    )
    workflow.add_edge("Report", "Responding")
    workflow.add_edge("Responding", END)

    checkpointer = checkpointer or MemorySaver()
    return workflow.compile(checkpointer=checkpointer)


def grag_agent(llm, grag, checkpointer=None):
    return create_agent_graph(llm=llm, grag=grag, checkpointer=checkpointer)


if __name__ == "__main__":
    shared_llm = select_llm(os.getenv("LLM_CHAT"))
    graph_rag_instance = GraphRAG(llm=shared_llm)
    agent_app = grag_agent(llm=shared_llm, grag=graph_rag_instance)
    #placeholder for pgsql
    thread_config = {"configurable": {"thread_id": "cli-demo"}}
    print("NGINX monitoring agent demo. Type 'exit' to quit.\n")

    try:

        while True:
            user_input = input("You: ")
            if not user_input:
                continue
            result = agent_app.invoke(fresh_state(user_input), config=thread_config)

            if "__interrupt__" in result:
                payload = result["__interrupt__"][0].value
                print(f"\n[Approval needed] {payload.get('question')}")
                print(f"Proposed NGINX config:\n{payload.get('recommended_config')}\n")
                print(f"Why: {payload.get('explanation')}\n")
                decision = input("Approve? (y/n): ").strip()
                result = agent_app.invoke(Command(resume=decision), config=thread_config)

            if result.get("next_node") == "exit_agent":
                print("\nAgent: Goodbye!\n")
                break

            print(f"\nAgent: {result.get('response')}\n")
    finally:
        graph_rag_instance.close()