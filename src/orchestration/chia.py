"""Canonical bounded campaign controller."""

import copy
import hashlib
import json
import os
import platform
from pathlib import Path
import re
import time

import yaml

from src.common.candidate import ROOT, Candidate
from src.common.errors import ConfigError, failure
from src.common.logging import utc_now
from src.common.records import atomic_json, atomic_text, provenance
from src.common.security import canonical, finite_number, local_endpoint, safe_id
from src.orchestration.dispatch import ChiaDispatcher, LocalDispatcher
from src.orchestration.experiment import run_experiment
from src.orchestration.policies import deterministic_candidates, pareto


def ray_worker_environment(runtime):
    """Return only operator-approved environment values needed by Ray tasks."""
    permission_name = runtime.get(
        "software", {}
    ).get("dataset_permission_env")
    if not permission_name:
        return {}
    permission_value = os.getenv(permission_name)
    return {permission_name: "1"} if permission_value == "1" else {}


def validate_campaign_config(value=None):
    """Validate campaign settings without starting Ray or either runtime."""

    if value is None:
        value = {}

    if not isinstance(value, dict):
        raise ConfigError("Campaign configuration must be a YAML object.")

    allowed = {
        "campaign_id",
        "mode",
        "tier",
        "backend",
        "iterations",
        "wall_budget_seconds",
        "runtime",
        "results_root",
        "ray_address",
        "candidates",
        "optimizer",
        "study",
        "stopping",
    }

    unknown = set(value) - allowed

    if unknown:
        raise ConfigError(
            f"Unknown campaign field: {sorted(unknown)[0]}."
        )

    config = copy.deepcopy(value)

    campaign_id = safe_id(
        config.get("campaign_id", "deterministic-local")
    )
    config["campaign_id"] = campaign_id

    iterations = config.get("iterations", 3)

    if (
        isinstance(iterations, bool)
        or not isinstance(iterations, int)
        or not 1 <= iterations <= 100
    ):
        raise ConfigError(
            "iterations must be at least 1 and no more than 100."
        )

    config["iterations"] = iterations

    wall_budget = finite_number(
        config.get("wall_budget_seconds", 1800),
        "wall_budget_seconds",
        positive=True,
    )
    config["wall_budget_seconds"] = wall_budget

    runtime = config.get("runtime", {})

    if not isinstance(runtime, dict):
        raise ConfigError(
            "runtime must be a YAML object with software and "
            "hardware sections."
        )

    config["runtime"] = runtime

    policy_path = (
        ROOT
        / "experiment-contracts"
        / "policies"
        / "compute-policy.yaml"
    )

    policy = yaml.safe_load(
        policy_path.read_text(encoding="utf-8")
    )

    tier = config.get("tier", "dev")
    backend = config.get("backend", "local")

    if tier not in policy["tiers"]:
        raise ConfigError(f"Unknown compute tier: {tier}.")

    if backend not in policy["tiers"][tier]["backends"]:
        raise ConfigError(
            "Execution backend is not allowed in this compute tier."
        )

    mode = config.get("mode", "local")

    if mode not in {"local", "chia"}:
        raise ConfigError("Unknown execution mode.")

    if (
        mode == "chia"
        and policy["tiers"][tier]["max_parallel_jobs"] < 2
    ):
        raise ConfigError(
            "This tier does not allow both runtime nodes concurrently."
        )

    config["tier"] = tier
    config["backend"] = backend
    config["mode"] = mode

    permitted_runtime_fields = {
        "software": {
            "endpoint",
            "timeout_seconds",
            "retries",
            "assets_root",
            "gguf",
            "model_sha256",
            "context_tokens",
            "parallel_slots",
            "candidate_timeout_seconds",
            "request_timeout_seconds",
            "request_retries",
            "request_retry_delay_seconds",
            "dataset_permission_env",
        },
        "hardware": {
            "image",
            "timeout_seconds",
            "retries",
            "correctness_tolerance",
            "artifacts_root",
        },
        "energy": {
            "image",
            "timeout_seconds",
            "retries",
            "artifacts_root",
        },
    }

    for name, default_timeout in (
        ("software", 120),
        ("hardware", 600),
        ("energy", 300),
    ):
        runtime.setdefault(name, {})

        if not isinstance(runtime[name], dict):
            raise ConfigError(
                f"runtime.{name} must be a YAML object."
            )

        extra = (
            set(runtime[name])
            - permitted_runtime_fields[name]
        )

        if extra:
            raise ConfigError(
                f"Unknown runtime.{name} field: "
                f"{sorted(extra)[0]}."
            )

        runtime[name].setdefault(
            "timeout_seconds",
            default_timeout,
        )
        runtime[name].setdefault("retries", 0)

        finite_number(
            runtime[name]["timeout_seconds"],
            f"{name} timeout",
            positive=True,
        )

        retries = runtime[name]["retries"]

        if (
            type(retries) is not int
            or not 0 <= retries <= 2
        ):
            raise ConfigError(
                "Transient retries must be an integer "
                "between zero and two."
            )

    endpoint = runtime["software"].get(
        "endpoint",
        "http://127.0.0.1:8081",
    )
    runtime["software"]["endpoint"] = local_endpoint(endpoint)

    supplied_software_runtime = value.get("runtime", {}).get("software", {})
    if supplied_software_runtime:
        for field in ("assets_root", "gguf", "model_sha256"):
            item = runtime["software"].get(field)
            if not isinstance(item, str) or not item.strip():
                raise ConfigError(f"runtime.software.{field} must be nonempty text.")
        for field in ("context_tokens", "parallel_slots"):
            item = runtime["software"].get(field)
            if type(item) is not int or item < 1:
                raise ConfigError(
                    f"runtime.software.{field} must be a positive integer."
                )

        for field in (
            "candidate_timeout_seconds",
            "request_timeout_seconds",
        ):
            if field in runtime["software"]:
                finite_number(
                    runtime["software"][field],
                    f"runtime.software.{field}",
                    positive=True,
                )

        if "request_retry_delay_seconds" in runtime["software"]:
            finite_number(
                runtime["software"]["request_retry_delay_seconds"],
                "runtime.software.request_retry_delay_seconds",
            )

        if "request_retries" in runtime["software"]:
            request_retries = runtime["software"]["request_retries"]
            if (
                type(request_retries) is not int
                or not 0 <= request_retries <= 2
            ):
                raise ConfigError(
                    "runtime.software.request_retries must be an integer "
                    "between zero and two."
                )

        permission_env = runtime["software"].get("dataset_permission_env")
        if permission_env is not None and (
            not isinstance(permission_env, str)
            or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", permission_env) is None
        ):
            raise ConfigError(
                "runtime.software.dataset_permission_env must be "
                "a valid environment variable name."
            )

    if "hardware" in value.get("runtime", {}):
        tolerance = runtime["hardware"].get(
            "correctness_tolerance"
        )

        required_tolerances = {
            "max_absolute_error",
            "mean_squared_error",
        }

        if (
            not isinstance(tolerance, dict)
            or set(tolerance) != required_tolerances
        ):
            raise ConfigError(
                "runtime.hardware.correctness_tolerance requires "
                "exactly max_absolute_error and mean_squared_error."
            )

        for name, limit in tolerance.items():
            finite_number(limit, name)

            if limit < 0:
                raise ConfigError(
                    f"{name} must be nonnegative."
                )

    candidates = config.get(
        "candidates",
        deterministic_candidates(),
    )

    if not isinstance(candidates, list) or not candidates:
        raise ConfigError(
            "candidates must be a nonempty list."
        )

    for candidate in candidates:
        Candidate.from_dict(candidate)

    stopping = config.get("stopping", {})
    if not isinstance(stopping, dict):
        raise ConfigError("stopping must be a YAML object.")
    allowed_stopping = {
        "max_evaluated_candidates", "max_campaign_wall_seconds",
        "max_consecutive_proposal_failures", "max_infrastructure_failures",
        "no_improvement_patience", "duplicate_policy",
    }
    if set(stopping) - allowed_stopping:
        raise ConfigError("Unknown stopping field.")
    stopping.setdefault("max_evaluated_candidates", iterations)
    stopping.setdefault("max_campaign_wall_seconds", wall_budget)
    stopping.setdefault("max_consecutive_proposal_failures", 3)
    stopping.setdefault("max_infrastructure_failures", 3)
    stopping.setdefault("no_improvement_patience", None)
    stopping.setdefault("duplicate_policy", "reject_without_evaluation")
    for field in ("max_evaluated_candidates", "max_consecutive_proposal_failures", "max_infrastructure_failures"):
        if type(stopping[field]) is not int or stopping[field] < 1:
            raise ConfigError(f"stopping.{field} must be a positive integer.")
    if stopping["max_evaluated_candidates"] != iterations:
        raise ConfigError("iterations must equal stopping.max_evaluated_candidates.")
    if stopping["max_campaign_wall_seconds"] != wall_budget:
        raise ConfigError("wall_budget_seconds must equal stopping.max_campaign_wall_seconds.")
    if stopping["duplicate_policy"] != "reject_without_evaluation":
        raise ConfigError("Unsupported duplicate policy.")
    config["stopping"] = stopping

    optimizer = config.get("optimizer", {})

    if not isinstance(optimizer, dict):
        raise ConfigError("optimizer must be a YAML object.")

    permitted_optimizer_fields = {
        "enabled",
        "policy",
        "model",
        "max_calls",
        "budget_usd",
        "timeout_seconds",
        "seed",
    }

    extra_optimizer_fields = (
        set(optimizer) - permitted_optimizer_fields
    )

    if extra_optimizer_fields:
        raise ConfigError(
            "Unknown optimizer field: "
            f"{sorted(extra_optimizer_fields)[0]}."
        )

    optimizer.setdefault("enabled", False)

    if not isinstance(optimizer["enabled"], bool):
        raise ConfigError(
            "optimizer.enabled must be boolean."
        )

    if optimizer["enabled"]:
        optimizer_policy = optimizer.get("policy")
        if optimizer_policy not in {"gemini_api", "random"}:
            raise ConfigError("Enabled optimizer policy must be gemini_api or random.")
        if optimizer_policy == "gemini_api" and not policy["tiers"][tier]["gemini_allowed"]:
            raise ConfigError(
                "This compute tier forbids Gemini calls."
            )

        max_calls = optimizer.get("max_calls")

        if (
            type(max_calls) is not int
            or not 1 <= max_calls <= iterations
        ):
            raise ConfigError(
                "optimizer.max_calls must be bounded "
                "by iteration count."
            )

        if optimizer_policy == "random":
            seed = optimizer.get("seed", 20260921)
            if type(seed) is not int:
                raise ConfigError("optimizer.seed must be an integer.")
            optimizer["seed"] = seed
            config["optimizer"] = optimizer
            return config

        model = optimizer.get("model")
        pricing = (
            policy["gemini"]
            .get("models", {})
            .get(model)
        )

        expected_pricing_fields = {
            "input_usd_per_million_tokens",
            "output_usd_per_million_tokens",
        }

        if (
            not isinstance(pricing, dict)
            or set(pricing) != expected_pricing_fields
        ):
            raise ConfigError(
                "Optimizer model has no reviewed pricing policy."
            )

        for name, rate in pricing.items():
            finite_number(
                rate,
                f"Gemini pricing {name}",
            )

        optimizer_budget = finite_number(
            optimizer.get("budget_usd"),
            "optimizer.budget_usd",
            positive=True,
        )

        if optimizer_budget > policy["gemini"]["budget_usd"]:
            raise ConfigError(
                "Optimizer campaign budget exceeds project policy."
            )

        optimizer["timeout_seconds"] = finite_number(
            optimizer.get("timeout_seconds", 60),
            "optimizer.timeout_seconds",
            positive=True,
        )

    config["optimizer"] = optimizer

    for name in ("results_root", "ray_address"):
        if name in config and not isinstance(
            config[name],
            str,
        ):
            raise ConfigError(
                f"{name} must be a string."
            )

    return config


