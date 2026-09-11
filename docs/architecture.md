# Architecture

```text
                         CHIA / Gemini
                              |
                     experiment config
                              |
              +---------------+---------------+
              |                               |
              v                               v
       Tutor Runner                     Hardware Runner
              |                               |
       System prompt                    Attention kernel
       + test question                        |
              |                               v
          Llama 3.1                          gem5
              |                               |
              v                               v
      Generated answer                   HW metrics
              |
              v
     OpenStax comparison
      (evaluation only)
              |
              v
       Quality/perf metrics
              |
              +---------------+---------------+
                              |
                              v
                         Run Record
```

OpenStax reference content is never provided to Llama as model context.
