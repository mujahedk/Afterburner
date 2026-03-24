#!/usr/bin/env python3
"""
Failure simulation harness for Afterburner.

Submits 110 jobs across four scenarios and waits for all of them to reach a
terminal state (succeeded or dead), then asserts that the observed outcomes
match the expected outcomes.

Usage:
    python scripts/simulate_failures.py [--base-url http://localhost:8000]

Requires the API to be running. Start the full stack first:
    docker compose up --build
"""
import argparse
import sys
import time
from dataclasses import dataclass
from typing import Literal

try:
    import requests
except ImportError:
    sys.exit("requests is not installed. Run: pip install requests")


# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------

@dataclass
class Scenario:
    label: str
    job_type: str
    payload: dict
    max_attempts: int
    count: int
    expected_terminal: Literal["succeeded", "dead"]


SCENARIOS: list[Scenario] = [
    Scenario(
        label="immediate success (sleep)",
        job_type="sleep",
        payload={"duration_ms": 200},
        max_attempts=3,
        count=30,
        expected_terminal="succeeded",
    ),
    Scenario(
        label="success after 1 retry (fail_n_times=1, max=5)",
        job_type="fail_n_times",
        payload={"failures_before_success": 1},
        max_attempts=5,
        count=20,
        expected_terminal="succeeded",
    ),
    Scenario(
        label="success after 2 retries (fail_n_times=2, max=5)",
        job_type="fail_n_times",
        payload={"failures_before_success": 2},
        max_attempts=5,
        count=30,
        expected_terminal="succeeded",
    ),
    Scenario(
        label="dead-lettered (fail_n_times=3, max=3)",
        job_type="fail_n_times",
        payload={"failures_before_success": 3},
        max_attempts=3,
        count=30,
        expected_terminal="dead",
    ),
]

TOTAL_JOBS = sum(s.count for s in SCENARIOS)   # 110


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def submit_job(base_url: str, job_type: str, payload: dict, max_attempts: int) -> str:
    resp = requests.post(
        f"{base_url}/api/jobs",
        json={"type": job_type, "payload": payload, "max_attempts": max_attempts},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def get_status(base_url: str, job_id: str) -> dict:
    resp = requests.get(f"{base_url}/api/jobs/{job_id}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def is_terminal(status: str) -> bool:
    return status in ("succeeded", "dead")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(base_url: str, timeout_seconds: int = 180) -> int:
    print(f"Afterburner failure simulation — {TOTAL_JOBS} jobs")
    print(f"API: {base_url}\n")

    # Health check
    try:
        requests.get(f"{base_url}/health", timeout=5).raise_for_status()
    except Exception as e:
        print(f"ERROR: API not reachable at {base_url}  ({e})")
        print("Start the stack first:  docker compose up --build")
        return 1

    # Track which scenario each job_id belongs to
    job_scenario: dict[str, Scenario] = {}

    # Submit all jobs
    print("Submitting jobs...")
    for scenario in SCENARIOS:
        for _ in range(scenario.count):
            job_id = submit_job(
                base_url, scenario.job_type, scenario.payload, scenario.max_attempts
            )
            job_scenario[job_id] = scenario
    print(f"  {len(job_scenario)} jobs submitted\n")

    # Poll until all reach a terminal state or we time out
    print("Waiting for all jobs to reach terminal state...")
    deadline = time.time() + timeout_seconds
    statuses: dict[str, str] = {}

    while True:
        pending = [jid for jid, s in statuses.items() if not is_terminal(s)]
        pending += [jid for jid in job_scenario if jid not in statuses]

        if not pending:
            break

        if time.time() > deadline:
            print(f"\nTIMEOUT: {len(pending)} jobs still pending after {timeout_seconds}s")
            break

        for job_id in pending:
            data = get_status(base_url, job_id)
            statuses[job_id] = data["status"]

        done = sum(1 for s in statuses.values() if is_terminal(s))
        total = len(job_scenario)
        print(f"  {done}/{total} complete", end="\r", flush=True)
        time.sleep(2)

    print()

    # ---------------------------------------------------------------------------
    # Assertions
    # ---------------------------------------------------------------------------
    failures = 0

    print("\n--- Results by scenario ---\n")
    for scenario in SCENARIOS:
        job_ids = [jid for jid, s in job_scenario.items() if s is scenario]
        terminal_statuses = [statuses.get(jid, "pending") for jid in job_ids]

        correct = sum(1 for s in terminal_statuses if s == scenario.expected_terminal)
        wrong = [(jid, s) for jid, s in zip(job_ids, terminal_statuses) if s != scenario.expected_terminal]

        status_icon = "PASS" if not wrong else "FAIL"
        print(f"  [{status_icon}]  {scenario.label}")
        print(f"         count={scenario.count}  expected={scenario.expected_terminal}  correct={correct}  wrong={len(wrong)}")

        if wrong:
            for jid, s in wrong[:5]:
                print(f"           job {jid[:8]}  got={s}")
            if len(wrong) > 5:
                print(f"           ... and {len(wrong) - 5} more")
            failures += 1

        print()

    # Summary
    total_correct = sum(
        1 for jid, s in statuses.items()
        if s == job_scenario[jid].expected_terminal
    )
    total_terminal = sum(1 for s in statuses.values() if is_terminal(s))

    print("--- Summary ---\n")
    print(f"  Total jobs submitted : {TOTAL_JOBS}")
    print(f"  Reached terminal     : {total_terminal}")
    print(f"  Correct outcome      : {total_correct}/{TOTAL_JOBS}")
    print()

    if failures == 0 and total_terminal == TOTAL_JOBS:
        print("ALL SCENARIOS PASSED")
        return 0
    else:
        print("SOME SCENARIOS FAILED — see details above")
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Afterburner failure simulation")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL of the Afterburner API (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="Max seconds to wait for all jobs to complete (default: 180)",
    )
    args = parser.parse_args()
    sys.exit(run(args.base_url, args.timeout))