def chia_entrypoint(config=None, *, dispatcher=None):
    """Run a bounded hardware/software optimization campaign."""

    config = validate_campaign_config(config)

    campaign_id = config["campaign_id"]
    iterations = config["iterations"]
    wall_budget = config["wall_budget_seconds"]
    runtime = config["runtime"]
    stopping = config["stopping"]
    tier = config["tier"]
    backend = config["backend"]
    mode = config["mode"]

    policy_path = (
        ROOT
        / "experiment-contracts"
        / "policies"
        / "compute-policy.yaml"
    )

    policy = yaml.safe_load(
        policy_path.read_text(encoding="utf-8")
    )

    results_root = Path(
        config.get(
            "results_root",
            ROOT / "results/full-loop",
        )
    ).resolve()

    campaign_directory = results_root / campaign_id
    campaign_directory.mkdir(
        parents=True,
        exist_ok=False,
    )
    atomic_text(campaign_directory / "campaign.yaml", yaml.safe_dump(config, sort_keys=False))
    atomic_json(campaign_directory / "environment.json", {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "machine_role": "CHIA head node",
    })
    campaign_provenance = provenance()
    campaign_provenance.update({
        "campaign_config_sha256": hashlib.sha256(canonical(config).encode()).hexdigest(),
        "design_space_sha256": hashlib.sha256(
            (ROOT / "experiment-contracts/design-spaces/software.yaml").read_bytes()
            + (ROOT / "experiment-contracts/design-spaces/hardware.yaml").read_bytes()
        ).hexdigest(),
        "dataset_sha256": hashlib.sha256((ROOT / "data/questions/questions.json").read_bytes()).hexdigest(),
        "model_sha256": runtime.get("software", {}).get("model_sha256"),
    })
    atomic_json(campaign_directory / "provenance.json", campaign_provenance)

    if dispatcher is None:
        if mode == "chia":
            dispatcher = ChiaDispatcher(
                config.get("ray_address", "auto"),
                env_vars=ray_worker_environment(runtime),
            )
        else:
            dispatcher = LocalDispatcher()

    history = []
    seen = set()
    skipped = []

    campaign_start = time.monotonic()
    stop_reason = "candidate_list_exhausted"

    candidates = config.get(
        "candidates",
        deterministic_candidates(),
    )
    candidate_iterator = iter(candidates)

    optimizer_config = config.get("optimizer", {})
    optimizer = None

    if optimizer_config.get("enabled", False) and optimizer_config["policy"] == "gemini_api":
        from src.orchestration.gemini_api import (
            GeminiAPIOptimizer,
        )

        pricing = policy["gemini"]["models"][
            optimizer_config["model"]
        ]

        optimizer = GeminiAPIOptimizer(
            model=optimizer_config["model"],
            pricing=pricing,
            timeout_seconds=optimizer_config[
                "timeout_seconds"
            ],
        )
    elif optimizer_config.get("enabled", False):
        from src.orchestration.random_search import RandomProposer
        optimizer = RandomProposer(seed=optimizer_config["seed"])

    optimizer_events = []
    optimizer_failures = 0
    optimizer_calls = 0

    gemini_usage_total = {
        "request_count": 0,
        "accepted_proposals": 0,
        "rejected_proposals": 0,
        "duplicates": 0,
        "malformed_responses": 0,
        "retry_count": 0,
        "fallback_count": 0,
        "unmetered_request_failures": 0,
        "input_tokens": 0,
        "candidate_tokens": 0,
        "thought_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "estimated_cost_usd": 0.0,
    }

    optimizer_budget = (
        optimizer_config.get("budget_usd")
        if optimizer is not None and optimizer_config["policy"] == "gemini_api"
        else None
    )

    summary = {
        "campaign_id": campaign_id,
        "mode": mode,
        "tier": tier,
        "backend": backend,
        "state": "running",
        "started_at": utc_now(),
        "ended_at": None,
        "records": [],
        "skipped": skipped,
        "optimizer_events": optimizer_events,
        "optimizer_calls": optimizer_calls,
        "optimizer_failures": optimizer_failures,
        "gemini_usage_total": gemini_usage_total,
        "optimizer_budget_usd": optimizer_budget,
        "optimizer_budget_remaining_usd": optimizer_budget,
    }

    atomic_json(
        campaign_directory / "summary.json",
        summary,
    )
    def next_fallback_candidate():
        for value in candidate_iterator:
            try:
                candidate_id = Candidate.from_dict(
                    value
                ).candidate_id
            except Exception:
                return value

            if candidate_id not in seen:
                return value

            skipped.append(
                {
                    "reason": "duplicate_candidate",
                    "candidate_id": candidate_id,
                }
            )

        return None

    for input_index in range(iterations):
        if optimizer_failures >= stopping["max_consecutive_proposal_failures"]:
            stop_reason = "proposal_failure_limit"
            break
        if len(history) >= iterations:
            stop_reason = "iteration_limit"
            break

        elapsed = time.monotonic() - campaign_start
        remaining = wall_budget - elapsed

        if remaining <= 0:
            stop_reason = "wall_budget"
            break

        proposal_metadata = {}
        selected_policy = "deterministic"
        candidate = None

        optimizer_is_available = (
            optimizer is not None
            and optimizer_calls
            < optimizer_config["max_calls"]
            and (
                optimizer_budget is None
                or gemini_usage_total["estimated_cost_usd"] < optimizer_budget
            )
        )

        if optimizer_is_available:
            optimizer_calls += 1

            if hasattr(optimizer, "timeout_seconds"):
                optimizer.timeout_seconds = min(optimizer.timeout_seconds, remaining)

            try:
                candidate, proposal_metadata = (
                    optimizer.propose(
                        history,
                        seen,
                    )
                )

                usage = proposal_metadata.get("usage")

                if usage:
                    gemini_usage_total["request_count"] += 1

                for name in (
                    "input_tokens",
                    "candidate_tokens",
                    "thought_tokens",
                    "output_tokens",
                    "total_tokens",
                ):
                    if usage:
                        gemini_usage_total[name] += usage[name]

                proposal_cost = proposal_metadata.get("estimated_cost_usd", 0.0)

                gemini_usage_total[
                    "estimated_cost_usd"
                ] += proposal_cost

                proposed_id = Candidate.from_dict(
                    candidate
                ).candidate_id

                optimizer_event = {
                    "call": optimizer_calls,
                    "status": "accepted",
                    "candidate_id": proposed_id,
                    **proposal_metadata,
                }

                if (
                    optimizer_budget is not None and gemini_usage_total[
                        "estimated_cost_usd"
                    ]
                    > optimizer_budget
                ):
                    optimizer_event["status"] = (
                        "budget_exceeded_after_call"
                    )

                    skipped.append(
                        {
                            "reason":
                                "optimizer_budget_exceeded",
                            "candidate_id": proposed_id,
                        }
                    )

                    candidate = None
                    proposal_metadata = {}
                    if usage:
                        gemini_usage_total["rejected_proposals"] += 1
                else:
                    selected_policy = optimizer_config["policy"]
                    if usage:
                        gemini_usage_total["accepted_proposals"] += 1

                optimizer_events.append(optimizer_event)

            except Exception as error:
                optimizer_failures += 1
                gemini_usage_total["fallback_count"] += 1

                controlled_error = failure(
                    error,
                    "optimizer",
                )

                failed_metadata = getattr(
                    error,
                    "optimizer_metadata",
                    None,
                )

                if isinstance(failed_metadata, dict):
                    gemini_usage_total["request_count"] += 1
                    outcome = failed_metadata.get("outcome", "rejected")
                    gemini_usage_total["rejected_proposals"] += 1
                    if outcome == "duplicate":
                        gemini_usage_total["duplicates"] += 1
                    if outcome == "malformed":
                        gemini_usage_total["malformed_responses"] += 1
                    usage = failed_metadata.get("usage")

                    if usage:
                        for name in (
                            "input_tokens",
                            "candidate_tokens",
                            "thought_tokens",
                            "output_tokens",
                            "total_tokens",
                        ):
                            gemini_usage_total[name] += usage[name]
                    else:
                        gemini_usage_total["unmetered_request_failures"] += 1

                    failed_cost = failed_metadata.get("estimated_cost_usd")
                    if isinstance(failed_cost, (int, float)) and not isinstance(failed_cost, bool):
                        gemini_usage_total["estimated_cost_usd"] += failed_cost

                skipped.append(
                    {
                        "reason": "optimizer_fallback",
                        "error": controlled_error,
                    }
                )

                optimizer_events.append(
                    {
                        "call": optimizer_calls,
                        "status": "failed",
                        "error": controlled_error,
                        **(failed_metadata or {}),
                    }
                )

            summary.update(
                optimizer_calls=optimizer_calls,
                optimizer_failures=optimizer_failures,
                optimizer_budget_remaining_usd=max(
                    0.0,
                    (optimizer_budget or 0.0)
                    - gemini_usage_total[
                        "estimated_cost_usd"
                    ],
                ),
            )

            atomic_json(
                campaign_directory / "summary.json",
                summary,
            )

        if candidate is None:
            candidate = next_fallback_candidate()

        if candidate is None:
            stop_reason = "candidate_list_exhausted"
            break

        elapsed = time.monotonic() - campaign_start
        remaining = wall_budget - elapsed

        if remaining <= 0:
            stop_reason = "wall_budget"
            break

        try:
            candidate_id = Candidate.from_dict(
                candidate
            ).candidate_id
        except Exception:
            candidate_id = None

        if candidate_id in seen:
            skipped.append(
                {
                    "input_index": input_index,
                    "reason": "duplicate_candidate",
                    "candidate_id": candidate_id,
                }
            )
            continue

        if candidate_id:
            seen.add(candidate_id)

        bounded_runtime = {
            name: {
                **runtime[name],
                "timeout_seconds": min(
                    runtime[name]["timeout_seconds"],
                    remaining,
                ),
                "deadline_epoch_seconds": (
                    time.time() + remaining
                ),
            }
            for name in ("software", "hardware", "energy")
        }

        bounded_runtime["graph_timeout_seconds"] = remaining

        record = run_experiment(
            candidate,
            runtime=bounded_runtime,
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
                    "run_id": item["run_id"],
                    "candidate_id": item["candidate_id"],
                    "status": item["status"],
                }
                for item in history
            ],
            pareto_candidate_ids=pareto(history),
        )

        atomic_json(
            campaign_directory / "summary.json",
            summary,
        )

        recent_failures = sum(
            item["status"] == "failed"
            for item in history[-stopping["max_infrastructure_failures"]:]
        )

        if recent_failures == stopping["max_infrastructure_failures"]:
            stop_reason = "infrastructure_failure_limit"
            break

    if (
        len(history) >= iterations
        and stop_reason == "candidate_list_exhausted"
    ):
        stop_reason = "iteration_limit"

    completed = (
        bool(history)
        and all(
            item["status"] == "completed"
            for item in history
        )
    )

    summary.update(
        state="completed" if completed else "incomplete",
        ended_at=utc_now(),
        stop_reason=stop_reason,
        elapsed_seconds=(
            time.monotonic() - campaign_start
        ),
        optimizer_calls=optimizer_calls,
        optimizer_failures=optimizer_failures,
        optimizer_budget_remaining_usd=(
            None
            if optimizer_budget is None
            else max(
                0.0,
                optimizer_budget
                - gemini_usage_total[
                    "estimated_cost_usd"
                ],
            )
        ),
    )

    atomic_json(
        campaign_directory / "summary.json",
        summary,
    )

    frontier_ids = pareto(history)
    atomic_json(campaign_directory / "pareto.json", {
        "candidate_ids": frontier_ids,
        "records": [
            {"run_id": item["run_id"], "candidate_id": item["candidate_id"], "objectives": item["evaluation"]["objectives"]}
            for item in history if item["candidate_id"] in frontier_ids and item["evaluation"]
        ],
    })
    all_events = [event for item in history for event in item["events"]]
    atomic_text(campaign_directory / "events.jsonl", "".join(canonical(event) + "\n" for event in all_events))
    if optimizer_config.get("policy") == "gemini_api":
        atomic_json(campaign_directory / "gemini/usage.json", gemini_usage_total)
        atomic_text(campaign_directory / "gemini/proposals.jsonl", "".join(canonical(event) + "\n" for event in optimizer_events))
    elif optimizer_config.get("policy") == "random":
        atomic_json(campaign_directory / "random/metadata.json", {"seed": optimizer_config["seed"], "proposals": optimizer_events})
    manifest_lines = []
    for artifact in sorted(path for path in campaign_directory.rglob("*") if path.is_file() and path.name != "MANIFEST.sha256"):
        manifest_lines.append(f"{hashlib.sha256(artifact.read_bytes()).hexdigest()}  {artifact.relative_to(campaign_directory).as_posix()}")
    atomic_text(campaign_directory / "MANIFEST.sha256", "\n".join(manifest_lines) + "\n")

    return {
        **summary,
        "experiments": history,
        "results_directory": str(campaign_directory),
    }
