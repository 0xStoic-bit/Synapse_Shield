import os

try:
    from prometheus_client import Counter, Histogram, CollectorRegistry, multiprocess
    
    if "PROMETHEUS_MULTIPROC_DIR" in os.environ:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
    else:
        from prometheus_client import REGISTRY as registry

    synapse_requests_total = Counter(
        'synapse_requests_total',
        'Total number of requests analyzed by Synapse Shield',
        ['status', 'classification'],
        registry=registry
    )

    synapse_inference_latency_seconds = Histogram(
        'synapse_inference_latency_seconds',
        'Time spent running the behavioral inference engine',
        registry=registry,
        buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 1.0)
    )
    
    METRICS_ENABLED = True
except ImportError:
    METRICS_ENABLED = False
    synapse_requests_total = None
    synapse_inference_latency_seconds = None
