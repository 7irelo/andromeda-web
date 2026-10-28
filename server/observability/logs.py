"""One JSON object per log line, with the request id and (when tracing) the trace id."""
import json
import logging
from datetime import UTC, datetime

# Attributes every LogRecord has; anything else was passed via ``extra=``.
_STANDARD = set(vars(logging.LogRecord('', 0, '', 0, '', (), None))) | {'message', 'asctime', 'request_id'}


def _trace_ids():
    try:
        from opentelemetry import trace
    except ImportError:
        return None, None
    ctx = trace.get_current_span().get_span_context()
    if not ctx.is_valid:
        return None, None
    return f'{ctx.trace_id:032x}', f'{ctx.span_id:016x}'


class JsonFormatter(logging.Formatter):
    def format(self, record):
        out = {
            'ts': datetime.fromtimestamp(record.created, UTC).isoformat(timespec='milliseconds'),
            'level': record.levelname,
            'logger': record.name,
            'msg': record.getMessage(),
            'request_id': getattr(record, 'request_id', '-'),
            'pid': record.process,
        }
        trace_id, span_id = _trace_ids()
        if trace_id:
            out['trace_id'], out['span_id'] = trace_id, span_id
        for key, value in vars(record).items():
            if key not in _STANDARD and not key.startswith('_'):
                out[key] = value if isinstance(value, (str, int, float, bool, type(None))) else repr(value)
        if record.exc_info:
            out['exc'] = self.formatException(record.exc_info)
        return json.dumps(out, ensure_ascii=False)
