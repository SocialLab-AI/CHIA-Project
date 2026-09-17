/*
 * Hardware-owned attention proxy used by the native and gem5 adapters.
 * It compares packed-Q4 grouped-query attention with an FP32 reference and
 * emits machine-readable correctness evidence for the orchestration loop.
 */
#include <math.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>

#ifndef CONTEXT
#define CONTEXT 512
#endif

#ifndef QUERY_HEADS
#define QUERY_HEADS 4
#endif

#ifndef KV_HEADS
#define KV_HEADS 2
#endif

#ifndef HEAD_DIM
#define HEAD_DIM 32
#endif

#ifndef REPETITIONS
#define REPETITIONS 10
#endif

#ifndef THREADS
#define THREADS 2
#endif

#define PACKED_DIM (HEAD_DIM / 2)
#define Q4_MAX 7

#if CONTEXT <= 0
#error "CONTEXT must be positive"
#endif

#if QUERY_HEADS <= 0
#error "QUERY_HEADS must be positive"
#endif

#if KV_HEADS <= 0
#error "KV_HEADS must be positive"
#elif (QUERY_HEADS % KV_HEADS) != 0
#error "QUERY_HEADS must be divisible by KV_HEADS"
#endif

#if HEAD_DIM <= 0 || (HEAD_DIM % 2) != 0
#error "Packed Q4 requires a positive even HEAD_DIM"
#endif

#if REPETITIONS <= 0
#error "REPETITIONS must be positive"
#endif

#if THREADS != 2
#error "The reviewed proxy currently supports exactly two threads"
#endif

static float query[QUERY_HEADS][HEAD_DIM];

static uint8_t keys_q4[CONTEXT][KV_HEADS][PACKED_DIM];
static uint8_t values_q4[CONTEXT][KV_HEADS][PACKED_DIM];

static float key_scales[CONTEXT][KV_HEADS];
static float value_scales[CONTEXT][KV_HEADS];

static float scores[QUERY_HEADS][CONTEXT];
static float output_fp32[QUERY_HEADS][HEAD_DIM];
static float output_q4[QUERY_HEADS][HEAD_DIM];

static float make_value(int index, int salt)
{
    int value = (index * 37 + salt * 17 + 23) % 201;
    return (float)(value - 100) / 100.0f;
}

static uint8_t pack_q4(int8_t low, int8_t high)
{
    return ((uint8_t)low & 0x0f) |
           (((uint8_t)high & 0x0f) << 4);
}

static int8_t unpack_q4(uint8_t packed, int high)
{
    uint8_t value = high ? (packed >> 4) : (packed & 0x0f);
    return value >= 8 ? (int8_t)(value - 16) : (int8_t)value;
}

static void quantize_vector(
    int token,
    int head,
    int salt,
    uint8_t destination[PACKED_DIM],
    float *scale)
{
    float maximum = 0.0f;

    for (int dimension = 0; dimension < HEAD_DIM; dimension++) {
        int index = (token * KV_HEADS + head) * HEAD_DIM + dimension;
        float value = fabsf(make_value(index, salt));

        if (value > maximum) {
            maximum = value;
        }
    }

    *scale = maximum > 0.0f ? maximum / (float)Q4_MAX : 1.0f;

    for (int packed_index = 0;
         packed_index < PACKED_DIM;
         packed_index++) {

        int dimension0 = packed_index * 2;
        int dimension1 = dimension0 + 1;

        int index0 =
            (token * KV_HEADS + head) * HEAD_DIM + dimension0;
        int index1 =
            (token * KV_HEADS + head) * HEAD_DIM + dimension1;

        int q0 = (int)roundf(make_value(index0, salt) / *scale);
        int q1 = (int)roundf(make_value(index1, salt) / *scale);

        if (q0 > Q4_MAX) q0 = Q4_MAX;
        if (q0 < -Q4_MAX) q0 = -Q4_MAX;
        if (q1 > Q4_MAX) q1 = Q4_MAX;
        if (q1 < -Q4_MAX) q1 = -Q4_MAX;

        destination[packed_index] =
            pack_q4((int8_t)q0, (int8_t)q1);
    }
}

