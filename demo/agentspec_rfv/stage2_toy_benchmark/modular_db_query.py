# Copyright (C) 2025 Oracle and/or its affiliates. All rights reserved.

import asyncio
import json
import os
from pathlib import Path

from redflagverification.helpers.file_loader import FileLoader
import os
from wayflowcore.models import OpenAIModel
from redflagverification.helpers.schema import format_schema_str
from redflagverification.stages.modular_db_query.planner import (
    ModularDatabasePlanner,
    parse_planner_trace,
)


def main() -> float:
    # Define Paths
    script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    file_loader = FileLoader(
        use_object_store=False,
        local_paths={
            "data_tables_path": str(script_dir / "planner_tables"),
            "tables_schema_path": str(script_dir / "schema.json"),
        },
    )
    schema_json = file_loader.get_tables_schema()
    schema_description = format_schema_str(schema_json)
    data_tables = file_loader.get_data_tables()

    # Load questions (becnhmark)
    questions_path = script_dir / "questions.json"
    with open(questions_path, "r") as file:
        data = json.load(file)

    # Use OpenAI directly instead of OCI GenAI
    openai_model = os.getenv("RFV_OPENAI_MODEL_MASTER", "gpt-4o-mini")
    llm = OpenAIModel(model_id=openai_model)

    # Duplicate data points to challenge LLM's randomness
    data_points = data * 2

    eval_accuracy = 0
    for element in data_points:
        try:
            planner = ModularDatabasePlanner(
                llm=llm,
                question=element["question"],
                tables=schema_description,
                data_tables=data_tables,
            )
            planner_trace = asyncio.run(planner.run())
            last_step_output, _ = parse_planner_trace(planner_trace)
            eval_accuracy += element["output"].lower() in last_step_output.lower()
            print(last_step_output, element["output"])
        except Exception as e:
            print(f"Failure due to Error {e}")

    return eval_accuracy / len(data_points)


if __name__ == "__main__":
    print(f"The Final Accuracy is {main()*100}%")
