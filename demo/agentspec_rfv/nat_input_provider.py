from __future__ import annotations

from pathlib import Path
from typing import Any


def stage2_inputs(user_question: str) -> dict[str, Any]:
    """
    Provide initial inputs for RFV Stage 2 AgentSpec.
    Maps the user input to the AgentSpec's expected input names and 
    loads data tables + schema from RFV_PROJECT_DIR.
    """
    from .fcc_red_flag_export import _create_planner_from_scratch

    project_dir = Path(__file__).resolve().parent / "stage2_toy_benchmark"
    planner = _create_planner_from_scratch(project_dir, user_question)
    return {
        # keys match red_flag_agentspec_stage2.json StartNode inputs
        "tables_io": planner.tables,
        "statement_io": user_question,
        "data_tables": planner.data_tables,
    }

