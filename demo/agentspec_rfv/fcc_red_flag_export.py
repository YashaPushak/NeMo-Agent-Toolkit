# Copyright (C) 2024, 2025 Oracle and/or its affiliates. All rights reserved.

import asyncio
import pprint
from pathlib import Path
from typing import Any, Dict, Tuple

import dotenv

dotenv.load_dotenv()

from wayflowcore.agentspec import AgentSpecExporter, AgentSpecLoader
from wayflowcore.flow import Flow
from wayflowcore.steps import FlowExecutionStep, MapStep, ToolExecutionStep
from wayflowcore.tools import ServerTool
from wayflowcore.tracing.spanprocessor import SimpleSpanProcessor

from redflagverification.helpers.file_loader import FileLoader
import os
from wayflowcore.models import OpenAIModel
from redflagverification.helpers.schema import format_schema_str
from redflagverification.stages.modular_db_query.planner import ModularDatabasePlanner
from redflagverification.stages.query_reformulation_stage.statement_reformulation import (
    _run_reformulation_with_span,
    get_reformulation_flow,
)
from redflagverification.tracing.exporters import InMemoryExporter
from redflagverification.tracing.rfvtrace import RFVTrace


def create_tool_registry_inspecting_flow(flow: Flow) -> dict[str, Any]:
    tool_registry: dict[str, Any] = {}
    for step_name, step in flow.steps.items():
        if isinstance(step, ToolExecutionStep):
            if isinstance(step.tool, ServerTool):
                tool_registry[step.tool.name] = step.tool.func
        elif isinstance(step, (FlowExecutionStep, MapStep)):
            tool_registry = {
                **tool_registry,
                **create_tool_registry_inspecting_flow(step.sub_flow()),
            }
    return tool_registry


def load_synthetic_data(project_dir: str | Path, stage=1):
    _PROJECT_DIR = Path(project_dir).resolve()
    file_paths = {
        "tables_schema_path": str(_PROJECT_DIR / "schema.json"),
        "data_tables_path": str(_PROJECT_DIR / "planner_tables"),
        "threshold_tables_path": str(_PROJECT_DIR / "thresholds_tables"),
        "knowledge_base_path": str(_PROJECT_DIR / "knowledge_base.json"),
    }
    file_loader = FileLoader(use_object_store=False, local_paths=file_paths)
    if stage != 2:
        knowledge_base = file_loader.get_knowledge_base()
    else:
        knowledge_base = None
    schema_json = file_loader.get_tables_schema()
    schema_description = format_schema_str(schema_json)
    data_tables = file_loader.get_data_tables()
    if stage != 2:
        threshold_tables = file_loader.get_threshold_tables()
    else:
        threshold_tables = None
    return knowledge_base, schema_description, data_tables, threshold_tables


def get_stage_1_tool_registry_from_scratch(project_dir):
    knowledge_base, _, _, _ = load_synthetic_data(project_dir, stage=1)
    # Use OpenAI directly instead of OCI GenAI
    openai_model_master = os.getenv("RFV_OPENAI_MODEL_MASTER", "gpt-4o-mini")
    openai_model_question = os.getenv("RFV_OPENAI_MODEL_QUESTION", openai_model_master)
    llm_master = OpenAIModel(model_id=openai_model_master)
    llm_question = OpenAIModel(model_id=openai_model_question)
    flow = get_reformulation_flow(llm_master, llm_question, knowledge_base)
    tool_registry = create_tool_registry_inspecting_flow(flow)
    return tool_registry


def _create_planner_from_scratch(project_dir, question=None):
    _, schema_description, data_tables, _ = load_synthetic_data(project_dir, stage=2)
    # Use OpenAI directly instead of OCI GenAI
    openai_model_master = os.getenv("RFV_OPENAI_MODEL_MASTER", "gpt-4o-mini")
    llm_master = OpenAIModel(model_id=openai_model_master)
    planner = ModularDatabasePlanner(
        llm_master, question, schema_description, data_tables
    )
    return planner


def get_stage_2_tool_registry_from_scratch(project_dir) -> dict[str, Any]:
    planner = _create_planner_from_scratch(project_dir, "dummy-question-not-used")
    flow = planner.moodular_db_flow()
    tool_registry = create_tool_registry_inspecting_flow(flow)
    return tool_registry


