**AgentSpec RFV Standalone Guide**

- Purpose: Understand the provided AgentSpec-based financial investigator (Red Flag Verification) assets and how to run them standalone, outside of NeMo Agent Toolkit (NAT).
- Location: Files are unpacked under `demo/agentspec_rfv/`.

**Contents**
- `README.md`: Brief overview and installation notes.
- `fcc_red_flag_export.py`: Wayflow-based script that builds two flows (Stage 1: question reformulation, Stage 2: modular DB planner), exports to AgentSpec JSON, reloads them, and runs both with tracing.
- `fcc_red_flag_langgraph_import.py`: Runs the same AgentSpec JSON via LangGraph using an AgentSpec-LangGraph adapter; also includes a toy benchmark driver for Stage 2.
- `red_flag_agentspec_stage1.json`: AgentSpec export for Stage 1 (reformulation pipeline).
- `red_flag_agentspec_stage2.json`: AgentSpec export for Stage 2 (planner pipeline).
- `langgraph_agentspec_adapter-26.1.0.dev0-py3-none-any.whl`: AgentSpec-LangGraph adapter wheel (install with `[oci]` extra when using OCI models).
- `redflagverification-25.4.0.1-py3-none-any.whl`: Core RFV package including wayflow components, tools, helpers, and tracing.
- `test_data.zip`: Small end-to-end dataset (schema, tables, thresholds, KB) used by `fcc_red_flag_export.py`.
- `stage2_toy_benchmark/`: Larger CSV tables and a `questions.json` for Stage 2 benchmarking; also includes a standalone planner script `modular_db_query.py`.

**High-Level Stages**
- Stage 1 (Reformulation): Reformulates a red-flag statement into a concrete, structured question using two LLMs and knowledge base context.
- Stage 2 (Planner): Given the reformulated question and table schema/data (CSV), plans and executes a sequence of retrieval, aggregation, and decision steps to derive the final Yes/No answer.

**Key Entry Points**
- Wayflow + AgentSpec export/run: `demo/agentspec_rfv/fcc_red_flag_export.py`
  - Exports both stages to AgentSpec JSON (`red_flag_agentspec_stage{1,2}.json`), asserts no plugin artifacts, reloads via AgentSpec loader, and executes with tracing.
  - Uses `redflagverification.helpers.llm_helper.get_llm` to obtain an OCI GenAI model client. Defaults: `openai.o3` for “master” and `meta.llama-3.3-70b-instruct` for “question”.
  - Reads synthetic data from the local project directory (`schema.json`, `planner_tables/`, `thresholds_tables/`, `knowledge_base.json`). For the included example, these come from `test_data.zip` (see Setup below).

- LangGraph + AgentSpec import/run: `demo/agentspec_rfv/fcc_red_flag_langgraph_import.py`
  - Loads `red_flag_agentspec_stage1.json` or `stage2.json` and executes via `langgraph_agentspec_adapter.AgentSpecLoader`.
  - Functions:
    - `load_and_run_stage(stage: 1|2)`: One-off Stage 1 or Stage 2 execution on the small example dataset.
    - `run_benchmark_stage_2()`: Evaluates Stage 2 planning accuracy against `stage2_toy_benchmark/questions.json`.
    - `run_stage_2_planner_with_question(agent, question)`: Helper to run Stage 2 for a single question and parse final Yes/No.

- Standalone planner benchmark: `demo/agentspec_rfv/stage2_toy_benchmark/modular_db_query.py`
  - Directly constructs and runs the ModularDatabasePlanner over the `stage2_toy_benchmark` tables, evaluating accuracy against `questions.json`.

**Data Expectations**
- Minimal example data (for Wayflow script): `test_data/` contains:
  - `planner_tables/` with `ACCT.csv`, `CUST.csv`, `CUST_ACCT.csv`, `WIRE_TRXN.csv`, `CASH_TRXN.csv`
  - `schema.json` describing table columns and relationships
  - `thresholds_tables/` with thresholds (e.g., `TSHLD.csv`) and scenarios (`SCNRO.csv`)
  - `knowledge_base.json` with scenario knowledge used in Stage 1
- Stage 2 toy benchmark: Larger CSVs under `stage2_toy_benchmark/planner_tables/`, plus `schema.json` and `questions.json`.

**Dependencies**
- Python 3.10+
- From wheels included:
  - `redflagverification-25.4.0.1-py3-none-any.whl` (requires: `wayflowcore>=25.4.0`, `pandas`, `sqlalchemy>=2.0.41`, `numpy`, `requests`, `oracledb`, `oci>=2.158.2`, `python-dotenv` for dev).
  - `langgraph_agentspec_adapter-26.1.0.dev0-py3-none-any.whl` (requires: `pyagentspec==26.1.0.dev0`, `langgraph>=0.5.3`, `langchain-core>=0.3`, `httpx>0.28.0`, `langchain-openai>=0.3.7`, `langchain-ollama>=0.3.3`; extra `oci` adds `langchain-oci==0.2.0`).
