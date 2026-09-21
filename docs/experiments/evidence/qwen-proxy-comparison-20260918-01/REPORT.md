# Original versus Qwen-shaped proxy comparison

Native KV cache: `{'key': 'f16', 'value': 'f16'}`. Proxy KV cache: `Q4`.

The KV representations differ. Timing trends and numerical approximation are reported separately; this experiment does not claim full-model equivalence.

## Summary

| Profile | Shape Q/KV/D | Spearman rho | Trend MAPE | Tolerance violations |
|---|---:|---:|---:|---|
| original-corrected | 4/2/32 | 1.0000 | 3.580% | 128 |
| qwen-shaped | 14/2/64 | 1.0000 | 3.668% | 128, 256, 512, 1024, 2048 |

## original-corrected

| Context | Mean gem5 seconds | Stddev | Worst normalized RMSE | Worst normalized max error |
|---:|---:|---:|---:|---:|
| 128 | 0.002557000 | 0.000000000 | 0.012966385 | 0.026286831 |
| 256 | 0.004932000 | 0.000000000 | 0.010602555 | 0.020245261 |
| 512 | 0.009470000 | 0.000000000 | 0.009314929 | 0.019847813 |
| 1024 | 0.018943000 | 0.000000000 | 0.009246765 | 0.018456762 |
| 2048 | 0.037634000 | 0.000000000 | 0.009138173 | 0.018569234 |

## qwen-shaped

| Context | Mean gem5 seconds | Stddev | Worst normalized RMSE | Worst normalized max error |
|---:|---:|---:|---:|---:|
| 128 | 0.007636000 | 0.000000000 | 0.023581689 | 0.041540401 |
| 256 | 0.014819000 | 0.000000000 | 0.012596505 | 0.029574890 |
| 512 | 0.029393000 | 0.000000000 | 0.010697379 | 0.025396136 |
| 1024 | 0.058514000 | 0.000000000 | 0.009284273 | 0.020225868 |
| 2048 | 0.116700000 | 0.000000000 | 0.009301861 | 0.020398974 |

## Decision rule

Prefer the Qwen-shaped profile only if it remains numerically controlled and its normalized context trend is at least as defensible as the corrected original. Do not choose a profile from absolute gem5 time alone because the modeled work differs.

This compares one-layer attention proxies. It does not simulate complete Qwen.
