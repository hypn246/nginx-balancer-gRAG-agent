import json
import os
import traceback
import pandas as pd
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
import time
from typing import Any
from .grag import GraphRAG, select_llm, _content_to_text, _parse_map_json
from config import MAX_CONCURRENCY
from langchain.rate_limiters import InMemoryRateLimiter
from dotenv import load_dotenv

# Configuration
n_case=100
path="data/examples"

CHECKPOINT = 1
base_output_dir = "./test11/test_result_ggg"
time_file = "test11/time_ggg"
time_error_file = "test11/time_error_ggg"

# Define directory structure
retriever_out_dir = os.path.join(base_output_dir, "retriever_outputs")
generation_out_dir = os.path.join(base_output_dir, "generation_outputs")
retriever_eval_dir = os.path.join(base_output_dir, "retriever_evals")
generation_eval_dir = os.path.join(base_output_dir, "generation_evals")
failed_cases_dir = os.path.join(base_output_dir, "failed_cases")

for d in [retriever_out_dir, generation_out_dir, retriever_eval_dir, generation_eval_dir, failed_cases_dir]:
    os.makedirs(d, exist_ok=True)

RETRIEVER_EVAL_PROMPT = PromptTemplate.from_template(
    """
    You are an evaluator assessing the retrieval quality of a GraphRAG system for server metrics.
    
    SERVER METRICS:
    {question}
    
    RETRIEVED CONTEXT:
    {context}
    
    Task: Evaluate the relevance and usefulness of the RETRIEVED CONTEXT to the SERVER METRICS with a score is an interger from 0-100. Criterial to judge is: How the RETRIEVED CONTEXT help to solve the problem in the SERVER METRICS.
    Return a JSON with:
    {{
        "retrieval_relevance_score": 50,
        "relevance_explanation": "The ...",
        "sufficient_evidence": false
    }}
    """
)

GENERATION_EVAL_PROMPT = PromptTemplate.from_template(
    """
    You are an evaluator assessing the generated NGINX configuration and analysis.
    
    SERVER METRICS:
    {question}
    
    RETRIEVED CONTEXT:
    {context}
    
    GENERATED RESPONSE:
    {generation}
    
    Task: Evaluate the accuracy with score is an integer between 0-100, NGINX configuration validity, and reasoning. All these criteria base on: How well the GENERATED RESPONSE solve the SERVER METRICS problem.
    Criteria and score /100:
    +       10: Analyze
    +       30: Explain for lba
    +       20: LBA
    +       40: Nginx config (upstream block)        
    Give an integer score from 0-100.
    Return a JSON with:
    {{
        "generation_score": 85 ,
        "config_validity": true,
        "reasoning_explanation": "The context provides..."
    }}
    """
)

def create_sample(csv_path):
    df = pd.read_csv(csv_path)
    df["latency"] = df["latency"].apply(lambda x: f"{x}ms")
    df = df.rename(columns={"network_traffic": "network_connection"})

    df = df[
        ["ip", "cpu_usage", "memory_usage", "network_connection", "execution_time", "latency"]
    ]

    return df.to_dict(orient="records")

def run_retriever_stage(grag: GraphRAG, question: str, batch_size: int = 5, top_k: int = 5):
    reports = grag.load_community_summaries()
    if not reports:
        return {
            "map_stage": [],
            "reduced_stage": "No community reports found in Neo4j.",
        }
    report_batches = [
        reports[i : i + batch_size]
        for i in range(0, len(reports), batch_size)
    ]
    map_inputs = [
        {
            "question": question,
            "summaries": json.dumps(batch, ensure_ascii=False),
        }
        for batch in report_batches
    ]
    try:
        raw_results = grag.map_chain.batch(
            map_inputs,
            config={"max_concurrency": MAX_CONCURRENCY},
        )
    except Exception as e:
        print(f"Map batch execution failed: {e}")
        raw_results = []

    all_summaries = []
    print("handle parsed map")
    for idx, raw in enumerate(raw_results, start=1):
        text = _content_to_text(raw)
        parsed = _parse_map_json(text, default={"relevant_score": 0, "batch_summary": text})
        grag._debug_print("MAP", idx, raw, parsed)
        all_summaries.append(parsed)

    all_summaries.sort(
        key=lambda item: item.get("relevant_score", 0),
        reverse=True,
    )
    top_summaries = all_summaries[: max(1, top_k)]
    print(f"Result from top_k: {top_summaries}")

    print("REDUCE Stage")
    raw_reduce = None
    if top_summaries:
        try:
            raw_reduce = grag.reduce_chain.invoke({
                "map": json.dumps(top_summaries, ensure_ascii=False),
            })
            parsed_reduced = _content_to_text(raw_reduce).strip()

        except Exception as e:
            print(f"[REDUCE ERROR] {e}")
            parsed_reduced = "Reduce stage failed."
    else:
        parsed_reduced = "No extra context added"

    if raw_reduce is not None:
        grag._debug_print("REDUCE", 1, raw_reduce, parsed_reduced)
    return {
        "map_stage": all_summaries,
        "reduced_stage": parsed_reduced,
    }

    

