# CHIA Multi-Objective Function

## 1. Purpose

CHIA evaluates each candidate configuration through two evaluation pipelines:

1. The native tutor pipeline, which produces an `answer_quality` metric.
2. The gem5 pipeline, which produces hardware-performance metrics, with `latency_ms` used as the primary optimization metric.

The purpose of this objective layer is to define how these metrics are interpreted together when CHIA compares candidate configurations.

This document defines the optimization semantics only. It does not define software search ranges, quantization candidates, metric implementations, runtime adapters, or the complete HW/SW search space.

---

## 2. Candidate Configuration

Let a candidate configuration be:

$$
x = (x_{sw}, x_{hw})
$$

where:

- \(x_{sw}\) represents the software configuration;
- \(x_{hw}\) represents the hardware configuration.

Each candidate must be evaluated as one complete HW/SW configuration.

Quantization belongs to the software configuration, but it is treated as a cross-layer variable because changing quantization can affect both model quality and the computational behavior observed by gem5.

---

## 3. Objective Metrics

For each candidate configuration \(x\), CHIA receives two primary objective values.

### Answer quality

$$
Q(x) = \text{answer\_quality}
$$

This value is produced by the native tutor evaluation pipeline.

The optimization direction is:

$$
\boxed{\max Q(x)}
$$

### Hardware performance

$$
L(x) = \text{latency\_ms}
$$

This value is produced by, or derived from, the gem5 evaluation pipeline.

The optimization direction is:

$$
\boxed{\min L(x)}
$$

Therefore, the multi-objective problem is:

$$
\boxed{\max Q(x), \qquad \min L(x)}
$$

The goal is to identify configurations that provide the best trade-offs between answer quality and execution latency.

For an optimization framework that represents all objectives using minimization, the equivalent objective vector is:

$$
F(x) =
\begin{bmatrix}
-Q(x) \\
L(x)
\end{bmatrix}
$$

---

## 4. Candidate Comparison

Candidate configurations are compared using Pareto dominance.

For two candidates \(x_a\) and \(x_b\), candidate \(x_a\) dominates candidate \(x_b\) when:

$$
Q(x_a) \ge Q(x_b)
$$

and:

$$
L(x_a) \le L(x_b)
$$

with at least one of the two inequalities being strict.

In practical terms, \(x_a\) dominates \(x_b\) if it provides:

- better answer quality without worse latency;
- lower latency without worse answer quality; or
- improvements in both metrics.

For example:

| Candidate | Answer Quality | Latency |
|---|---:|---:|
| A | 0.85 | 80 ms |
| B | 0.82 | 95 ms |

Candidate A dominates candidate B because A has both higher quality and lower latency.

However:

| Candidate | Answer Quality | Latency |
|---|---:|---:|
| A | 0.88 | 100 ms |
| B | 0.84 | 70 ms |

Neither candidate dominates the other.

Candidate A provides better quality, while candidate B provides better latency.

Both therefore represent valid quality-performance trade-offs.

Under this objective definition, non-dominated candidates form the Pareto frontier used to represent the quality-latency trade-off.

At this stage, no fixed weighted sum such as:

$$
\alpha Q(x) - \beta L(x)
$$

is defined.

Using Pareto dominance avoids introducing arbitrary weights between metrics that have different units and meanings.

---

## 5. Quantization as a Cross-Layer Variable

Quantization must be treated as a cross-layer design variable.

Let:

$$
q = \text{quantization configuration}
$$

Changing \(q\) can affect the native tutor result:

$$
q \rightarrow Q(x)
$$

because quantization may change model behavior and therefore answer quality.

The same quantization choice can also modify the workload executed by the hardware:

$$
q
\rightarrow
\text{compute profile}
\rightarrow
\text{gem5}
\rightarrow
L(x)
$$

Therefore, quantization affects both sides of the objective:

$$
q
\rightarrow
\begin{cases}
Q(x) \\
L(x)
\end{cases}
$$

This coupling is important because the quality result and hardware-performance result must describe the same candidate configuration.

When quantization becomes part of the active CHIA search space, a candidate using quantization configuration \(q\) must therefore receive:

1. a native tutor evaluation producing `answer_quality`;
2. a corresponding gem5 evaluation producing the hardware-performance result from which `latency_ms` is obtained.

The quality result from one quantization configuration must not be combined with the hardware result from a different quantization configuration.

This document defines that dependency but does not define which quantization formats CHIA will search over or how the quantized workload is propagated into gem5.

---

## 6. Objective-Layer Contract

The objective layer consumes the metrics produced by the two evaluation pipelines for the same candidate.

### Input

Conceptually:

```yaml
candidate_id: <candidate-id>

metrics:
  answer_quality: <native-tutor-result>
  latency_ms: <gem5-derived-result>
```

The required invariant is:

> Native tutor metrics and gem5 metrics must correspond to the same candidate configuration.

The objective layer interprets these metrics as:

```yaml
objectives:
  answer_quality:
    direction: maximize

  latency_ms:
    direction: minimize
```

### Output

For a candidate \(x\), the objective representation is:

```yaml
candidate_id: <candidate-id>

objective_values:
  answer_quality:
    value: <Q(x)>
    direction: maximize

  latency_ms:
    value: <L(x)>
    direction: minimize
```

These objective values are then used to compare candidates according to Pareto dominance.

The objective layer does not calculate the underlying metrics itself. It consumes the results produced by their respective evaluation pipelines.

---

## 7. Relationship to the CHIA Loop

The objective layer fits into the CHIA co-design loop as follows:

```text
          Candidate configuration x
                    |
          +---------+---------+
          |                   |
          v                   v
    Native tutor            gem5
     evaluation           evaluation
          |                   |
          v                   v
   answer_quality      hardware metrics
        Q(x)                   |
          |                    v
          |              latency_ms
          |                 L(x)
          \                   /
           \                 /
            +---------------+
                    |
                    v
           Objective layer
                    |
             max Q(x)
             min L(x)
                    |
                    v
          Pareto comparison
                    |
                    v
             CHIA decision
```

The objective layer therefore acts as the point where the native quality result and hardware-performance result are interpreted together.

---

## 8. Scope Boundaries

This objective definition intentionally does not define:

- how `answer_quality` is calculated;
- the dataset or grader used to calculate answer quality;
- how `latency_ms` is measured or derived;
- the detailed gem5 workload implementation;
- which quantization formats are available;
- quantization search ranges;
- software knob search ranges;
- hardware knob search ranges;
- how quantization is implemented in the runtime;
- how quantization changes are propagated into gem5;
- the complete joint HW/SW search space;
- the execution runner joining the two pipelines.

These are handled by their respective workload, evaluation, runtime, and design-space tasks.

This document defines only:

1. the metrics entering the optimization layer;
2. their optimization directions;
3. how candidate configurations are compared;
4. the cross-layer dependency introduced by quantization.

---

## 9. Objective Definition Summary

For every candidate configuration \(x\):

$$
\boxed{\text{maximize } Q(x)}
$$

$$
\boxed{\text{minimize } L(x)}
$$

where:

$$
Q(x) = \text{native tutor answer quality}
$$

and:

$$
L(x) = \text{gem5-derived latency}
$$

Candidate configurations are compared using Pareto dominance.

Quantization is explicitly treated as a cross-layer variable:

$$
\boxed{
q \rightarrow Q(x)
\qquad\text{and}\qquad
q \rightarrow \text{compute profile} \rightarrow L(x)
}
$$

The objective layer therefore joins native software-quality evaluation and gem5 hardware-performance evaluation without collapsing them into an arbitrary weighted scalar.
