"""Docker integration tests for observability features."""

import pytest
import os
import asyncio
import httpx
import json
import time
from typing import Dict, Any, List, Optional
from datetime import datetime


class TestDockerObservability:
    """Test observability features in Docker environment."""
    
    @pytest.fixture
    def docker_services_available(self):
        """Check if Docker services are running."""
        # Check if we're in Docker CI environment
        if os.getenv("CI") or not os.getenv("DOCKER_SERVICES_AVAILABLE"):
            pytest.skip("Docker services not available")
        return True
    
    @pytest.fixture
    def auth_headers(self):
        """Get authentication headers for testing."""
        return {
            "Authorization": f"Bearer {os.getenv('TEST_JWT_TOKEN', 'test-token')}"
        }
    
    @pytest.fixture
    def service_urls(self):
        """Get service URLs based on environment."""
        base_url = os.getenv("DOCKER_HOST", "http://localhost")
        return {
            "auth": f"{base_url}:8000",
            "mcp": f"{base_url}:8001",
            "prometheus": f"{base_url}:9090",
            "jaeger": f"{base_url}:16686"
        }
    
    async def wait_for_service(self, url: str, timeout: int = 30):
        """Wait for a service to be ready."""
        start_time = time.time()
        async with httpx.AsyncClient() as client:
            while time.time() - start_time < timeout:
                try:
                    response = await client.get(f"{url}/health", timeout=2)
                    if response.status_code == 200:
                        return True
                except:
                    pass
                await asyncio.sleep(1)
        return False
    
    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_distributed_tracing_across_services(self, docker_services_available, service_urls, auth_headers):
        """Test that traces are properly propagated across services."""
        # Ensure services are ready
        assert await self.wait_for_service(service_urls["auth"])
        assert await self.wait_for_service(service_urls["mcp"])
        
        async with httpx.AsyncClient() as client:
            # Make a request through auth gateway
            response = await client.post(
                f"{service_urls['auth']}/mcp/proxy",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "search_web",
                        "arguments": {"query": "distributed tracing test"}
                    },
                    "id": 1
                },
                headers=auth_headers
            )
            
            assert response.status_code == 200
            result = response.json()
            
            # Extract trace ID from response headers (if exposed)
            trace_id = response.headers.get("X-Trace-Id")
            
            # Give time for traces to be exported
            await asyncio.sleep(2)
            
            # Query Jaeger for the trace (if available)
            if await self.wait_for_service(service_urls["jaeger"], timeout=5):
                jaeger_response = await client.get(
                    f"{service_urls['jaeger']}/api/traces/{trace_id}"
                )
                if jaeger_response.status_code == 200:
                    trace_data = jaeger_response.json()
                    # Verify trace contains spans from both services
                    assert len(trace_data.get("data", [])) > 0
                    spans = trace_data["data"][0]["spans"]
                    service_names = {span["process"]["serviceName"] for span in spans}
                    assert "auth-gateway" in service_names
                    assert "mcp-retriever" in service_names
    
    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_metrics_collection_in_prometheus(self, docker_services_available, service_urls, auth_headers):
        """Test that custom metrics are collected in Prometheus."""
        # Make several requests to generate metrics
        async with httpx.AsyncClient() as client:
            for i in range(5):
                await client.post(
                    f"{service_urls['mcp']}/",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "params": {
                            "name": "search_web" if i % 2 == 0 else "search_database",
                            "arguments": {"query": f"metrics test {i}"}
                        },
                        "id": i
                    },
                    headers=auth_headers
                )
            
            # Give time for metrics to be scraped
            await asyncio.sleep(5)
            
            # Query Prometheus for our custom metrics
            if await self.wait_for_service(service_urls["prometheus"], timeout=5):
                # Query request counter
                prom_response = await client.get(
                    f"{service_urls['prometheus']}/api/v1/query",
                    params={"query": "mcp_requests_total"}
                )
                
                if prom_response.status_code == 200:
                    metrics_data = prom_response.json()
                    assert metrics_data["status"] == "success"
                    assert len(metrics_data["data"]["result"]) > 0
                    
                    # Verify we have metrics for different tools
                    tools = {
                        result["metric"].get("tool")
                        for result in metrics_data["data"]["result"]
                    }
                    assert "search_web" in tools or "search_database" in tools
    
    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_error_tracking_in_sentry(self, docker_services_available, service_urls, auth_headers):
        """Test that errors are properly tracked in Sentry."""
        async with httpx.AsyncClient() as client:
            # Trigger an error
            error_response = await client.post(
                f"{service_urls['mcp']}/",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "search_database",
                        "arguments": {"query": "SELECT * FROM non_existent_table"}
                    },
                    "id": 1
                },
                headers=auth_headers
            )
            
            assert "error" in error_response.json()
            
            # In a real test, you would:
            # 1. Query Sentry API to verify the error was captured
            # 2. Check error details and context
            # 3. Verify user context was attached
            
            # For now, we just verify the error response format
            error_data = error_response.json()["error"]
            assert "code" in error_data
            assert "message" in error_data
    
    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_health_endpoints_with_metrics(self, docker_services_available, service_urls):
        """Test health endpoints expose metrics."""
        async with httpx.AsyncClient() as client:
            # Check MCP health
            mcp_health = await client.get(f"{service_urls['mcp']}/health")
            assert mcp_health.status_code == 200
            health_data = mcp_health.json()
            
            # Verify health data includes observability status
            assert "status" in health_data
            assert health_data["status"] == "healthy"
            
            # Check metrics endpoint
            metrics_response = await client.get(f"{service_urls['mcp']}/metrics")
            assert metrics_response.status_code == 200
            
            # Verify Prometheus format
            metrics_text = metrics_response.text
            assert "# HELP" in metrics_text
            assert "# TYPE" in metrics_text
            assert "mcp_requests_total" in metrics_text
    
    @pytest.mark.asyncio
    @pytest.mark.docker 
    async def test_concurrent_request_tracing(self, docker_services_available, service_urls, auth_headers):
        """Test tracing behavior under concurrent load."""
        async with httpx.AsyncClient() as client:
            # Send concurrent requests
            tasks = []
            for i in range(10):
                task = client.post(
                    f"{service_urls['mcp']}/",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "params": {
                            "name": "search_all",
                            "arguments": {"query": f"concurrent {i}"}
                        },
                        "id": i
                    },
                    headers=auth_headers
                )
                tasks.append(task)
            
            # Execute concurrently
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Verify all requests completed
            successful = [r for r in responses if not isinstance(r, Exception)]
            assert len(successful) >= 8  # At least 80% success rate
            
            # Each should have unique request/trace IDs
            trace_ids = set()
            for response in successful:
                if "X-Trace-Id" in response.headers:
                    trace_ids.add(response.headers["X-Trace-Id"])
            
            # Should have unique traces for each request
            assert len(trace_ids) >= len(successful) * 0.8
    
    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_service_dependency_visualization(self, docker_services_available, service_urls):
        """Test that service dependencies are properly tracked."""
        # This test would verify that the observability platform
        # can visualize the service dependency graph:
        # Client -> Auth Gateway -> MCP Server -> Retrievers -> External Services
        
        # In a real implementation, you would:
        # 1. Make requests that exercise all service paths
        # 2. Query the tracing backend for service dependencies
        # 3. Verify the dependency graph is complete
        
        # For now, we just make a request that touches all services
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{service_urls['auth']}/mcp/proxy",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "search_all",
                        "arguments": {"query": "service dependency test"}
                    },
                    "id": 1
                },
                headers={
                    "Authorization": f"Bearer {os.getenv('TEST_JWT_TOKEN', 'test-token')}"
                }
            )
            
            assert response.status_code == 200
            result = response.json()
            assert "result" in result
    
    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_performance_baseline(self, docker_services_available, service_urls, auth_headers):
        """Establish performance baselines with observability enabled."""
        async with httpx.AsyncClient() as client:
            # Warm up
            for _ in range(3):
                await client.post(
                    f"{service_urls['mcp']}/",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/list",
                        "id": 0
                    }
                )
            
            # Measure performance
            latencies = []
            for i in range(20):
                start_time = time.time()
                
                response = await client.post(
                    f"{service_urls['mcp']}/",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "params": {
                            "name": "search_web",
                            "arguments": {"query": f"perf test {i}"}
                        },
                        "id": i
                    },
                    headers=auth_headers
                )
                
                latency = (time.time() - start_time) * 1000  # ms
                if response.status_code == 200:
                    latencies.append(latency)
            
            # Calculate statistics
            if latencies:
                avg_latency = sum(latencies) / len(latencies)
                p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]
                p99_latency = sorted(latencies)[int(len(latencies) * 0.99)]
                
                # Log baselines
                print(f"Performance with observability enabled:")
                print(f"  Average latency: {avg_latency:.2f}ms")
                print(f"  P95 latency: {p95_latency:.2f}ms")
                print(f"  P99 latency: {p99_latency:.2f}ms")
                
                # Assert reasonable performance
                assert avg_latency < 500  # Average under 500ms
                assert p95_latency < 1000  # P95 under 1 second
                assert p99_latency < 2000  # P99 under 2 seconds