def evaluate_retriever_and_generation(llm:Any, grag: GraphRAG, input_data: list, case_id: int):
    question_str = str(json.dumps(input_data, ensure_ascii=False, indent=2))
    # --- 1. RETRIEVER ---
    retriever_output = run_retriever_stage(grag, question_str)
    retriever_file = os.path.join(retriever_out_dir, f"case_{case_id}.json")
    with open(retriever_file, "w", encoding="utf-8") as f:
        json.dump(retriever_output, f, ensure_ascii=False, indent=2)

    reduced_context = retriever_output.get("reduced_stage", "")
    retriever_context_str = json.dumps(retriever_output, ensure_ascii=False)

    # --- 2. EVALUATE: RETRIEVER ---
    retriever_eval_chain = RETRIEVER_EVAL_PROMPT | (llm if llm else grag.llm)
    retriever_eval_raw = retriever_eval_chain.invoke({
        "question": question_str,
        "context": retriever_context_str
    })
    
    retriever_eval_res =  _content_to_text(retriever_eval_raw)
    
    retriever_eval_file = os.path.join(retriever_eval_dir, f"case_{case_id}.json")
    with open(retriever_eval_file, "w", encoding="utf-8") as f:
        json.dump(retriever_eval_res, f, ensure_ascii=False, indent=2)

    # --- 3. GENERATION ---
    final_raw = grag.final_chain.invoke({
        "question": question_str,
        "context": reduced_context
    })
    generation_parsed = _content_to_text(final_raw)
      
    generation_file = os.path.join(generation_out_dir, f"case_{case_id}.json")
    with open(generation_file, "w", encoding="utf-8") as f:
        json.dump(generation_parsed, f, ensure_ascii=False, indent=2)

    # --- 4. EVALUATE: GENERATION ---
    generation_eval_chain = GENERATION_EVAL_PROMPT | (llm if llm else grag.llm)
    generation_eval_raw = generation_eval_chain.invoke({
        "question": question_str,
        "context": reduced_context,
        "generation": json.dumps(generation_parsed, ensure_ascii=False)
    })
    
    generation_eval_res =  _content_to_text(generation_eval_raw)

    generation_eval_file = os.path.join(generation_eval_dir, f"case_{case_id}.json")
    with open(generation_eval_file, "w", encoding="utf-8") as f:
        json.dump(generation_eval_res, f, ensure_ascii=False, indent=2)

    return {
        "retriever_eval": retriever_eval_res,
        "generation_eval": generation_eval_res
    }

def eval_with_csv(llm: Any, grag: GraphRAG):
    checkpoint = CHECKPOINT
    print(f"start at: {checkpoint}")
    for i in range(checkpoint, n_case + 1):
        t = time.time()
        csv_file = f"{path}/case_{i}.csv"
        
        if not os.path.exists(csv_file):
            print(f"File {csv_file} not found. Skipping...")
            continue

        input_data = create_sample(csv_path=csv_file)
        
        try:
            res = evaluate_retriever_and_generation(llm, grag, input_data, case_id=i)
            print(f"Finished case_{i}:")
            print(json.dumps(res, ensure_ascii=False, indent=2))
            with open(f"./{time_file}.txt", "a") as file:
                file.write(f"Time for test case {i}: {round(time.time()-t, 1)}s\n")

        except Exception as initial_error:
            print(f"[WARNING] Case {i} failed: ({initial_error}).")
            success = False
            if not success:
                error_payload = {
                    "case_id": i,
                    "error_message": str(initial_error),
                    "traceback": traceback.format_exc()
                }
                fail_file = os.path.join(failed_cases_dir, f"case_{i}_failed.json")
                with open(fail_file, "w", encoding="utf-8") as f:
                    json.dump(error_payload, f, ensure_ascii=False, indent=2)

                print(f"[ERROR] Case {i} failed and recorded to {fail_file}. Continuing batch...")
                with open(f"./{time_error_file}.txt", "a") as file:
                    file.write(f"Time for test case {i}: {round(time.time()-t, 1)}s (f)\n")

if __name__ == "__main__":
    load_dotenv()
    # print(f"Using {os.getenv('LLM_EVAL')} /w {os.getenv('OPENAI_EVAL_MODEL')} as judge")
    # judge=select_llm(os.getenv("LLM_EVAL"), os.getenv("OPENAI_EVAL_MODEL"))
    
    print(f"For grag {os.getenv('LLM_RETRIEVER')}")
    llm = select_llm(os.getenv('LLM_RETRIEVER'))
    grag = GraphRAG(llm=llm)
    try:
        # eval_with_csv(llm=judge,grag=grag)
        eval_with_csv(llm=None,grag=grag)
    finally:
        grag.close()