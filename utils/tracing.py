import contextlib
import functools
import inspect
from opentelemetry import trace

try:
    import pyroscope
    _profile_tags = pyroscope.tag_wrapper
except ImportError:
    @contextlib.contextmanager
    def _profile_tags(_tags):
        yield

tracer = trace.get_tracer("mydiscordbot")

def trace_function(func):
    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        with tracer.start_as_current_span(func.__name__) as span:
            span.set_attribute("function.name", func.__name__)
            # Record arguments (be careful with sensitive data, here we just record keys or simple types)
            # For simplicity, we might not record all args to avoid clutter or PII
            try:
                with _profile_tags({"span_name": func.__name__}):
                    return await func(*args, **kwargs)
            except Exception as e:
                span.record_exception(e)
                raise e

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        with tracer.start_as_current_span(func.__name__) as span:
            span.set_attribute("function.name", func.__name__)
            try:
                with _profile_tags({"span_name": func.__name__}):
                    return func(*args, **kwargs)
            except Exception as e:
                span.record_exception(e)
                raise e

    if inspect.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper
