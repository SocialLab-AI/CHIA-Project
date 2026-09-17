"""Analyze Qwen-to-gem5 proxy evidence; hardware owns proxy fidelity claims."""

from __future__ import annotations

import math
from xml.sax.saxutils import escape

import yaml

from src.common.candidate import ROOT
from src.common.errors import MetricsError


CONTEXT_LENGTHS = (128, 256, 512, 1024, 2048)


def load_proxy_profile() -> dict:
    """Return the implemented proxy shape and its explicit scope."""

    baseline = yaml.safe_load(
        (ROOT / "experiment-contracts/baselines/attention.yaml").read_text(
            encoding="utf-8"
        )
    )
    design = yaml.safe_load(
        (ROOT / "experiment-contracts/design-spaces/hardware.yaml").read_text(
            encoding="utf-8"
        )
    )
    workload = baseline["workload"]
    return {
        "implementation": baseline["software"]["implementation"],
        "query_heads": workload["query_heads"],
        "kv_heads": workload["kv_heads"],
        "head_dimension": workload["head_dimension"],
        "layers": workload["layers"],
        "maximum_tested_context": max(design["evaluation_axes"]["context_tokens"]),
        "kv_quantization": baseline["software"]["kv_format"],
        "weight_quantization": None,
        "hidden_size": None,
        "feed_forward_dimension": None,
        "includes": [
            "one query vector per query head",
            "packed-Q4 KV-cache dequantization",
            "QK dot products and scaled attention scores",
            "softmax normalization",
            "attention-weighted value accumulation",
            "two-thread execution and an FP32 numerical reference",
        ],
        "excludes": [
            "Q/K/V projection matrix multiplication",
            "feed-forward or MLP blocks",
            "repeated execution across all transformer layers",
            "embeddings and the language-model head",
            "tokenization and sampling",
            "llama.cpp graph, allocator and HTTP runtime overhead",
            "complete Qwen weight access behavior",
        ],
    }


def architecture_comparison(model: dict, proxy: dict | None = None) -> list[dict]:
    """Build the evidence table before any proxy dimensions are changed."""

    proxy = proxy or load_proxy_profile()
    fields = (
        ("Transformer layers", "layers", "layers"),
        ("Hidden size", "hidden_size", "hidden_size"),
        ("Query heads", "query_heads", "query_heads"),
        ("KV heads", "kv_heads", "kv_heads"),
        ("Head dimension", "head_dimension", "head_dimension"),
        ("FFN / intermediate dimension", "feed_forward_dimension", "feed_forward_dimension"),
        ("Maximum context", "maximum_context_length", "maximum_tested_context"),
        ("Weight quantization", "quantization", "weight_quantization"),
    )
    rows = []
    for label, model_key, proxy_key in fields:
        real = model.get(model_key)
        current = proxy.get(proxy_key)
        if current is None:
            match = "not_modeled"
            action = "Keep outside the proxy claim or add a reviewed component."
        elif real == current:
            match = "yes"
            action = "No structural change required."
        else:
            match = "no"
            if model_key == "layers":
                action = "Keep a representative layer and document omitted repetition."
            elif model_key == "maximum_context_length":
                action = "Treat tested contexts as an evaluation range, not the model limit."
            else:
                action = "Review and update the representative attention mapping."
        rows.append(
            {
                "parameter": label,
                "real_qwen": real,
                "current_proxy": current,
                "match": match,
                "action_needed": action,
            }
        )
    rows.append(
        {
            "parameter": "KV-cache quantization",
            "real_qwen": model.get("kv_cache_quantization", "runtime-dependent"),
            "current_proxy": proxy["kv_quantization"],
            "match": "unknown",
            "action_needed": "Record llama.cpp KV-cache types before claiming a match.",
        }
    )
    return rows


