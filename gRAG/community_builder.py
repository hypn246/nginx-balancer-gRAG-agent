import json
import os
import re
import time
from typing import Any, Optional, List
from dotenv import load_dotenv
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_core.prompts import PromptTemplate
from neo4j import GraphDatabase
from langchain.rate_limiters import InMemoryRateLimiter

rate_limiter = InMemoryRateLimiter(
    requests_per_second=0.15,  
    check_every_n_seconds=0.15,
    max_bucket_size=1, 
)

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
    """Turn any LLM chain output into a plain str, no matter what class it actually is."""
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
    """ JSON parsing for MAP-stage """
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

class CommunityBuilder(Base):
    def __init__(self, llm, driver=None):
        super().__init__(driver=driver)
        self.llm = llm

    def project_graph(self, graph_name="graphrag_communities"):
        with self.driver.session() as session:
            session.run(
                "MATCH (n:__Entity__) REMOVE n.community, n.community_hierarchy"
            ).consume()

            exists = session.run(
                "CALL gds.graph.exists($graph_name) YIELD exists RETURN exists",
                graph_name=graph_name,
            ).single()["exists"]

            if exists:
                session.run(
                    """CALL gds.graph.drop($graph_name, false)
                        YIELD graphName""",
                    graph_name=graph_name,
                )

            session.run(
                """
                CALL gds.graph.project(
                    $graph_name,
                    '__Entity__',
                    {
                        _ALL_: {
                            type: '*',
                            orientation: 'UNDIRECTED'
                        }
                    }
                )
                """,
                graph_name=graph_name,
            )

    def run_leiden(
        self,
        graph_name="graphrag_communities",
        include_intermediate_communities=True,
        random_seed=42,
        max_levels=10,
    ):
        property_name = (
            "community_hierarchy"
            if include_intermediate_communities
            else "community"
        )

        config = {
            "writeProperty": property_name,
            "includeIntermediateCommunities": include_intermediate_communities,
            "randomSeed": random_seed,
            "maxLevels": max_levels,
        }

        print("Running Leiden...")
        with self.driver.session() as session:
            session.run(
                "CALL gds.leiden.write($graph_name, $config)",
                graph_name=graph_name,
                config=config,
            ).consume()

            session.run(
                """CALL gds.graph.drop($graph_name, false)
                    YIELD graphName""",
                graph_name=graph_name,
            ).consume()

        return property_name

    def build(
        self,
        graph_name="graphrag_communities",
        include_intermediate_communities=True,
        random_seed=42,
        max_levels=10,
    ):
        self.project_graph(graph_name)
        property_name = self.run_leiden(
            graph_name=graph_name,
            include_intermediate_communities=include_intermediate_communities,
            random_seed=random_seed,
            max_levels=max_levels,
        )
        print(f"Community detection complete. Property written: {property_name}")
        return property_name

