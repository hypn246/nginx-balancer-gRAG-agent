import json
import os
import traceback
import pandas as pd
import time

from langchain_core.prompts import PromptTemplate
from .grag import select_llm, _content_to_text

#Vanilla  evaluation, no gRAG

CHECKPOINT = 1
n_case = 100
path = "data/examples"

base_output_dir = "./test11/test_result_vanilla_gemini"

generation_out_dir = os.path.join(base_output_dir, "generation_outputs")
generation_eval_dir = os.path.join(base_output_dir, "generation_evals")
failed_cases_dir = os.path.join(base_output_dir, "failed_cases")

time_file = "test11/time_vanilla_gemini"
time_error_file = "test11/time_error_vanilla_gemini"

for d in [
    generation_out_dir,
    generation_eval_dir,
    failed_cases_dir,
]:
    os.makedirs(d, exist_ok=True)


VANILLA_GENERATION_PROMPT = PromptTemplate.from_template(
    """
You are an expert NGINX performance engineer.

SERVER METRICS:
{question}

Your task is to analyze the server metrics above to provide a suitable NGINX load-balacing method, configuration and analysis to solve the problem in the metrics.

Return your response to JSON with the following structure:
{{
    "analysis": "...",
    "recommended_load_balancing_method": "...",
    "nginx_config": "...",
    "explaination":"..."
}}


"""
)


GENERATION_EVAL_PROMPT = PromptTemplate.from_template(
    """
You are an evaluator assessing a generated NGINX configuration and performance analysis.

SERVER METRICS:
{question}

GENERATED RESPONSE:
{generation}

Task:
Evaluate how well the GENERATED RESPONSE solves the load balacing problem with SERVER METRICS.

Evaluate:
- Accuracy of the analysis. Whether the proposed NGINX configuration is technically valid.
- Whether the recommendations are relevant to the observed metrics.
- Whether the explaination correctly connects the metrics to the proposed solution.
- Overall usefulness for solving the server performance problem.

Criteria and score /100:
+       10: Analyze
+       30: Explain for lba
+       20: LBA
+       40: Nginx config (upstream block)        
Give an integer score from 0-100.

Return JSON:

{{
    "generation_score": 85,
    "config_validity": true,
    "explanation": "The response correctly identifies ...",
}}
"""
)


def create_sample(csv_path):
    df = pd.read_csv(csv_path)

    df["latency"] = df["latency"].apply(lambda x: f"{x}ms")

    df = df[
        [
            "ip",
            "cpu_usage",
            "memory_usage",
            "network_traffic",
            "execution_time",
            "latency",
        ]
    ]

    return df.to_dict(orient="records")

def run_vanilla_generation(llm, question: str):
    chain = VANILLA_GENERATION_PROMPT | llm
    raw_result = chain.invoke({
        "question": question
    })
    generation_text = _content_to_text(raw_result)
    generation_parsed=generation_text
    return generation_parsed


def evaluate_vanilla(llm_gen, llm_eval, input_data: list, case_id: int):
    question_str = json.dumps(input_data,ensure_ascii=False,indent=2)
    generation_parsed = run_vanilla_generation(llm=llm_gen,question=question_str)
    generation_file = os.path.join(
        generation_out_dir,
        f"case_{case_id}.json"
    )

    with open(generation_file,"w",encoding="utf-8") as f:
        json.dump(generation_parsed,f,ensure_ascii=False,indent=2)

    generation_eval_chain = GENERATION_EVAL_PROMPT | llm_eval
    generation_eval_raw = generation_eval_chain.invoke({
        "question": question_str,
        "generation": json.dumps(
            generation_parsed,
            ensure_ascii=False
        )
    })

    generation_eval_res =  _content_to_text(generation_eval_raw)
    generation_eval_file = os.path.join(generation_eval_dir,f"case_{case_id}.json")

    with open(generation_eval_file,"w",encoding="utf-8") as f:
        json.dump(generation_eval_res,f,ensure_ascii=False,indent=2)
    return {
        "generation_eval": generation_eval_res
    }

def eval_with_csv(llm_gen, llm_eval):
    checkpoint = CHECKPOINT
    print(f"Starting vanilla evaluation at case: {checkpoint}")

    for i in range(checkpoint, n_case + 1):
        t = time.time()
        csv_file = f"{path}/case_{i}.csv"

        if not os.path.exists(csv_file):
            print(f"File {csv_file} not found. Skipping...")
            continue

        print("=" * 80)
        print(f"Starting vanilla case_{i}")
        print("=" * 80)

        input_data = create_sample(csv_path=csv_file)

        try:
            res = evaluate_vanilla(llm_gen=llm_gen, llm_eval=llm_eval,input_data=input_data,case_id=i)
            print(f"Finished case_{i}:")
            print(json.dumps(res,ensure_ascii=False,indent=2))
            elapsed = round(time.time() - t, 1)
            with open(f"./{time_file}.txt","a",encoding="utf-8") as file:
                file.write(f"Time for test case {i}: {elapsed}s\n")

        except Exception as error:
            print( f"[ERROR] Case {i} failed {error}")

            error_payload = {
                "case_id": i,
                "error_message": str(error),
                "traceback": traceback.format_exc()
            }
            fail_file = os.path.join(failed_cases_dir,f"case_{i}_failed.json")
            with open(fail_file,"w",encoding="utf-8") as f:
                json.dump(error_payload,f,ensure_ascii=False,indent=2)
            print(f"[ERROR] Case {i} failed and recorded to{fail_file}. Continuing...")
            elapsed = round(time.time() - t, 1)
            with open(f"./{time_error_file}.txt","a",encoding="utf-8") as file:
                file.write(f"Time for test case {i}: {elapsed}s (failed)\n")

"""
py -m test11.vanila_eval
"""
if __name__ == "__main__":
    llm_gen = select_llm(os.getenv("LLM_RETRIEVER"))
    llm_eval = select_llm(os.getenv("LLM_RETRIEVER"))
    # llm_gen = select_llm(os.getenv("LLM_EVAL"), os.getenv("OPENAI_MODEL"))
    # llm_eval = select_llm(os.getenv("LLM_EVAL"), os.getenv("OPENAI_EVAL_MODEL"))
    eval_with_csv(llm_gen=llm_gen,llm_eval=llm_eval)