def _average_ranks(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    position = 0
    while position < len(indexed):
        end = position + 1
        while end < len(indexed) and indexed[end][1] == indexed[position][1]:
            end += 1
        average = ((position + 1) + end) / 2.0
        for original_index, _ in indexed[position:end]:
            ranks[original_index] = average
        position = end
    return ranks


def spearman_rank_correlation(left: list[float], right: list[float]) -> float:
    """Calculate Spearman rho with average ranks for ties."""

    if len(left) != len(right) or len(left) < 2:
        raise MetricsError("Spearman correlation requires equal vectors of length >= 2.")
    if any(not math.isfinite(value) for value in left + right):
        raise MetricsError("Spearman inputs must be finite.")
    x = _average_ranks(left)
    y = _average_ranks(right)
    x_mean = sum(x) / len(x)
    y_mean = sum(y) / len(y)
    numerator = sum((a - x_mean) * (b - y_mean) for a, b in zip(x, y))
    x_scale = math.sqrt(sum((a - x_mean) ** 2 for a in x))
    y_scale = math.sqrt(sum((b - y_mean) ** 2 for b in y))
    if x_scale == 0 or y_scale == 0:
        raise MetricsError("Spearman correlation is undefined for a constant vector.")
    return numerator / (x_scale * y_scale)


def _by_context(items: list[dict], value) -> tuple[list[int], list[float]]:
    ordered = sorted(items, key=lambda item: item["context_tokens"])
    contexts = [item["context_tokens"] for item in ordered]
    values = [float(value(item)) for item in ordered]
    if contexts != list(CONTEXT_LENGTHS):
        raise MetricsError("Proxy-fidelity evidence must cover 128, 256, 512, 1024 and 2048.")
    if any(not math.isfinite(item) or item <= 0 for item in values):
        raise MetricsError("Proxy-fidelity timing values must be finite and positive.")
    return contexts, values


def _normalize(values: list[float]) -> list[float]:
    return [value / values[0] for value in values]


def analyze_fidelity(model: dict, native: dict, hardware: dict) -> dict:
    """Combine measured evidence without claiming unavailable native cache rankings."""

    contexts, native_latency = _by_context(
        native["contexts"], lambda item: item["average_latency_ms"]
    )
    hardware_contexts, proxy_latency = _by_context(
        hardware["contexts"], lambda item: item["metrics"]["simulated_seconds"]
    )
    if contexts != hardware_contexts:
        raise MetricsError("Native and proxy context axes differ.")
    rho = spearman_rank_correlation(native_latency, proxy_latency)
    comparison = architecture_comparison(model)
    mismatches = sum(row["match"] == "no" for row in comparison)
    missing = sum(row["match"] in {"not_modeled", "unknown"} for row in comparison)
    sensitivity = sorted(
        hardware.get("sensitivity", []),
        key=lambda item: item["metrics"]["simulated_seconds"],
    )

    # A full calibration claim requires a native platform exposing equivalent
    # cache/memory configurations. Adam cannot change its physical L1/L2 design.
    conclusion = "C_PROXY_NEEDS_REVISION" if rho <= 0 else "B_PARTIAL_PROXY"
    return {
        "schema_version": "0.1.0",
        "contexts": contexts,
        "architecture_comparison": comparison,
        "architecture_mismatch_count": mismatches,
        "architecture_unknown_or_unmodeled_count": missing,
        "native_latency_ms": native_latency,
        "proxy_simulated_seconds": proxy_latency,
        "native_normalized_latency": _normalize(native_latency),
        "proxy_normalized_latency": _normalize(proxy_latency),
        "native_measurement_scope": native.get("measurement_scope", "not recorded"),
        "proxy_measurement_scope": hardware.get("measurement_scope", "not recorded"),
        "context_spearman_rho": rho,
        "proxy_hardware_ranking": [item["case_id"] for item in sensitivity],
        "native_hardware_ranking": None,
        "configuration_rank_correlation": None,
        "configuration_rank_limitation": (
            "The Adam host cannot expose gem5-equivalent L1/L2 sizes, associativity, "
            "issue width or memory controller settings. A native Qwen ranking over those "
            "configurations is therefore not identifiable on the current cluster."
        ),
        "conclusion": conclusion,
        "claim": (
            "The gem5 workload is an attention-kernel proxy. It is not a simulation "
            "of complete Qwen inference."
        ),
    }


def render_trend_svg(analysis: dict) -> str:
    """Render a dependency-free normalized trend plot for the evidence bundle."""

    width, height = 860, 480
    left, right, top, bottom = 80, 30, 45, 75
    plot_w = width - left - right
    plot_h = height - top - bottom
    contexts = analysis["contexts"]
    native = analysis["native_normalized_latency"]
    proxy = analysis["proxy_normalized_latency"]
    maximum = max(native + proxy) * 1.08
    if maximum <= 1:
        maximum = 1.1

    def x(index):
        return left + index * plot_w / (len(contexts) - 1)

    def y(value):
        return top + plot_h * (1 - value / maximum)

    def points(values):
        return " ".join(f"{x(i):.1f},{y(value):.1f}" for i, value in enumerate(values))

    grid = []
    for step in range(6):
        value = maximum * step / 5
        ypos = y(value)
        grid.append(
            f'<line x1="{left}" y1="{ypos:.1f}" x2="{width-right}" y2="{ypos:.1f}" '
            'stroke="#d8dee9" stroke-width="1"/>'
        )
        grid.append(
            f'<text x="{left-12}" y="{ypos+4:.1f}" text-anchor="end" '
            f'font-size="12">{value:.1f}x</text>'
        )
    labels = []
    for index, context in enumerate(contexts):
        labels.append(
            f'<text x="{x(index):.1f}" y="{height-bottom+28}" text-anchor="middle" '
            f'font-size="12">{context}</text>'
        )
    circles = []
    for values, color in ((native, "#1565c0"), (proxy, "#ef6c00")):
        for index, value in enumerate(values):
            circles.append(
                f'<circle cx="{x(index):.1f}" cy="{y(value):.1f}" r="5" fill="{color}"/>'
            )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
        '<rect width="100%" height="100%" fill="white"/>'
        '<text x="430" y="25" text-anchor="middle" font-size="18" font-weight="bold">'
        'Normalized context-length scaling (128 tokens = 1.0x)</text>'
        + "".join(grid)
        + f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height-bottom}" stroke="#263238"/>'
        + f'<line x1="{left}" y1="{height-bottom}" x2="{width-right}" y2="{height-bottom}" stroke="#263238"/>'
        + "".join(labels)
        + f'<polyline points="{points(native)}" fill="none" stroke="#1565c0" stroke-width="3"/>'
        + f'<polyline points="{points(proxy)}" fill="none" stroke="#ef6c00" stroke-width="3"/>'
        + "".join(circles)
        + '<text x="430" y="455" text-anchor="middle" font-size="13">Context tokens</text>'
        + '<rect x="575" y="48" width="16" height="4" fill="#1565c0"/>'
        + '<text x="598" y="56" font-size="12">Native Qwen prompt processing</text>'
        + '<rect x="575" y="70" width="16" height="4" fill="#ef6c00"/>'
        + '<text x="598" y="78" font-size="12">gem5 attention proxy</text>'
        + '</svg>\n'
    )


