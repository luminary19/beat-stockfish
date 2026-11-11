#!/usr/bin/env python3
"""Run the approved 15-episode A/B/D pilot, with four concurrent episodes.

Run with .venv/bin/python experiments/run_step2.py. Repeating this command
resumes the same per-episode eval sets rather than scheduling new samples.
"""
from __future__ import annotations

import csv
import fcntl
import hashlib
import importlib.metadata
import json
import os
import random
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from inspect_ai.log import list_eval_logs, read_eval_log

from analyze import episode

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs" / "step2-abd"
PROMPTS = {
    "a": "step2-a-interpretation.txt",
    "b": "step2-b-user-question.txt",
    "d": "step2-d-assumptions.txt",
}


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def command(arm: str, replicate: int) -> list[str]:
    return [
        sys.executable, str(ROOT / "run/rollout.py"),
        "--model", "openai/gpt-6-astra", "--epochs", "1",
        "--variants", "v001", "--turn-limit", "100",
        "--time-limit", "10800", "--reasoning-effort", "high",
        "--image", "beat-stockfish:local", "--debrief", "--max-samples", "1",
        "--system-prompt-file", str(ROOT / "experiments/prefills" / PROMPTS[arm]),
        "--log-dir", str(LOGS / arm / f"run-{replicate:02d}"),
    ]


def run_one(arm: str, replicate: int) -> dict:
    directory = LOGS / arm / f"run-{replicate:02d}"
    directory.mkdir(parents=True, exist_ok=True)
    print(f"{stamp()} START {arm}/{replicate}", flush=True)
    started = stamp()
    with (directory / "console.log").open("a") as console:
        result = subprocess.run(command(arm, replicate), cwd=ROOT,
                                stdout=console, stderr=subprocess.STDOUT)
    status = {"arm": arm, "replicate": replicate, "started": started,
              "finished": stamp(), "returncode": result.returncode}
    (directory / "status.json").write_text(json.dumps(status, indent=2) + "\n")
    print(f"{stamp()} END {arm}/{replicate} exit={result.returncode}", flush=True)
    return status


def main() -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    with (LOGS / "campaign.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Randomize within five blocks to spread each arm across launch time.
        rng = random.Random(20261105)
        schedule = []
        for replicate in range(1, 6):
            arms = list(PROMPTS)
            rng.shuffle(arms)
            schedule.extend((arm, replicate) for arm in arms)
        files = [ROOT / "run/rollout.py", ROOT / "run/env.json",
                 Path(__file__).resolve(),
                 *(ROOT / "experiments/prefills" / name for name in PROMPTS.values())]
        manifest = {
            "model": "openai/gpt-6-astra",
            "proxy_url": os.environ.get("OPENAI_BASE_URL"),
            "inspect_ai": importlib.metadata.version("inspect_ai"),
            "image_id": subprocess.check_output(
                ["docker", "image", "inspect", "beat-stockfish:local", "--format", "{{.Id}}"],
                text=True).strip(),
            "turn_limit": 100, "time_limit_s": 10800, "reasoning_effort": "high",
            "debrief": True, "max_concurrent_episodes": 4,
            "episodes_per_arm": 5, "schedule": schedule,
            "sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in files},
            "commands": [command(a, n) for a, n in schedule],
        }
        path = LOGS / "manifest.json"
        serialized = json.dumps(manifest, indent=2) + "\n"
        if path.exists() and path.read_text() != serialized:
            raise SystemExit("Campaign configuration changed; refusing to mix results.")
        path.write_text(serialized)
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(run_one, a, n) for a, n in schedule]
            statuses = [f.result() for f in as_completed(futures)]

        # Summarize locally: no extra model calls, and no overwrite of step 1 CSVs.
        rows = []
        for arm, replicate in schedule:
            logs = list_eval_logs(str(LOGS / arm / f"run-{replicate:02d}"))
            if not logs:
                continue
            log = read_eval_log(logs[0])
            for sample in log.samples or []:
                row = asdict(episode(arm, sample))
                row["replicate"] = replicate
                row["eval_status"] = log.status
                rows.append(row)
        if rows:
            with (LOGS / "episodes.csv").open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
        counts = {a: sum(r["arm"] == a for r in rows) for a in PROMPTS}
        print(f"{stamp()} FINISHED sample counts={counts}", flush=True)
        (LOGS / "statuses.json").write_text(json.dumps(statuses, indent=2) + "\n")
        if any(s["returncode"] for s in statuses) or any(n != 5 for n in counts.values()):
            raise SystemExit("Pilot incomplete; inspect statuses and resume the same command.")


if __name__ == "__main__":
    main()