# ----------------------------- Helpers ----------------------------- #
def export_flow_to_json(flow: Any) -> str:
    return AgentSpecExporter().to_json(flow)


def persist_agentspec(path: Path | str, json_config: str) -> None:
    Path(path).write_text(json_config, encoding="utf-8")
    print("Agent spec persisted to", path)


def load_flow_from_json(json_config: str, flow_for_tools: Any) -> Any:
    tool_registry = create_tool_registry_inspecting_flow(flow_for_tools)
    return AgentSpecLoader(tool_registry=tool_registry).load_json(json_config)


def assert_no_plugins(json_config: str, stage_label: str) -> None:
    assert "Plugin" not in json_config, f"Plugins are still present in the config ({stage_label})"


# ----------------------------- Stage 1 ----------------------------- #
async def run_stage1(
    agentspec_stage1_path: str,
    llm_master: Any,
    llm_question: Any,
    knowledge_base: Any,
    schema_description: Any,
    threshold_tables: Any,
) -> Tuple[str, Dict[str, Any]]:
    print("[Stage 1] Building reformulation flow")
    flow = get_reformulation_flow(llm_master, llm_question, knowledge_base)

    json_config = export_flow_to_json(flow)
    print("[Stage 1] Export succeeded")
    persist_agentspec(agentspec_stage1_path, json_config)
    assert_no_plugins(json_config, "Stage 1")

    loaded_flow = load_flow_from_json(json_config, flow)
    print("[Stage 1] Import succeeded:", type(loaded_flow))

    exporter = InMemoryExporter()
    final_result: Dict[str, Any] = {}

    print("[Stage 1] Executing reformulation with tracing")
    with RFVTrace(debug=True, span_processors=[SimpleSpanProcessor(exporter)]):
        result, status, conversation = await _run_reformulation_with_span(
            flow=loaded_flow,
            tables=schema_description,
            statement="Large international transactions transiting through the account",
            scenario="Large Reportable Transactions",
            customer_id="CUTRUSTEDPAIR-002",
            period="01/12/2014 to 31/12/2015",
            threshold_tables=threshold_tables,
            span_exporter=exporter,
        )

    print("[Stage 1] Execution succeeded")
    reformulated_question = result["final_reformulation"]
    print("[Stage 1] Reformulated question:")
    print(reformulated_question)
    # - Does at least one record exist in WIRE_TRXN where TRXN_EXCTN_DT is on or after '2014-12-01' and on or before '2015-12-31'?
    # - AND WIRE_TRXN.FRGN_TRXN_FL = 'Y' (indicating an international transaction).
    # - AND WIRE_TRXN.TRXN_BASE_AM is greater than or equal to 10,000 USD.
    # - AND (WIRE_TRXN.ORIG_ACCT_ID = ACCT_INTRL_ID OR WIRE_TRXN.BENEF_ACCT_ID = ACCT_INTRL_ID) for any ACCT_INTRL_ID that, via CUST_ACCT, is linked to CUST_INTRL_ID = 'CUTRUSTEDPAIR-002'?
    return reformulated_question, final_result


