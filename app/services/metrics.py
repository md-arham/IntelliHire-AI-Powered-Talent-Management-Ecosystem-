from prometheus_client import Counter, Histogram, start_http_server

# Prometheus metrics
ENFORCE_LATENCY = Histogram(
    'casbin_enforce_latency_seconds',
    'Latency of Casbin enforcement calls',
    ['tenant', 'result'],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1, 5]
)

ENFORCE_COUNTER = Counter(
    'casbin_enforce_total', 
    'Total number of Casbin enforcement calls',
    ['tenant', 'result']
)
POLICY_UPDATE_COUNTER = Counter(
    'casbin_policy_updates_total', 
    'Total number of policy updates',
    ['tenant', 'operation']
)

def setup_metrics(app=None):
    from app.core.config import settings
    start_http_server(settings.METRICS_PORT)
    return app