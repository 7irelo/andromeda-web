"""WebSocket connection metrics for the chat and notification consumers."""
from prometheus_client import Counter

WS_CONNECTIONS = Counter('ws_connections_total', 'WebSocket connections accepted', ['consumer'])
WS_DISCONNECTS = Counter('ws_disconnects_total', 'WebSocket disconnects by kind', ['consumer', 'reason'])


def disconnect_reason(code):
    """Bucket close codes so the label set stays small."""
    if code in (1000, 1001):
        return 'normal'
    if code == 1006:
        return 'abnormal'  # dropped without a close frame: network, proxy or server restart
    if isinstance(code, int) and 4000 <= code < 5000:
        return 'policy'    # our own closes: auth, membership, frame limits
    return 'error'


def connected(consumer):
    WS_CONNECTIONS.labels(consumer).inc()


def disconnected(consumer, code):
    WS_DISCONNECTS.labels(consumer, disconnect_reason(code)).inc()
