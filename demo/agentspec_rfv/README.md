# README

* There are two AgentSpec exports in the folder:
  * `red_flag_agentspec_stage1.json` for the question reformulation stage
  * `red_flag_agentspec_stage2.json` for the database query stage

* There are two wheel files in the folder (please install them):
  * Redflagverification: `redflagverification-25.4.0.1-py3-none-any.whl`
  * AgentSpec-LangGraph Adapter: `langgraph_agentspec_adapter-26.1.0.dev0-py3-none-any.whl`
    * Needs to be installed with the "oci" option:
      ```bash
      pip install "langgraph_agentspec_adapter-26.1.0.dev0-py3-none-any.whl[oci]"
      ```

* There are two scripts for running the agents:
  * `fcc_red_flag_export.py` that is primarily used for agentspec export, but note that this has some parts that are required to run the below script (because of tools).
  * `fcc_red_flag_langgraph_import.py` runs the agents using langgraph.

* There are two data folders:
  * `test_data.zip` is the same file that has been shared previously for one end-to-end example (It is the example used in the scripts above).
  * `stage2_toy_benchmark` has some more questions and corresponding data files that can be used to test the stage 2. You should be able to achieve near 100 % accuracy on this data.