def _cell(value) -> str:
    if value is None:
        return "not modeled"
    return str(value).replace("|", "\\|")


def render_report(analysis: dict, model: dict, proxy: dict | None = None) -> str:
    """Produce the concise Issue #60 evidence report from measured artifacts."""

    proxy = proxy or load_proxy_profile()
    lines = [
        "# Qwen–gem5 proxy fidelity report",
        "",
        "## Architecture comparison",
        "",
        "| Parameter | Real Qwen | Current proxy | Match? | Action needed |",
        "|---|---:|---:|---|---|",
    ]
    for row in analysis["architecture_comparison"]:
        lines.append(
            "| " + " | ".join(
                _cell(row[key])
                for key in ("parameter", "real_qwen", "current_proxy", "match", "action_needed")
            ) + " |"
        )
    lines += ["", "## Proxy scope", "", "Included:"]
    lines += [f"- {item}" for item in proxy["includes"]]
    lines += ["", "Excluded:"]
    lines += [f"- {item}" for item in proxy["excludes"]]
    lines += [
        "",
        "## Context-length evidence",
        "",
        "| Context | Qwen latency (ms) | Qwen normalized | gem5 seconds | gem5 normalized |",
        "|---:|---:|---:|---:|---:|",
    ]
    for index, context in enumerate(analysis["contexts"]):
        lines.append(
            f"| {context} | {analysis['native_latency_ms'][index]:.3f} | "
            f"{analysis['native_normalized_latency'][index]:.3f}x | "
            f"{analysis['proxy_simulated_seconds'][index]:.6f} | "
            f"{analysis['proxy_normalized_latency'][index]:.3f}x |"
        )
    lines += [
        "",
        f"Spearman context-rank correlation: **{analysis['context_spearman_rho']:.4f}**.",
        "",
        "![Normalized Qwen and proxy trends](normalized-context-trends.svg)",
        "",
        "## Hardware-configuration sensitivity",
        "",
        "gem5 ranking (fastest first): "
        + (", ".join(analysis["proxy_hardware_ranking"]) or "no completed cases"),
        "",
        "Native configuration ranking: **unavailable on the current cluster**.",
        "",
        analysis["configuration_rank_limitation"],
        "",
        "## Conclusion",
        "",
        f"**{analysis['conclusion']}**",
        "",
        analysis["claim"],
        "",
        "## Evidence classification",
        "",
        "**FACT:** Model dimensions come from the SHA-verified GGUF header. Native and "
        "gem5 values in this report come from the retained sweep artifacts.",
        "",
        "**INTERPRETATION:** The context Spearman value describes ordering agreement "
        "between different workload scopes; it does not establish full-model cycle accuracy.",
        "",
        "**UNKNOWN:** Native-versus-gem5 hardware-configuration rank preservation is "
        "not identifiable on the current cluster.",
        "",
        "**IDEA:** After the original mismatch evidence is reviewed, update only the "
        "attention dimensions that the proxy actually models and repeat this protocol.",
        "",
        "A full calibrated-proxy claim requires equivalent native hardware configurations "
        "or another defensible validation method. Until then, optimization claims must be "
        "limited to the attention kernel and reported separately from native Qwen metrics.",
        "",
        "## Provenance",
        "",
        f"- Model architecture: `{escape(str(model.get('architecture')))}`",
        f"- GGUF SHA-256: `{escape(str(model.get('model_sha256')))}`",
        f"- Quantization: `{escape(str(model.get('quantization')))}`",
        f"- Native scope: {escape(str(analysis['native_measurement_scope']))}",
        f"- gem5 scope: {escape(str(analysis['proxy_measurement_scope']))}",
    ]
    return "\n".join(lines) + "\n"
