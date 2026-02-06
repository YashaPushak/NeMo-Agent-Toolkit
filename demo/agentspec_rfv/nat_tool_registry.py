import os
from pathlib import Path
from typing import Any


def stage2_factory() -> dict[str, Any]:
    """
    Build the RFV Stage 2 tool registry by constructing the Modular DB planner
    and introspecting its flow to extract ServerTool callables.

    Environment variables:
    - RFV_PROJECT_DIR: optional path to dataset dir (defaults to stage2_toy_benchmark)
    - OCI_COMPARTMENT_ID: set to a placeholder if not provided to satisfy RFV's get_llm()
    """
    # Avoid RFV get_llm() failing on missing compartment id during planner construction
    os.environ.setdefault("OCI_COMPARTMENT_ID", "placeholder-compartment-id")

    # Local import to keep dependency surface small for NAT users
    from .fcc_red_flag_export import get_stage_2_tool_registry_from_scratch

    project_dir = os.getenv(
        "RFV_PROJECT_DIR",
        str(Path(__file__).resolve().parent / "stage2_toy_benchmark"),
    )
    return get_stage_2_tool_registry_from_scratch(project_dir)

