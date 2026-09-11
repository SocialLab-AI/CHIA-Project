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

static void run_fp32_reference(void)
{
    const float scale = 1.0f / sqrtf((float)HEAD_DIM);

    for (int query_head = 0; query_head < QUERY_HEADS; query_head++) {
        int kv_head = query_head % KV_HEADS;
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
    int kv_head = query_head % KV_HEADS;
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
    int worker_id = 1;

    if (pthread_create(
            &worker_thread,
            NULL,
            attention_worker,
            &worker_id) != 0) {

        return 0;
    }

    /* The main thread handles query heads 0 and 2. */
    run_q4_head(0);
    run_q4_head(2);

    /* The worker handles query heads 1 and 3. */
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

    for (int head = 0; head < QUERY_HEADS; head++) {
        for (int dimension = 0; dimension < HEAD_DIM; dimension++) {
            double difference =
                (double)output_q4[head][dimension] -
                (double)output_fp32[head][dimension];

            double absolute_error = fabs(difference);

            if (absolute_error > maximum_absolute_error) {
                maximum_absolute_error = absolute_error;
            }

            squared_error_sum += difference * difference;
        }
    }

    double mean_squared_error =
        squared_error_sum / (QUERY_HEADS * HEAD_DIM);

    int passed =
        isfinite(q4_checksum) &&
        isfinite(maximum_absolute_error) &&
        isfinite(mean_squared_error);

    printf("ATTENTION_Q4_RESULT\n");
    printf("context=%d\n", CONTEXT);
    printf("query_heads=%d\n", QUERY_HEADS);
    printf("kv_heads=%d\n", KV_HEADS);
    printf("head_dimension=%d\n", HEAD_DIM);
    printf("threads=%d\n", THREADS);
    printf("repetitions=%d\n", REPETITIONS);
    printf("kv_format=Q4\n");
    printf("fp32_checksum=%.9f\n", fp32_checksum);
    printf("q4_checksum=%.9f\n", q4_checksum);
    printf("max_absolute_error=%.9f\n", maximum_absolute_error);
    printf("mean_squared_error=%.9f\n", mean_squared_error);
    printf("status=%s\n", passed ? "PASS" : "FAIL");

    return passed ? 0 : 1;
}
