import os

try:
    from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, multiprocess

    if "PROMETHEUS_MULTIPROC_DIR" in os.environ:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
    else:
        from prometheus_client import REGISTRY as registry

    synapse_requests_total = Counter(
        "synapse_requests_total",
        "Total number of requests analyzed by Synapse Shield",
        ["status", "classification"],
        registry=registry,
    )

    synapse_inference_latency_seconds = Histogram(
        "synapse_inference_latency_seconds",
        "Time spent running the behavioral inference engine",
        registry=registry,
        buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 1.0),
    )

    synapse_replays_detected_total = Counter(
        "synapse_replays_detected_total",
        "Total replay attacks prevented by Synapse Shield",
        registry=registry,
    )

    synapse_active_bans = Gauge(
        "synapse_active_bans",
        "Current number of actively quarantined IP addresses",
        registry=registry,
    )

    synapse_pow_solved_total = Counter(
        "synapse_pow_solved_total",
        "Total Proof of Work puzzles successfully verified",
        registry=registry,
    )

    synapse_shadow_requests_total = Counter(
        "synapse_shadow_requests_total",
        "Total requests evaluated under Shadow Mode",
        ["action", "classification"],
        registry=registry,
    )

    METRICS_ENABLED = True
except ImportError:
    METRICS_ENABLED = False
    synapse_requests_total = None
    synapse_inference_latency_seconds = None
    synapse_replays_detected_total = None
    synapse_active_bans = None
    synapse_pow_solved_total = None
    synapse_shadow_requests_total = None