# ----------------------------- Stage 2 ----------------------------- #
async def run_stage2(
    agentspec_stage2_path,
    llm_master: Any,
    reformulated_question: str,
    schema_description: Any,
    data_tables: Any,
) -> Dict[str, Any]:
    print("[Stage 2] Building modular DB planner")
    planner = ModularDatabasePlanner(
        llm_master, reformulated_question, schema_description, data_tables
    )
    flow = planner.moodular_db_flow()

    json_config = export_flow_to_json(flow)
    print("[Stage 2] Export succeeded")
    persist_agentspec(agentspec_stage2_path, json_config)
    assert_no_plugins(json_config, "Stage 2")

    loaded_flow = load_flow_from_json(json_config, flow)
    print("[Stage 2] Import succeeded:", type(loaded_flow))

    exporter = InMemoryExporter()
    print("[Stage 2] Executing planner with tracing")
    with RFVTrace(debug=True, span_processors=[SimpleSpanProcessor(exporter)]):
        result = await planner._run_planner_with_span(
            flow=loaded_flow,
            span_exporter=exporter,
        )

    print("[Stage 2] Execution succeeded")
    print("[Stage 2] Executed plan:")
    pprint.pprint(result["steps_execution"])
    #     [{'module': 'Retriever',
    #   'output': 'SELECT\n'
    #             '  TRXN_INTRL_REF_ID,\n'
    #             '  TRXN_EXCTN_DT,\n'
    #             '  TRXN_BASE_AM,\n'
    #             '  ORIG_ACCT_ID,\n'
    #             '  BENEF_ACCT_ID,\n'
    #             '  FRGN_TRXN_FL\n'
    #             'FROM WIRE_TRXN\n'
    #             "WHERE TRXN_EXCTN_DT BETWEEN '2014-12-01' AND '2015-12-31'\n"
    #             '  AND TRXN_BASE_AM >= 3000\n'
    #             "  AND FRGN_TRXN_FL = 'Y'\n"
    #             '  AND (\n'
    #             '        ORIG_ACCT_ID IN (\n'
    #             '            SELECT ACCT_INTRL_ID\n'
    #             '            FROM CUST_ACCT\n'
    #             "            WHERE CUST_INTRL_ID = 'CUTRUSTEDPAIR-002'\n"
    #             '        )\n'
    #             '     OR BENEF_ACCT_ID IN (\n'
    #             '            SELECT ACCT_INTRL_ID\n'
    #             '            FROM CUST_ACCT\n'
    #             "            WHERE CUST_INTRL_ID = 'CUTRUSTEDPAIR-002'\n"
    #             '        )\n'
    #             '  );\n',
    #   'step': '1. Retriever: Select rows from WIRE_TRXN that (a) have '
    #           "TRXN_EXCTN_DT between '2014-12-01' and '2015-12-31', (b) "
    #           "TRXN_BASE_AM ≥ 3000, (c) FRGN_TRXN_FL = 'Y', and (d) ORIG_ACCT_ID "
    #           'or BENEF_ACCT_ID is in CUST_ACCT for CUST_INTRL_ID = '
    #           "'CUTRUSTEDPAIR-002'. %%INPUT:[]"},
    #  {'module': 'Informer',
    #   'output': 'SELECT COUNT(*) AS row_count\nFROM STEP1;\n',
    #   'step': '2. Informer: Count how many rows were returned in Step 1. '
    #           '%%INPUT:[STEP1]'},
    #  {'module': 'Executor',
    #   'output': '- <final answer: Yes>\n'
    #             '- <reason: Count from Step 2 is 3, which meets the at-least-1 '
    #             'condition.>',
    #   'step': '3. Executor: Conclude “Yes” if the count from Step 2 is at least 1; '
    #           'otherwise conclude “No”. %%INPUT:[STEP2]'}]
    return result


# ----------------------------- Orchestration ----------------------------- #
async def async_main():
    PROJECT_DIR = Path(".")
    knowledge_base, schema_description, data_tables, threshold_tables = load_synthetic_data(
        PROJECT_DIR
    )

    # Ensure model usage aligns with Oracle policies and approved endpoints
    llm_master = get_llm(ocigenai_model="openai.o3")
    llm_question = get_llm(ocigenai_model="meta.llama-3.3-70b-instruct")

    # Stage 1
    reformulated_q, _ = await run_stage1(
        agentspec_stage1_path="red_flag_agentspec_stage1.json",
        llm_master=llm_master,
        llm_question=llm_question,
        knowledge_base=knowledge_base,
        schema_description=schema_description,
        threshold_tables=threshold_tables,
    )

    # Prefer the computed reformulation, but fall back to the predefined one if empty
    reformulated_question = (
        "Does at least one record exist in WIRE_TRXN where TRXN_EXCTN_DT is between "
        "'2014-12-01' and '2015-12-31' inclusive, TRXN_BASE_AM ≥ 3000, FRGN_TRXN_FL = 'Y', "
        "and (ORIG_ACCT_ID or BENEF_ACCT_ID) matches an ACCT_INTRL_ID that appears in "
        "CUST_ACCT with CUST_INTRL_ID = 'CUTRUSTEDPAIR-002'?"
    )

    # Stage 2
    await run_stage2(
        agentspec_stage2_path="red_flag_agentspec_stage2.json",
        llm_master=llm_master,
        reformulated_question=reformulated_question,
        schema_description=schema_description,
        data_tables=data_tables,
    )


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
