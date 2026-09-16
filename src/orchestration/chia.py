"""Canonical bounded campaign controller."""

import copy
from pathlib import Path
import time

import yaml

from src.common.candidate import ROOT, Candidate
from src.common.errors import ConfigError, failure
from src.common.logging import utc_now
from src.common.records import atomic_json
from src.common.security import finite_number, local_endpoint, safe_id
from src.orchestration.dispatch import ChiaDispatcher, LocalDispatcher
from src.orchestration.experiment import run_experiment
from src.orchestration.policies import deterministic_candidates, pareto


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
        },
        "hardware": {
            "image",
            "timeout_seconds",
            "retries",
            "correctness_tolerance",
            "artifacts_root",
        },
    }

    for name, default_timeout in (
        ("software", 120),
        ("hardware", 600),
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
        if not policy["tiers"][tier]["gemini_allowed"]:
            raise ConfigError(
                "This compute tier forbids Gemini calls."
            )

        if optimizer.get("policy") != "gemini_api":
            raise ConfigError(
                "Enabled optimizer policy must be gemini_api."
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

    if dispatcher is None:
        if mode == "chia":
            dispatcher = ChiaDispatcher(
                config.get("ray_address", "auto")
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

    if optimizer_config.get("enabled", False):
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

    optimizer_events = []
    optimizer_failures = 0
    optimizer_calls = 0

    gemini_usage_total = {
        "input_tokens": 0,
        "candidate_tokens": 0,
        "thought_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "estimated_cost_usd": 0.0,
    }

    optimizer_budget = (
        optimizer_config.get("budget_usd")
        if optimizer is not None
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
            and gemini_usage_total["estimated_cost_usd"]
            < optimizer_budget
        )

        if optimizer_is_available:
            optimizer_calls += 1

            optimizer.timeout_seconds = min(
                optimizer.timeout_seconds,
                remaining,
            )

            try:
                candidate, proposal_metadata = (
                    optimizer.propose(
                        history,
                        seen,
                    )
                )

                usage = proposal_metadata["usage"]

                for name in (
                    "input_tokens",
                    "candidate_tokens",
                    "thought_tokens",
                    "output_tokens",
                    "total_tokens",
                ):
                    gemini_usage_total[name] += usage[name]

                proposal_cost = proposal_metadata[
                    "estimated_cost_usd"
                ]

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
                    gemini_usage_total[
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
                else:
                    selected_policy = "gemini_api"

                optimizer_events.append(optimizer_event)

            except Exception as error:
                optimizer_failures += 1

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
                    usage = failed_metadata["usage"]

                    for name in (
                        "input_tokens",
                        "candidate_tokens",
                        "thought_tokens",
                        "output_tokens",
                        "total_tokens",
                    ):
                        gemini_usage_total[name] += usage[name]

                    gemini_usage_total[
                        "estimated_cost_usd"
                    ] += failed_metadata[
                        "estimated_cost_usd"
                    ]

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
                    optimizer_budget
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
            for name in ("software", "hardware")
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
            for item in history[-3:]
        )

        if recent_failures == 3:
            stop_reason = "repeated_runtime_failures"
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

    return {
        **summary,
        "experiments": history,
        "results_directory": str(campaign_directory),
    }