- OCI GenAI access: `redflagverification.helpers.llm_helper.get_llm` creates an `OCIGenAIModel` and requires `OCI_COMPARTMENT_ID` and valid OCI API key config; it uses service endpoint `https://inference.generativeai.us-chicago-1.oci.oraclecloud.com`.

**Environment Setup**
1) Create and activate a Python 3.10+ virtual environment.
2) Install required wheels (local):
   - `pip install demo/agentspec_rfv/redflagverification-25.4.0.1-py3-none-any.whl`
   - For LangGraph runs: `pip install "demo/agentspec_rfv/langgraph_agentspec_adapter-26.1.0.dev0-py3-none-any.whl[oci]"`
   - If not present, install runtime deps for `redflagverification` (e.g., `pandas`, `sqlalchemy`, `numpy`, `oci`, `oracledb`). Many are pulled transitively by the wheel.
3) Set OCI credentials and region as required by `OCIClientConfigWithApiKey` and `OCIGenAIModel`:
   - `export OCI_COMPARTMENT_ID=ocid1.compartment.oc1..xxxxx`
   - Ensure the standard OCI API key config is available (env vars or default config file) compatible with `wayflowcore` client; `.env` is auto-loaded if present.

**Prepare Example Data**
- For `fcc_red_flag_export.py`, unpack the small example data next to the script:
  - `unzip demo/agentspec_rfv/test_data.zip -d demo/agentspec_rfv/`
  - This creates `demo/agentspec_rfv/test_data/` with required files. Either:
    - Run from within `demo/agentspec_rfv/test_data/` so relative paths resolve; or
    - Edit the script’s `PROJECT_DIR` to point to `test_data`.
- For Stage 2 toy benchmark, no unpacking needed beyond the repository files; it uses `stage2_toy_benchmark/` in place.

**How To Run (Wayflow + AgentSpec export/import)**
- From `demo/agentspec_rfv/test_data/` (or adjust `PROJECT_DIR`):
  - `python ../fcc_red_flag_export.py`
  - Behavior:
    - Stage 1: builds, exports to `red_flag_agentspec_stage1.json`, reloads, and executes reformulation; prints reformulated question.
    - Stage 2: builds from reformulated question, exports to `red_flag_agentspec_stage2.json`, reloads, and executes planner; prints executed plan and final decision trace.

**How To Run (LangGraph + AgentSpec import)**
- One-off stage run with the small example data:
  - `python demo/agentspec_rfv/fcc_red_flag_langgraph_import.py` (default main runs Stage 2 benchmark—see next section). To run a single stage:
    - Edit main to call `load_and_run_stage(1)` or `load_and_run_stage(2)`.
  - Alternatively, from an interactive session:
    - Stage 1: `load_and_run_stage(1)` prints the reformulated question.
    - Stage 2: `load_and_run_stage(2)` prints the planned steps and tool outputs.

**How To Run (Stage 2 Toy Benchmark)**
- Using LangGraph agent:
  - `python demo/agentspec_rfv/fcc_red_flag_langgraph_import.py`
  - Default main calls `run_benchmark_stage_2()` which:
    - Loads `stage2_toy_benchmark/questions.json`, duplicates items to reduce randomness effects, and reports aggregate accuracy.
- Using Wayflow planner directly:
  - `python demo/agentspec_rfv/stage2_toy_benchmark/modular_db_query.py`
  - Prints planner step outputs and final overall accuracy across the questions.

**Notes and Assumptions**
- LLM Access: Both the Wayflow and LangGraph paths use OCI GenAI models via `OCIGenAIModel`; valid OCI credentials and `OCI_COMPARTMENT_ID` are required. Model IDs used in scripts are examples; ensure the tenancy has access to `openai.o3` and `meta.llama-3.3-70b-instruct` aliases or adjust accordingly.
- JSON exports: `red_flag_agentspec_stage{1,2}.json` are generated/overwritten by the Wayflow script and then reused by the LangGraph adapter.
- Tool registry: Tools are discovered from the Wayflow graphs and passed into the AgentSpec loader, ensuring tool invocations for data retrieval, aggregation, etc., function correctly when running from the exported JSON.
- Data shape: Schema (`schema.json`) and table files must match the column names referenced in questions; otherwise, planner execution can fail.
- Performance: The toy benchmark is designed for near-100% accuracy with the intended models; results may vary with different models or temperature settings.

This document captures the standalone execution flow; next, we can wire the AgentSpec configs into NeMo Agent Toolkit via a suitable NAT config to demo running the RFV agent end-to-end.

