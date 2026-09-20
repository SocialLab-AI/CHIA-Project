/*
 * Frozen original-corrected profile from the Issue #60 repeated comparison.
 * The reviewed shared implementation lives in attention_kv.c; this entry file
 * locks the smaller 4/2/32 shape so the team can reproduce that profile.
 */
#define QUERY_HEADS 4
#define KV_HEADS 2
#define HEAD_DIM 32
#define REPETITIONS 1

#include "attention_kv.c"
