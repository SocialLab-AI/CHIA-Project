/*
 * Frozen Qwen-shaped profile from the Issue #60 repeated comparison.
 * The reviewed shared implementation lives in attention_kv.c; this entry file
 * locks the selected Qwen2.5 0.5B shape at 14/2/64 for team review.
 */
#define QUERY_HEADS 14
#define KV_HEADS 2
#define HEAD_DIM 64
#define REPETITIONS 1

#include "attention_kv.c"
