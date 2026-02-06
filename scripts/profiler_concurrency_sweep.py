#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def run_cmd(cmd: list[str]) -> int:
    print("\n>>> Running:", " ".join(cmd), flush=True)
    proc = subprocess.run(cmd)
    return proc.returncode


def find_latest_job_dir(output_dir: Path) -> Path | None:
    jobs_base = output_dir / "jobs"
    if not jobs_base.exists():
        return None
    dirs = [d for d in jobs_base.iterdir() if d.is_dir()]
    if not dirs:
        return None
    dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return dirs[0]


def parse_metrics(job_dir: Path) -> dict:
    # Prefer inference_optimization.json (contains CI and p95)
    path = job_dir / "inference_optimization.json"
    if not path.exists():
        # Fallback to workflow_profiling_metrics.json if needed
        path = job_dir / "workflow_profiling_metrics.json"
        if not path.exists():
            return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}

    # inference_optimization.json layout
    # {
    #   "confidence_intervals": {
    #     "workflow_run_time_confidence_intervals": {"p95": ...},
    #     "llm_latency_confidence_intervals": {"p95": ...},
    #     "throughput_estimate_confidence_interval": {...}
    #   },
    #   ...
    # }
    out: dict = {}
    ci = data.get("confidence_intervals") if isinstance(data, dict) else None
    if ci and isinstance(ci, dict):
        wrt = ci.get("workflow_run_time_confidence_intervals") or {}
        llm = ci.get("llm_latency_confidence_intervals") or {}
        thr = ci.get("throughput_estimate_confidence_interval") or {}
        out["workflow_p95"] = float(wrt.get("p95", 0.0) or 0.0)
        out["llm_p95"] = float(llm.get("p95", 0.0) or 0.0)
        out["throughput_mean"] = float(thr.get("mean", 0.0) or 0.0)
        return out

    # Fallback minimal parsing
    return {}


def main():
    ap = argparse.ArgumentParser(description="Run NAT profiler concurrency sweep and summarize p95 latencies.")
    ap.add_argument("config_file", type=Path, help="Path to NAT YAML config file")
    ap.add_argument("--concurrency", nargs="*", type=int, default=[1, 2, 4, 8],
                    help="Concurrency levels to test (default: 1 2 4 8)")
    ap.add_argument("--reps", type=int, default=20, help="Repetitions to keep the pipeline full (default: 20)")
    ap.add_argument("--base_output", type=Path, default=Path(".tmp/nat/agent_spec_openai/sweep"),
                    help="Base output directory for sweep runs")
    ap.add_argument("--lower_spike_threshold", type=int, default=0,
                    help="If >0, override spike threshold to this value for small tests")
    ap.add_argument("--clean", action="store_true", help="Remove base_output before running")
    args = ap.parse_args()

    base_output = args.base_output
    if args.clean and base_output.exists():
        shutil.rmtree(base_output)

    results: list[tuple[int, dict]] = []
    for c in args.concurrency:
        outdir = base_output / f"c{c}"
        outdir.mkdir(parents=True, exist_ok=True)
        cmd = [
            "nat", "eval",
            "--config_file", str(args.config_file),
            "--reps", str(args.reps),
            "--override", "eval.general.max_concurrency", str(c),
            "--override", "eval.general.output.dir", str(outdir),
        ]
        if args.lower_spike_threshold and args.lower_spike_threshold > 0:
            cmd += ["--override", "eval.general.profiler.concurrency_spike_analysis.spike_threshold",
                    str(args.lower_spike_threshold)]

        rc = run_cmd(cmd)
        if rc != 0:
            print(f"Run failed at concurrency={c} (exit {rc}). Aborting.")
            sys.exit(rc)

        # Find latest job dir and parse metrics
        job_dir = find_latest_job_dir(outdir)
        if not job_dir:
            print(f"No job directory found under {outdir}")
            continue
        metrics = parse_metrics(job_dir)
        results.append((c, metrics))

    # Summary
    print("\n=== Concurrency Sweep Summary ===")
    print(f"Config: {args.config_file}")
    print("concurrency, llm_p95_s, workflow_p95_s, throughput_mean_rps")
    base_llm_p95 = results[0][1].get("llm_p95", 0.0) if results else 0.0
    for c, m in results:
        llm_p95 = m.get("llm_p95", 0.0)
        wf_p95 = m.get("workflow_p95", 0.0)
        thr = m.get("throughput_mean", 0.0)
        rel = (llm_p95 / base_llm_p95) if base_llm_p95 > 0 else 0.0
        print(f"{c:>3}, {llm_p95:.3f}, {wf_p95:.3f}, {thr:.3f}  (x{rel:.2f} vs c{results[0][0]})")

    # Heuristic recommendation: highest c where llm_p95 <= 1.15x baseline
    rec = None
    for c, m in results:
        llm_p95 = m.get("llm_p95", 0.0)
        if base_llm_p95 > 0 and llm_p95 <= 1.15 * base_llm_p95:
            rec = c
    if rec is not None:
        print(f"\nRecommended safe concurrency (<=15% p95 increase): {rec}")
    else:
        print("\nNo safe concurrency found under 15% p95 increase criterion.")


if __name__ == "__main__":
    main()