static void initialize_data(void)
{
    for (int head = 0; head < QUERY_HEADS; head++) {
        for (int dimension = 0; dimension < HEAD_DIM; dimension++) {
            int index = head * HEAD_DIM + dimension;
            query[head][dimension] = make_value(index, 1);
        }
    }

    for (int token = 0; token < CONTEXT; token++) {
        for (int head = 0; head < KV_HEADS; head++) {
            quantize_vector(
                token,
                head,
                3,
                keys_q4[token][head],
                &key_scales[token][head]);

            quantize_vector(
                token,
                head,
                7,
                values_q4[token][head],
                &value_scales[token][head]);
        }
    }
}

static float dequantize(
    const uint8_t packed[PACKED_DIM],
    int dimension,
    float scale)
{
    uint8_t byte = packed[dimension / 2];
    int8_t quantized = unpack_q4(byte, dimension % 2);
    return (float)quantized * scale;
}

static int kv_head_for_query(int query_head)
{
    int query_heads_per_kv = QUERY_HEADS / KV_HEADS;
    return query_head / query_heads_per_kv;
}

static void run_fp32_reference(void)
{
    const float scale = 1.0f / sqrtf((float)HEAD_DIM);

    for (int query_head = 0; query_head < QUERY_HEADS; query_head++) {
        int kv_head = kv_head_for_query(query_head);
        float maximum_score = -INFINITY;

        for (int token = 0; token < CONTEXT; token++) {
            float dot_product = 0.0f;

            for (int dimension = 0; dimension < HEAD_DIM; dimension++) {
                int index =
                    (token * KV_HEADS + kv_head) * HEAD_DIM + dimension;

                dot_product +=
                    query[query_head][dimension] *
                    make_value(index, 3);
            }

            scores[query_head][token] = dot_product * scale;

            if (scores[query_head][token] > maximum_score) {
                maximum_score = scores[query_head][token];
            }
        }

        float denominator = 0.0f;

        for (int token = 0; token < CONTEXT; token++) {
            scores[query_head][token] =
                expf(scores[query_head][token] - maximum_score);

            denominator += scores[query_head][token];
        }

        for (int dimension = 0; dimension < HEAD_DIM; dimension++) {
            output_fp32[query_head][dimension] = 0.0f;
        }

        for (int token = 0; token < CONTEXT; token++) {
            float probability =
                scores[query_head][token] / denominator;

            for (int dimension = 0; dimension < HEAD_DIM; dimension++) {
                int index =
                    (token * KV_HEADS + kv_head) * HEAD_DIM + dimension;

                output_fp32[query_head][dimension] +=
                    probability * make_value(index, 7);
            }
        }
    }
}

static void run_q4_head(int query_head)
{
    const float scale = 1.0f / sqrtf((float)HEAD_DIM);
    int kv_head = kv_head_for_query(query_head);
    float maximum_score = -INFINITY;

    for (int token = 0; token < CONTEXT; token++) {
        float dot_product = 0.0f;

        for (int dimension = 0; dimension < HEAD_DIM; dimension++) {
            float key = dequantize(
                keys_q4[token][kv_head],
                dimension,
                key_scales[token][kv_head]);

            dot_product += query[query_head][dimension] * key;
        }

        scores[query_head][token] = dot_product * scale;

        if (scores[query_head][token] > maximum_score) {
            maximum_score = scores[query_head][token];
        }
    }

    float denominator = 0.0f;

    for (int token = 0; token < CONTEXT; token++) {
        scores[query_head][token] =
            expf(scores[query_head][token] - maximum_score);

        denominator += scores[query_head][token];
    }

    for (int dimension = 0; dimension < HEAD_DIM; dimension++) {
        output_q4[query_head][dimension] = 0.0f;
    }

    for (int token = 0; token < CONTEXT; token++) {
        float probability = scores[query_head][token] / denominator;

        for (int dimension = 0; dimension < HEAD_DIM; dimension++) {
            float value = dequantize(
                values_q4[token][kv_head],
                dimension,
                value_scales[token][kv_head]);

            output_q4[query_head][dimension] += probability * value;
        }
    }
}

static void *attention_worker(void *argument)
{
    int thread_id = *(int *)argument;

    for (int query_head = thread_id;
         query_head < QUERY_HEADS;
         query_head += THREADS) {

        run_q4_head(query_head);
    }

    return NULL;
}

