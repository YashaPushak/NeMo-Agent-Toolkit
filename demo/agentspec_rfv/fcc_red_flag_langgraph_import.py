# Copyright (C) 2024, 2025 Oracle and/or its affiliates. All rights reserved.

import json
import pprint
from pathlib import Path

import dotenv
from fcc_red_flag_export import (
    _create_planner_from_scratch,
    get_stage_1_tool_registry_from_scratch,
    get_stage_2_tool_registry_from_scratch,
    load_synthetic_data,
)
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph_agentspec_adapter import AgentSpecLoader
from tqdm import tqdm

dotenv.load_dotenv()


_PROJECT_DIR = Path(".")


def _run_reformulation_with_langgraph(graph: CompiledStateGraph, project_dir: Path):
    from redflagverification.stages.constants import (
        CUSTOMER_ID_IO,
        PERIOD_IO,
        SCENARIO_NAME_IO,
        STATEMENT_IO_RAW,
        TABLES_IO,
        THRESHOLD_TABLES,
    )

    _, schema_description, _, threshold_tables = load_synthetic_data(project_dir)
    graph_inputs = {
        TABLES_IO: schema_description,
        STATEMENT_IO_RAW: "Large international transactions transiting through the account",
        SCENARIO_NAME_IO: "Large Reportable Transactions",
        CUSTOMER_ID_IO: "CUTRUSTEDPAIR-002",
        PERIOD_IO: "01/12/2014 to 31/12/2015",
        THRESHOLD_TABLES: threshold_tables,
    }
    config = RunnableConfig({"configurable": {"thread_id": "1"}})
    return graph.invoke({"inputs": graph_inputs}, config)


def _run_planner_with_langgraph(
    graph: CompiledStateGraph, project_dir: Path, question: str | None = None
):
    from redflagverification.stages.constants import DATA_TABLES, STATEMENT_IO, TABLES_IO

    planner = _create_planner_from_scratch(project_dir, question)
    graph_inputs = {
        TABLES_IO: planner.tables,
        STATEMENT_IO: question,
        DATA_TABLES: planner.data_tables,
    }
    config = RunnableConfig({"configurable": {"thread_id": "1"}})
    return graph.invoke({"inputs": graph_inputs}, config)


def load_and_run_stage(stage):
    if stage not in {1, 2}:
        raise ValueError("stage should 1 or 2 (integer type)")

    with open(_PROJECT_DIR / f"red_flag_agentspec_stage{stage}.json", "r") as f:
        json_conf = f.read()

    if stage == 1:
        agent = AgentSpecLoader(
            tool_registry=get_stage_1_tool_registry_from_scratch(_PROJECT_DIR)
        ).load_json(json_conf)
        print("[Stage 1] Import Succeeded!")
        result = _run_reformulation_with_langgraph(agent, _PROJECT_DIR)
        print(f"[Stage 1] Reformulated question:")
        print(result["outputs"]["output"])
        # output keys: ['is_undetermined', 'clarification_questions', 'successful_reformulation', 'tool_output', 'exist_clarify_tag', 'output']
        # • Does at least one row exist in WIRE_TRXN such that TRXN_EXCTN_DT BETWEEN '2014-12-01' AND '2015-12-31', FRGN_TRXN_FL = 'Y', TRXN_BASE_AM ≥ 10000, and (WIRE_TRXN.ORIG_ACCT_ID = CUST_ACCT.ACCT_INTRL_ID OR WIRE_TRXN.BENEF_ACCT_ID = CUST_ACCT.ACCT_INTRL_ID) where CUST_ACCT.CUST_INTRL_ID = 'CUTRUSTEDPAIR-002'?
    elif stage == 2:
        agent = AgentSpecLoader(
            tool_registry=get_stage_2_tool_registry_from_scratch(_PROJECT_DIR)
        ).load_json(json_conf)
        print("[Stage 2] Import Succeeded!")
        result = _run_planner_with_langgraph(
            agent, _PROJECT_DIR
        )  # keys: 'outputs', 'messages', 'node_execution_details'
        print("[Stage 2] Execution Succeeded!")
        print(f"[Stage 2] Executed plan:")
        pprint.pprint(result["outputs"]["output"])  # output keys: ['tool_output', 'output']
        pprint.pprint(result["outputs"]["tool_output"])


#  ['1. Retriever: Pulls from WIRE_TRXN every row whose TRXN_EXCTN_DT is between '
#  "'2014-12-01' and '2015-12-31', TRXN_BASE_AM ≥ 3000, FRGN_TRXN_FL = 'Y', and "
#  'whose ORIG_ACCT_ID or BENEF_ACCT_ID matches an ACCT_INTRL_ID linked in '
#  "CUST_ACCT to CUST_INTRL_ID = 'CUTRUSTEDPAIR-002'. %%INPUT:[]",
#  '2. Informer: Returns the number of rows produced by Step 1. %%INPUT:[STEP1]',
#  '3. Executor: Determines if the count from Step 2 is at least one and answers '
#  'the question accordingly. %%INPUT:[STEP2]']
# ("Step 2's output is (\n"
#  '   qualifying_transactions_count\n'
#  '0                              3\n'
#  ')\n'
#  "Step 3's output is (\n"
#  '- <final answer: Yes>\n'
#  '- <reason: The count is 3, which is greater than 0, indicating at least one '
#  'qualifying record exists.>\n'
#  ')\n')


def load_stage_2():
    with open(_PROJECT_DIR / f"red_flag_agentspec_stage2.json", "r") as f:
        json_conf = f.read()
    agent = AgentSpecLoader(
        tool_registry=get_stage_2_tool_registry_from_scratch(_PROJECT_DIR / "stage2_toy_benchmark")
    ).load_json(json_conf)
    return agent


def run_benchmark_stage_2():
    # Load questions (becnhmark)
    with open(_PROJECT_DIR / Path("stage2_toy_benchmark/questions.json"), "r") as file:
        data = json.load(file)

    # Duplicate data points to challenge LLM's randomness
    data_points = data * 2

    eval_accuracy = 0
    i = 0
    for element in tqdm(data_points):
        try:
            agent = load_stage_2()
            pred = run_stage_2_planner_with_question(agent, element["question"])
            acc = pred == element["output"]
            print(acc)
            eval_accuracy += acc
            i += 1
        except Exception as e:
            print(f"Failure due to Error {e}")

    return eval_accuracy / len(data_points)


def run_stage_2_planner_with_question(agent, question):
    result = _run_planner_with_langgraph(agent, _PROJECT_DIR / "stage2_toy_benchmark", question)
    result = result["outputs"]["tool_output"].lower()
    assert "<final answer: " in result
    if "<final answer: yes" in result:
        pred = "Yes"
    elif "<final answer: no" in result:
        pred = "No"
    else:
        raise ValueError("did not predict, output was:", result)
    return pred


if __name__ == "__main__":
    # load_and_run_stage(1)
    accuracy = run_benchmark_stage_2()
    print("Accuracy of stage 2 on benchmark:", accuracy * 100)
    # 62.5% for langgraph vs 70.8% for wayflow
