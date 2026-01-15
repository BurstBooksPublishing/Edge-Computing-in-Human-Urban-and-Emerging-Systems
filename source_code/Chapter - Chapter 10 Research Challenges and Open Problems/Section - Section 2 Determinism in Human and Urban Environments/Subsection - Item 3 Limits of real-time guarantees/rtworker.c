#include 
#include 
#include 
#include 
#include 
#include 

#define TOKEN_RATE 50         // tokens per second (max inputs/s)
#define BUCKET_CAP 10         // burst capacity
#define CORE 3                // CPU core for isolation

// Placeholder: perform inference; replace with CUDA/TensorRT calls.
static int inference_call(void) {
    // run model inference, return success(1)/fail(0)
    usleep(8000); // simulate ~8ms inference
    return 1;
}

static void *rt_worker(void *arg) {
    struct sched_param sp;
    cpu_set_t cpuset;
    struct timespec last = {0,0};
    uint64_t tokens = BUCKET_CAP;

    // Set real-time priority
    sp.sched_priority = 80;
    pthread_setschedparam(pthread_self(), SCHED_FIFO, &sp);

    // Pin to CORE
    CPU_ZERO(&cpuset);
    CPU_SET(CORE, &cpuset);
    pthread_setaffinity_np(pthread_self(), sizeof(cpuset), &cpuset);

    clock_gettime(CLOCK_MONOTONIC, &last);
    while (1) {
        struct timespec now;
        clock_gettime(CLOCK_MONOTONIC, &now);
        double dt = (now.tv_sec - last.tv_sec) + (now.tv_nsec - last.tv_nsec) * 1e-9;
        last = now;

        // Refill token bucket
        tokens += (uint64_t)(dt * TOKEN_RATE);
        if (tokens > BUCKET_CAP) tokens = BUCKET_CAP;

        if (tokens > 0) {
            tokens--; // consume token for a new frame
            if (!inference_call()) {
                // handle inference failure, maybe fall back
            }
        } else {
            // drop/frame-skip policy to preserve latency guarantees
            // in production, log telemetry and signal degradation
            usleep(1000); // backoff short period
        }
    }
    return NULL;
}

int main(void) {
    pthread_t th;
    pthread_create(&th, NULL, rt_worker, NULL);
    pthread_join(th, NULL);
    return 0;
}