class CommunitySummarizer(Base):
    def __init__(self, llm, driver=None):
        super().__init__(driver=driver)
        self.llm = llm
        self.summary_prompt = PromptTemplate.from_template(
            """
You are generating a community summary for an NGINX load-balancing knowledge graph.

COMMUNITY CONTENT:
{community_data}

TASK:
- Focus analyzing more about the knowledge and relationship between those elements in side the COMMUNITY CONTENT. And talk more about how elements inside interact and effect to each other, where and how the parameters placed and analyse relationship as detail as possiable.
The analyse must at least 3-5 sentences

Remove all conversational preamble, special symbol, markdown headers, notes and intro style "This ... talk about ..." at the beginning of the result.
Respond with JSON  matching the exact structure below. 
Output expected:
{{
    "title": "<Short title for the community>",
    "summary": "<A summary of the community.>"
}}
            """
        )
        self.summary_chain = self.summary_prompt | self.llm | StrOutputParser()

    @staticmethod
    def _community_key(level: int, community_id: Any) -> str:
        return f"{level}:{community_id}"

    def get_communities(self, min_size=2):
        print("Getting communities...")
        with self.driver.session() as session:
            rows = session.run(
                """
                MATCH (n:__Entity__)
                WHERE n.community_hierarchy IS NOT NULL
                RETURN n.id AS entity_id,
                    n.community_hierarchy AS hierarchy
                """
            )

            communities: dict[tuple[int, Any], list[str]] = {}
            for row in rows:
                entity_id = row["entity_id"]
                hierarchy = row["hierarchy"] or []

                for level, community_id in enumerate(hierarchy):
                    communities.setdefault((level, community_id), []).append(entity_id)

        return {
            key: sorted(set(members))
            for key, members in communities.items()
            if len(set(members)) >= min_size
        }

    def get_community_data(self, members):
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (e:__Entity__)
                WHERE e.id IN $members
                MATCH (e)--(d)
                WHERE d.text IS NOT NULL
                RETURN DISTINCT d.text AS text
                """,
                members=members,
            )

            return "\n\n".join(
                record["text"]
                for record in result
            )
            
    def summarize_community(self, level, community_id, members, max_retries=3):
        print(f"Summarizing Community {community_id}: level={level}, members={len(members)}")
        data = self.get_community_data(members)
        print(f"This is raw com data: \n{data}")

        for attempt in range(1, max_retries + 1):
            try:
                result = self.summary_chain.invoke({
                    "community_data": data,
                })
                print(f"This is the result: \n{result}")
                text = _content_to_text(result)
                parsed = _parse_map_json(
                    text,
                    default={"title": f"Community {community_id}", "summary": ""},
                )
                if parsed.get("summary"):
                    return {
                        "title": str(
                            parsed.get("title", f"Community {community_id}")
                        ),
                        "summary": str(parsed.get("summary", "")),
                    }
                print(f"Success summarize for community {community_id}:\n {parsed}")
            except Exception as e:
                print(f"Attempt {attempt}/{max_retries} failed for community {community_id}: {e}")
                if attempt < max_retries:
                    time.sleep(1)
                print(f"All retries failed for community {community_id}. Applying fallback default.")
                return {
                    "title": f"Community {community_id}",
                    "summary": "",
                }
        return {
            "title": "",
            "summary": "",
        }

    def clear_old_reports(self):
        print("Clearing old reports...")
        with self.driver.session() as session:
            session.run("MATCH (c:__Community__) DETACH DELETE c").consume()

    def save_summaries(self, reports, hierarchy_property="community_hierarchy"):
        print("Saving summary")
        with self.driver.session() as session:
            for (level, community_id), item in reports.items():
                report = item.get("report") or {}  # Ensures report is always a dict
                parent_key = item.get("parent_key")

                session.run(
                    """
                    MERGE (c:__Community__ {id: $id})
                    SET c.community_id = $community_id,
                        c.level = $level,
                        c.title = $title,
                        c.summary = $summary,
                        c.hierarchy_property = $hierarchy_property
                    WITH c
                    OPTIONAL MATCH (e:__Entity__)
                    WHERE e.id IN $members
                    WITH c, collect(e) AS entities
                    FOREACH (entity IN entities |
                        MERGE (c)-[:HAS_MEMBER]->(entity)
                    )
                    """,
                    id=self._community_key(level, community_id),
                    community_id=community_id,
                    level=level,
                    title=report.get("title", f"Community {community_id}"),
                    summary=report.get("summary", ""),
                    hierarchy_property=hierarchy_property,
                    members=item["members"],
                )

                if parent_key is not None:
                    session.run(
                        """
                        MATCH (child:__Community__ {id: $child_id})
                        MATCH (parent:__Community__ {id: $parent_id})
                        MERGE (parent)-[:PARENT_OF]->(child)
                        """,
                        child_id=self._community_key(level, community_id),
                        parent_id=self._community_key(
                            parent_key[0], parent_key[1]
                        ),
                    ).consume()

    def build_summaries(
        self,
        min_size=2,
        max_communities=None,
        clear_existing=True,
        hierarchy_property="community_hierarchy",
    ):
        communities = self.get_communities(min_size=min_size)

        ordered = sorted(
            communities.items(),
            key=lambda item: (item[0][0], len(item[1]), str(item[0][1])),
        )

        if max_communities is not None:
            ordered = ordered[:max_communities]

        if clear_existing:
            self.clear_old_reports()

        reports = {}
        for (level, community_id), members in ordered:
            report = self.summarize_community(level, community_id, members)
            parent_key = None
            if level > 0:
                with self.driver.session() as session:
                    parent_row = session.run(
                        """
                        MATCH (n:__Entity__)
                        WHERE n.id = $member
                        RETURN n.community_hierarchy AS hierarchy
                        LIMIT 1
                        """,
                        member=members[0],
                    ).single()

                hierarchy = parent_row["hierarchy"] if parent_row else []
                if len(hierarchy) > level:
                    parent_key = (level - 1, hierarchy[level - 1])
            print(f"[DEBUG] Summarized Community {community_id}:")
            print(f"  Title: {report.get("title", "")}")
            print(f"  Summary: {report.get("summary", "")[:150]}...")
            reports[(level, community_id)] = {
                "report": report,
                "members": members,
                "parent_key": parent_key,
            }

        self.save_summaries(reports, hierarchy_property=hierarchy_property)
        print(f"Successfully summarized {len(reports)} communities.")
        return reports


def build_communities(
    llm,
    driver=None,
    include_intermediate_communities=True,
    random_seed=42,
    max_levels=10,
    min_size=2,
    max_communities=None,
    clear_existing=True,
):
    builder = CommunityBuilder(llm, driver=driver)
    try:
        hierarchy_property = builder.build(
            include_intermediate_communities=include_intermediate_communities,
            random_seed=random_seed,
            max_levels=max_levels,
        )
    finally:
        builder.close()

    summarizer = CommunitySummarizer(llm, driver=driver)
    try:
        return summarizer.build_summaries(
            min_size=min_size,
            max_communities=max_communities,
            clear_existing=clear_existing,
            hierarchy_property=hierarchy_property,
        )
    finally:
        summarizer.close()

import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GraphRAG CLI")
    parser.add_argument("--build", action="store_true", help="Build communities")

    args = parser.parse_args()
    if args.build:
        build_communities(llm=select_llm(os.getenv("LLM_EXT")))
    else:
        parser.print_help()