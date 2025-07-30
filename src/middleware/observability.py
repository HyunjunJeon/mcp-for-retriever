"""Observability middleware integrating OpenTelemetry and Sentry."""

from typing import Any, Callable, Dict, Optional
import time
import structlog
from opentelemetry import trace, baggage
from opentelemetry.trace import Status, StatusCode

from src.observability import get_tracer, get_sentry

logger = structlog.get_logger(__name__)


class ObservabilityMiddleware:
    """Middleware for distributed tracing and error tracking."""
    
    def __init__(
        self,
        service_name: str = "mcp-retriever",
        enable_tracing: bool = True,
        enable_sentry: bool = True,
        trace_all_requests: bool = False
    ):
        """Initialize observability middleware.
        
        Args:
            service_name: Name of the service for tracing
            enable_tracing: Whether to enable OpenTelemetry tracing
            enable_sentry: Whether to enable Sentry integration
            trace_all_requests: Whether to trace all requests or only errors
        """
        self.service_name = service_name
        self.enable_tracing = enable_tracing
        self.enable_sentry = enable_sentry
        self.trace_all_requests = trace_all_requests
        
        # Get tracer and Sentry instances
        self.tracer = get_tracer(f"{service_name}.middleware") if enable_tracing else None
        self.sentry = get_sentry() if enable_sentry else None
    
    async def __call__(self, request: Dict[str, Any], call_next: Callable) -> Dict[str, Any]:
        """Add observability to request processing."""
        # Extract request information
        request_id = request.get("request_id", "unknown")
        method = request.get("method", "unknown")
        user = request.get("user", {})
        
        # Extract tool name if applicable
        tool_name = None
        if method == "tools/call":
            params = request.get("params", {})
            if isinstance(params, dict):
                tool_name = params.get("name")
        
        # Set up tracing context
        span_name = f"{method}"
        if tool_name:
            span_name = f"{method}:{tool_name}"
        
        # Start span if tracing is enabled
        span = None
        if self.enable_tracing and self.tracer:
            span = self.tracer.start_span(span_name)
            
            # Add span attributes
            span.set_attribute("mcp.request_id", request_id)
            span.set_attribute("mcp.method", method)
            if tool_name:
                span.set_attribute("mcp.tool_name", tool_name)
            
            # Add user attributes
            if isinstance(user, dict):
                user_id = user.get("id", "anonymous")
                user_type = user.get("type", "user")
                span.set_attribute("user.id", user_id)
                span.set_attribute("user.type", user_type)
                
                # Set baggage for propagation
                baggage.set_baggage("user.id", str(user_id))
                baggage.set_baggage("user.type", user_type)
        
        # Set Sentry context
        if self.enable_sentry and self.sentry:
            # Set user context
            if isinstance(user, dict) and user.get("id"):
                self.sentry.set_user_context(
                    user_id=str(user.get("id")),
                    email=user.get("email"),
                    username=user.get("username")
                )
            
            # Set request context
            self.sentry.set_request_context(request_id, method, tool_name)
            
            # Add breadcrumb
            self.sentry.add_breadcrumb(
                message=f"Processing {method}",
                category="mcp.request",
                data={
                    "request_id": request_id,
                    "tool_name": tool_name,
                    "user_id": user.get("id") if isinstance(user, dict) else None
                }
            )
        
        # Process request
        start_time = time.time()
        error_occurred = False
        error_details = None
        response = None
        
        try:
            # Create Sentry transaction if enabled
            sentry_transaction = None
            if self.enable_sentry and self.sentry and self.sentry.enable_performance:
                sentry_transaction = self.sentry.create_transaction(
                    name=span_name,
                    op="mcp.request"
                )
                if sentry_transaction:
                    sentry_transaction.__enter__()
            
            # Call next middleware/handler
            response = await call_next(request)
            
            # Check for errors in response
            if isinstance(response, dict) and "error" in response:
                error_occurred = True
                error_details = response["error"]
            
            return response
            
        except Exception as e:
            error_occurred = True
            error_details = str(e)
            
            # Capture exception in Sentry
            if self.enable_sentry and self.sentry:
                self.sentry.capture_error(
                    e,
                    extra_context={
                        "request_id": request_id,
                        "method": method,
                        "tool_name": tool_name,
                        "user_id": user.get("id") if isinstance(user, dict) else None
                    }
                )
            
            raise
            
        finally:
            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000
            
            # Update span
            if span:
                span.set_attribute("mcp.duration_ms", duration_ms)
                span.set_attribute("mcp.error", error_occurred)
                
                if error_occurred:
                    span.set_status(Status(StatusCode.ERROR, str(error_details)))
                    if error_details and isinstance(error_details, dict):
                        span.set_attribute("error.code", error_details.get("code", "unknown"))
                        span.set_attribute("error.message", error_details.get("message", "unknown"))
                else:
                    span.set_status(Status(StatusCode.OK))
                
                span.end()
            
            # End Sentry transaction
            if 'sentry_transaction' in locals() and sentry_transaction:
                sentry_transaction.set_status("ok" if not error_occurred else "internal_error")
                sentry_transaction.set_tag("mcp.method", method)
                if tool_name:
                    sentry_transaction.set_tag("mcp.tool_name", tool_name)
                sentry_transaction.__exit__(None, None, None)
            
            # Log completion
            if error_occurred or self.trace_all_requests:
                logger.info(
                    "Request completed",
                    request_id=request_id,
                    method=method,
                    tool_name=tool_name,
                    duration_ms=duration_ms,
                    error=error_occurred,
                    trace_id=span.get_span_context().trace_id if span else None
                )
    
    def extract_trace_context(self, headers: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """Extract trace context from headers.
        
        Args:
            headers: Request headers
            
        Returns:
            Trace context if found
        """
        if not self.enable_tracing:
            return None
        
        # OpenTelemetry uses W3C Trace Context standard
        traceparent = headers.get("traceparent")
        tracestate = headers.get("tracestate")
        
        if traceparent:
            return {
                "traceparent": traceparent,
                "tracestate": tracestate
            }
        
        return None
    
    def inject_trace_context(self, headers: Dict[str, str]):
        """Inject current trace context into headers.
        
        Args:
            headers: Headers dictionary to update
        """
        if not self.enable_tracing:
            return
        
        # Get current span
        span = trace.get_current_span()
        if span and span.is_recording():
            context = span.get_span_context()
            # Format according to W3C Trace Context
            headers["traceparent"] = f"00-{format(context.trace_id, '032x')}-{format(context.span_id, '016x')}-01"