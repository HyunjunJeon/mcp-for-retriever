"""Integration tests for observability features (OpenTelemetry + Sentry)."""

import pytest
from typing import Dict, Any, List
from unittest.mock import Mock, patch, AsyncMock
import asyncio
import json
from datetime import datetime

from src.observability import TelemetrySetup, get_tracer, SentryIntegration
from src.middleware.observability import ObservabilityMiddleware
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, InMemorySpanExporter
import sentry_sdk


class TestObservabilityIntegration:
    """Test observability integration scenarios."""
    
    @pytest.fixture
    def mock_telemetry(self):
        """Create mock telemetry setup with in-memory exporter."""
        # Create in-memory span exporter for testing
        memory_exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(memory_exporter))
        trace.set_tracer_provider(provider)
        
        telemetry = TelemetrySetup(
            service_name="test-mcp",
            enable_console_export=False,
            enable_prometheus=False
        )
        telemetry._tracer_provider = provider
        telemetry._tracer = trace.get_tracer("test-mcp")
        
        return telemetry, memory_exporter
    
    @pytest.fixture
    def mock_sentry(self):
        """Create mock Sentry integration."""
        sentry = SentryIntegration(
            dsn=None,  # Disable actual sending
            environment="test",
            enable_performance=True
        )
        sentry._initialized = True  # Pretend it's initialized
        return sentry
    
    @pytest.fixture
    def observability_middleware(self, mock_telemetry, mock_sentry):
        """Create observability middleware with mocks."""
        telemetry, memory_exporter = mock_telemetry
        
        with patch('src.observability.get_tracer') as mock_get_tracer:
            mock_get_tracer.return_value = telemetry._tracer
            
            with patch('src.observability.get_sentry') as mock_get_sentry:
                mock_get_sentry.return_value = mock_sentry
                
                middleware = ObservabilityMiddleware(
                    service_name="test-mcp",
                    enable_tracing=True,
                    enable_sentry=True,
                    trace_all_requests=True
                )
                
                # Attach memory exporter for testing
                middleware._memory_exporter = memory_exporter
                
                return middleware
    
    @pytest.mark.asyncio
    async def test_full_request_tracing_flow(self, observability_middleware):
        """Test complete request flow with tracing."""
        # Create request
        request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "search_web",
                "arguments": {"query": "test query"}
            },
            "id": 1,
            "request_id": "req-123",
            "user": {
                "id": "user-456",
                "email": "test@example.com",
                "type": "user"
            }
        }
        
        # Mock successful response
        async def mock_call_next(req):
            await asyncio.sleep(0.01)  # Simulate processing
            return {
                "jsonrpc": "2.0",
                "result": {"data": "search results"},
                "id": 1
            }
        
        # Process request
        response = await observability_middleware(request, mock_call_next)
        
        # Verify response
        assert response["result"]["data"] == "search results"
        
        # Get exported spans
        spans = observability_middleware._memory_exporter.get_finished_spans()
        assert len(spans) > 0
        
        # Verify span attributes
        span = spans[0]
        assert span.name == "tools/call:search_web"
        assert span.attributes["mcp.request_id"] == "req-123"
        assert span.attributes["mcp.method"] == "tools/call"
        assert span.attributes["mcp.tool_name"] == "search_web"
        assert span.attributes["user.id"] == "user-456"
        assert span.attributes["user.type"] == "user"
        assert span.attributes["mcp.error"] is False
        assert "mcp.duration_ms" in span.attributes
        assert span.status.status_code == trace.StatusCode.OK
    
    @pytest.mark.asyncio
    async def test_error_capture_flow(self, observability_middleware, mock_sentry):
        """Test error capture in both OpenTelemetry and Sentry."""
        # Mock Sentry capture
        captured_errors = []
        mock_sentry.capture_error = Mock(side_effect=lambda e, **kwargs: captured_errors.append((e, kwargs)))
        
        # Create request
        request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "search_database",
                "arguments": {"query": "SELECT * FROM invalid_table"}
            },
            "id": 2,
            "request_id": "req-error-123",
            "user": {"id": "user-789"}
        }
        
        # Mock error response
        async def mock_call_next_error(req):
            raise ValueError("Database connection failed")
        
        # Process request
        with pytest.raises(ValueError):
            await observability_middleware(request, mock_call_next_error)
        
        # Verify error was captured in Sentry
        assert len(captured_errors) == 1
        error, context = captured_errors[0]
        assert isinstance(error, ValueError)
        assert context["extra_context"]["request_id"] == "req-error-123"
        assert context["extra_context"]["method"] == "tools/call"
        assert context["extra_context"]["tool_name"] == "search_database"
        
        # Get exported spans
        spans = observability_middleware._memory_exporter.get_finished_spans()
        assert len(spans) > 0
        
        # Verify error span
        span = spans[0]
        assert span.attributes["mcp.error"] is True
        assert span.status.status_code == trace.StatusCode.ERROR
        assert "Database connection failed" in span.status.description
    
    @pytest.mark.asyncio
    async def test_trace_context_propagation(self, observability_middleware):
        """Test trace context propagation between services."""
        # Create parent span
        tracer = trace.get_tracer("test-parent")
        with tracer.start_as_current_span("parent-operation") as parent_span:
            parent_trace_id = parent_span.get_span_context().trace_id
            
            # Inject trace context into headers
            headers = {}
            observability_middleware.inject_trace_context(headers)
            
            # Verify trace context headers
            assert "traceparent" in headers
            assert f"{format(parent_trace_id, '032x')}" in headers["traceparent"]
            
            # Create request with trace context
            request = {
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": 3,
                "request_id": "req-trace-123",
                "headers": headers
            }
            
            # Process request
            async def mock_call_next(req):
                # Verify we can extract trace context
                ctx = observability_middleware.extract_trace_context(req.get("headers", {}))
                assert ctx is not None
                assert ctx["traceparent"] == headers["traceparent"]
                return {"jsonrpc": "2.0", "result": {"tools": []}, "id": 3}
            
            response = await observability_middleware(request, mock_call_next)
            
            # Get child spans
            spans = observability_middleware._memory_exporter.get_finished_spans()
            child_spans = [s for s in spans if s.parent and s.parent.trace_id == parent_trace_id]
            
            # Verify parent-child relationship
            assert len(child_spans) > 0
            child_span = child_spans[0]
            assert child_span.parent.trace_id == parent_trace_id
    
    @pytest.mark.asyncio
    async def test_metrics_collection(self, mock_telemetry):
        """Test metrics collection during request processing."""
        telemetry, _ = mock_telemetry
        
        # Create custom metrics
        telemetry.create_custom_metrics()
        
        # Mock metric recording
        recorded_metrics = []
        
        def mock_add(value, attributes=None):
            recorded_metrics.append(("counter", value, attributes))
        
        def mock_record(value, attributes=None):
            recorded_metrics.append(("histogram", value, attributes))
        
        telemetry.request_counter.add = mock_add
        telemetry.request_duration.record = mock_record
        
        # Simulate request processing with metrics
        telemetry.request_counter.add(1, {"tool": "search_web", "status": "success"})
        telemetry.request_duration.record(150.5, {"tool": "search_web"})
        
        # Verify metrics
        assert len(recorded_metrics) == 2
        assert recorded_metrics[0] == ("counter", 1, {"tool": "search_web", "status": "success"})
        assert recorded_metrics[1] == ("histogram", 150.5, {"tool": "search_web"})
    
    @pytest.mark.asyncio
    async def test_sentry_transaction_flow(self, observability_middleware, mock_sentry):
        """Test Sentry transaction creation and completion."""
        # Mock transaction
        mock_transaction = Mock()
        mock_transaction.__enter__ = Mock(return_value=mock_transaction)
        mock_transaction.__exit__ = Mock()
        mock_transaction.set_status = Mock()
        mock_transaction.set_tag = Mock()
        
        mock_sentry.create_transaction = Mock(return_value=mock_transaction)
        
        # Create request
        request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": "search_vectors"},
            "id": 4,
            "request_id": "req-sentry-123"
        }
        
        # Process request
        async def mock_call_next(req):
            return {"jsonrpc": "2.0", "result": {"vectors": []}, "id": 4}
        
        await observability_middleware(request, mock_call_next)
        
        # Verify transaction was created
        mock_sentry.create_transaction.assert_called_once_with(
            name="tools/call:search_vectors",
            op="mcp.request"
        )
        
        # Verify transaction lifecycle
        mock_transaction.__enter__.assert_called_once()
        mock_transaction.set_status.assert_called_with("ok")
        mock_transaction.set_tag.assert_any_call("mcp.method", "tools/call")
        mock_transaction.set_tag.assert_any_call("mcp.tool_name", "search_vectors")
        mock_transaction.__exit__.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_baggage_propagation(self, observability_middleware):
        """Test baggage context propagation."""
        from opentelemetry import baggage
        
        # Set baggage before request
        baggage.set_baggage("tenant.id", "tenant-123")
        baggage.set_baggage("feature.flag", "new-ui")
        
        # Create request
        request = {
            "jsonrpc": "2.0",
            "method": "health_check",
            "id": 5,
            "request_id": "req-baggage-123",
            "user": {"id": "user-999", "type": "admin"}
        }
        
        # Process request
        async def mock_call_next(req):
            # Verify baggage is accessible
            assert baggage.get_baggage("tenant.id") == "tenant-123"
            assert baggage.get_baggage("feature.flag") == "new-ui"
            # User baggage should be set by middleware
            assert baggage.get_baggage("user.id") == "user-999"
            assert baggage.get_baggage("user.type") == "admin"
            return {"jsonrpc": "2.0", "result": {"status": "healthy"}, "id": 5}
        
        await observability_middleware(request, mock_call_next)
        
        # Verify baggage was propagated
        assert baggage.get_baggage("user.id") == "user-999"
        assert baggage.get_baggage("user.type") == "admin"
    
    @pytest.mark.asyncio
    async def test_performance_monitoring_disabled(self):
        """Test behavior when performance monitoring is disabled."""
        # Create Sentry without performance monitoring
        sentry = SentryIntegration(
            dsn=None,
            enable_performance=False
        )
        sentry._initialized = True
        
        # Create transaction should return None
        transaction = sentry.create_transaction("test-op")
        assert transaction is None
        
        # Create middleware without tracing
        with patch('src.observability.get_sentry', return_value=sentry):
            middleware = ObservabilityMiddleware(
                enable_tracing=False,
                enable_sentry=True
            )
            
            # Process request
            request = {"method": "test", "request_id": "req-no-perf"}
            
            async def mock_call_next(req):
                return {"result": "ok"}
            
            response = await middleware(request, mock_call_next)
            assert response["result"] == "ok"
            
            # No spans should be created
            assert middleware.tracer is None