static int run_q4_attention(void)
{
    pthread_t worker_thread;
    int main_thread_id = 0;
    int worker_thread_id = 1;

    if (pthread_create(
            &worker_thread,
            NULL,
            attention_worker,
            &worker_thread_id) != 0) {

        return 0;
    }

    /* Both threads use the same strided dispatcher for every legal head count. */
    attention_worker(&main_thread_id);

    if (pthread_join(worker_thread, NULL) != 0) {
        return 0;
    }

    return 1;
}

static double calculate_checksum(
    float output[QUERY_HEADS][HEAD_DIM])
{
    double checksum = 0.0;

    for (int head = 0; head < QUERY_HEADS; head++) {
        for (int dimension = 0; dimension < HEAD_DIM; dimension++) {
            int position = head * HEAD_DIM + dimension + 1;

            checksum +=
                (double)output[head][dimension] *
                (double)position;
        }
    }

    return checksum;
}

int main(void)
{
    initialize_data();
    run_fp32_reference();

    for (int repetition = 0;
         repetition < REPETITIONS;
         repetition++) {

        if (!run_q4_attention()) {
            printf("status=FAIL\n");
            return 1;
        }
    }

    double fp32_checksum = calculate_checksum(output_fp32);
    double q4_checksum = calculate_checksum(output_q4);

    double maximum_absolute_error = 0.0;
    double squared_error_sum = 0.0;
    double reference_squared_sum = 0.0;
    double reference_max_absolute = 0.0;

    for (int head = 0; head < QUERY_HEADS; head++) {
        for (int dimension = 0; dimension < HEAD_DIM; dimension++) {
            double reference =
                (double)output_fp32[head][dimension];
            double difference =
                (double)output_q4[head][dimension] - reference;

            double absolute_error = fabs(difference);
            double reference_absolute = fabs(reference);

            if (absolute_error > maximum_absolute_error) {
                maximum_absolute_error = absolute_error;
            }

            if (reference_absolute > reference_max_absolute) {
                reference_max_absolute = reference_absolute;
            }

            squared_error_sum += difference * difference;
            reference_squared_sum += reference * reference;
        }
    }

    double element_count = (double)(QUERY_HEADS * HEAD_DIM);
    double mean_squared_error =
        squared_error_sum / element_count;
    double root_mean_squared_error = sqrt(mean_squared_error);
    double reference_rms = sqrt(reference_squared_sum / element_count);
    double normalized_rmse =
        reference_rms > 0.0
            ? root_mean_squared_error / reference_rms
            : INFINITY;
    double normalized_max_error =
        reference_max_absolute > 0.0
            ? maximum_absolute_error / reference_max_absolute
            : INFINITY;

    int passed =
        isfinite(fp32_checksum) &&
        isfinite(q4_checksum) &&
        isfinite(maximum_absolute_error) &&
        isfinite(mean_squared_error) &&
        isfinite(root_mean_squared_error) &&
        isfinite(reference_rms) &&
        isfinite(reference_max_absolute) &&
        isfinite(normalized_rmse) &&
        isfinite(normalized_max_error);

    printf("ATTENTION_Q4_RESULT\n");
    printf("context=%d\n", CONTEXT);
    printf("query_heads=%d\n", QUERY_HEADS);
    printf("kv_heads=%d\n", KV_HEADS);
    printf("head_dimension=%d\n", HEAD_DIM);
    printf("threads=%d\n", THREADS);
    printf("repetitions=%d\n", REPETITIONS);
    printf("kv_format=Q4\n");
    printf("kv_mapping=grouped_query\n");
    printf("fp32_checksum=%.9f\n", fp32_checksum);
    printf("q4_checksum=%.9f\n", q4_checksum);
    printf("max_absolute_error=%.9f\n", maximum_absolute_error);
    printf("mean_squared_error=%.9f\n", mean_squared_error);
    printf("root_mean_squared_error=%.9f\n", root_mean_squared_error);
    printf("reference_rms=%.9f\n", reference_rms);
    printf("reference_max_absolute=%.9f\n", reference_max_absolute);
    printf("normalized_rmse=%.9f\n", normalized_rmse);
    printf("normalized_max_error=%.9f\n", normalized_max_error);
    printf("status=%s\n", passed ? "PASS" : "FAIL");

    return passed ? 0 : 1;
}
