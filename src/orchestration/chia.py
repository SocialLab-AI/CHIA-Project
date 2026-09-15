"""Canonical bounded campaign controller on Adam; deterministic policy is the default."""

from pathlib import Path
import time
import yaml
from src.common.candidate import ROOT, Candidate
from src.common.errors import ConfigError, failure
from src.common.security import safe_id, finite_number
from src.common.records import atomic_json
from src.orchestration.dispatch import LocalDispatcher, ChiaDispatcher
from src.orchestration.experiment import run_experiment
from src.orchestration.policies import deterministic_candidates, pareto


def chia_entrypoint(config=None, *, dispatcher=None):
    config = config or {}
    campaign_id = safe_id(config.get("campaign_id", "deterministic-local"))
    iterations = config.get("iterations", 3)
    if (
        isinstance(iterations, bool)
        or not isinstance(iterations, int)
        or not 1 <= iterations <= 100
    ):
        raise ConfigError("iterations must be at least 1 and no more than 100.")
    budget = finite_number(
        config.get("wall_budget_seconds", 1800), "wall_budget_seconds", positive=True
    )
    runtime = config.get("runtime", {})
    policy = yaml.safe_load(
        (ROOT / "experiment-contracts/policies/compute-policy.yaml").read_text()
    )
    tier = config.get("tier", "dev")
    backend = config.get("backend", "local")
    if tier not in policy["tiers"] or backend not in policy["tiers"][tier]["backends"]:
        raise ConfigError("Execution backend is not allowed in this compute tier.")
    # Local runs are serial; CHIA fans out two runtime nodes.
    mode = config.get("mode", "local")
    if mode not in {"local", "chia"}:
        raise ConfigError("Unknown execution mode.")
    if mode == "chia" and policy["tiers"][tier]["max_parallel_jobs"] < 2:
        raise ConfigError("This tier does not allow both runtime nodes concurrently.")
    for name, default in (("software", 120), ("hardware", 600)):
        runtime.setdefault(name, {})
        runtime[name].setdefault("timeout_seconds", default)
        runtime[name].setdefault("retries", 0)
        finite_number(
            runtime[name]["timeout_seconds"], name + " timeout", positive=True
        )
        if (
            type(runtime[name]["retries"]) is not int
            or not 0 <= runtime[name]["retries"] <= 2
        ):
            raise ConfigError(
                "Transient retries must be an integer between zero and two."
            )
    results_root = Path(
        config.get("results_root", ROOT / "results/full-loop")
    ).resolve()
    directory = results_root / campaign_id
    directory.mkdir(parents=True, exist_ok=False)
    dispatcher = dispatcher or (
        ChiaDispatcher(config.get("ray_address", "auto"))
        if mode == "chia"
        else LocalDispatcher()
    )
    history = []
    seen = set()
    skipped = []
    start = time.monotonic()
    reason = "candidate_list_exhausted"
    candidates = config.get("candidates", deterministic_candidates())
    optimizer_config = config.get("optimizer", {})
    optimizer = None
    if optimizer_config.get("enabled", False):
        if not policy["tiers"][tier]["gemini_allowed"]:
            raise ConfigError("This compute tier forbids Gemini calls.")
        if (
            optimizer_config.get("policy") != "gemini_cli"
            or optimizer_config.get("reviewed_cli_safety") is not True
        ):
            raise ConfigError(
                "Gemini CLI requires explicit policy and reviewed tool-isolation settings."
            )
        cap = optimizer_config.get("max_calls")
        if type(cap) is not int or not 1 <= cap <= iterations:
            raise ConfigError("Optimizer max_calls must be bounded by iteration count.")
        if policy["gemini"].get("metering_required", False):
            raise ConfigError(
                "Gemini CLI activation is blocked by the current mandatory dollar-metering policy. Implement reviewed CLI usage pricing before activation; do not weaken compute policy."
            )
        from src.orchestration.gemini_cli import GeminiCLIOptimizer

        optimizer = GeminiCLIOptimizer(
            executable=optimizer_config["executable"],
            model=optimizer_config["model"],
            expected_version=optimizer_config["expected_version"],
            timeout_seconds=optimizer_config.get("timeout_seconds", 60),
        )
    summary = {
        "campaign_id": campaign_id,
        "mode": mode,
        "state": "running",
        "records": [],
        "skipped": skipped,
    }
    atomic_json(directory / "summary.json", summary)
    iterator = iter(candidates)
    optimizer_calls = 0

    def next_fallback():
        for value in iterator:
            try:
                key = Candidate.from_dict(value).candidate_id
            except Exception:
                return value
            if key not in seen:
                return value
            skipped.append({"reason": "duplicate_candidate", "candidate_id": key})
        return None

    for index in range(iterations):
        if len(history) >= iterations:
            reason = "iteration_limit"
            break
        remaining = budget - (time.monotonic() - start)
        if remaining <= 0:
            reason = "wall_budget"
            break
        proposal_metadata = {}
        selected_policy = "deterministic"
        candidate = None
        if optimizer is not None and optimizer_calls < optimizer_config["max_calls"]:
            optimizer_calls += 1
            optimizer.timeout = min(optimizer.timeout, remaining)
            try:
                candidate, proposal_metadata = optimizer.propose(history, seen)
                selected_policy = "gemini_cli"
            except Exception as error:
                skipped.append(
                    {
                        "reason": "optimizer_fallback",
                        "error": failure(error, "optimizer"),
                    }
                )
        if candidate is None:
            candidate = next_fallback()
        if candidate is None:
            reason = "candidate_list_exhausted"
            break
        remaining = budget - (time.monotonic() - start)
        if remaining <= 0:
            reason = "wall_budget"
            break
        try:
            key = Candidate.from_dict(candidate).candidate_id
        except Exception:
            key = None  # executor emits a sanitized rejected record without executing either node.
        if key in seen:
            skipped.append(
                {
                    "input_index": index,
                    "reason": "duplicate_candidate",
                    "candidate_id": key,
                }
            )
            continue
        if key:
            seen.add(key)
        bounded = {
            name: {
                **runtime[name],
                "timeout_seconds": min(runtime[name]["timeout_seconds"], remaining),
                "deadline_epoch_seconds": time.time() + remaining,
            }
            for name in ("software", "hardware")
        }
        bounded["graph_timeout_seconds"] = remaining
        record = run_experiment(
            candidate,
            runtime=bounded,
            dispatcher=dispatcher,
            results_root=results_root,
            campaign_id=campaign_id,
            iteration=len(history) + 1,
            policy=selected_policy,
            optimizer_metadata=proposal_metadata,
        )
        history.append(record)
        summary.update(
            records=[
                {
                    "run_id": r["run_id"],
                    "candidate_id": r["candidate_id"],
                    "status": r["status"],
                }
                for r in history
            ],
            pareto_candidate_ids=pareto(history),
        )
        atomic_json(directory / "summary.json", summary)
        if sum(r["status"] == "failed" for r in history[-3:]) == 3:
            reason = "repeated_runtime_failures"
            break
    if len(history) >= iterations and reason == "candidate_list_exhausted":
        reason = "iteration_limit"
    summary.update(
        state="completed"
        if all(r["status"] == "completed" for r in history) and history
        else "incomplete",
        stop_reason=reason,
        elapsed_seconds=time.monotonic() - start,
        optimizer_calls=optimizer_calls,
    )
    atomic_json(directory / "summary.json", summary)
    return {**summary, "experiments": history, "results_directory": str(directory)}
