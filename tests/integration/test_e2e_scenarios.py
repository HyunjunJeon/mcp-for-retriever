"""End-to-end integration tests with mocked external services."""

import asyncio
import os
from typing import Any, Dict
from unittest.mock import patch, AsyncMock, MagicMock
import pytest
from fastapi.testclient import TestClient

from src.auth.server import app as auth_app
from src.server import create_server, retrievers
from src.retrievers.factory import RetrieverFactory
from tests.fixtures.mock_retriever import MockRetriever


class TestE2EScenarios:
    """End-to-end tests simulating real-world usage scenarios."""
    
    @pytest.fixture
    def auth_app(self):
        """Get auth app instance."""
        return auth_app
    
    @pytest.fixture
    def auth_client(self, auth_app):
        """Create auth test client."""
        return TestClient(auth_app)
    
    @pytest.fixture
    async def setup_mock_services(self):
        """Set up all mock services."""
        retrievers.clear()
        
        # Mock environment variables
        env_vars = {
            'TAVILY_API_KEY': 'test-tavily-key',
            'POSTGRES_DSN': 'postgresql://test:pass@localhost/testdb',
            'QDRANT_HOST': 'localhost',
            'QDRANT_PORT': '6333',
            'JWT_SECRET_KEY': 'test-secret-key'
        }
        
        with patch.dict(os.environ, env_vars):
            # Mock Tavily API
            with patch('src.retrievers.tavily.AsyncClient') as mock_tavily:
                tavily_instance = AsyncMock()
                tavily_instance.search.return_value = MagicMock(
                    results=[
                        MagicMock(
                            title="AI Research Paper",
                            url="https://arxiv.org/paper1",
                            content="Latest AI research findings...",
                            score=0.92
                        ),
                        MagicMock(
                            title="Machine Learning Tutorial",
                            url="https://ml-tutorial.com",
                            content="Introduction to ML concepts...",
                            score=0.88
                        )
                    ]
                )
                mock_tavily.return_value = tavily_instance
                
                # Mock PostgreSQL
                with patch('src.retrievers.postgres.asyncpg.create_pool') as mock_pg:
                    pg_pool = AsyncMock()
                    pg_connection = AsyncMock()
                    
                    # Mock connection acquisition
                    pg_pool.acquire.return_value.__aenter__.return_value = pg_connection
                    
                    # Mock query results
                    pg_connection.fetch.return_value = [
                        {"id": 1, "title": "Database Tutorial", "content": "SQL basics"},
                        {"id": 2, "title": "Advanced SQL", "content": "Complex queries"}
                    ]
                    
                    mock_pg.return_value = pg_pool
                    
                    # Mock Qdrant
                    with patch('src.retrievers.qdrant.QdrantClient') as mock_qdrant:
                        qdrant_instance = AsyncMock()
                        
                        # Mock collection info
                        qdrant_instance.get_collections.return_value = MagicMock(
                            collections=[
                                MagicMock(name="documents"),
                                MagicMock(name="embeddings")
                            ]
                        )
                        
                        # Mock search results
                        qdrant_instance.search.return_value = [
                            MagicMock(
                                id="vec-1",
                                score=0.89,
                                payload={
                                    "text": "Neural networks fundamentals",
                                    "category": "AI"
                                }
                            )
                        ]
                        
                        mock_qdrant.return_value = qdrant_instance
                        
                        yield {
                            "tavily": tavily_instance,
                            "postgres": pg_connection,
                            "qdrant": qdrant_instance
                        }
    
    async def test_research_assistant_scenario(self, auth_client, setup_mock_services):
        """Test a research assistant scenario using all retrievers."""
        # 1. User registration and login
        register_response = auth_client.post(
            "/api/v1/auth/register",
            json={
                "email": "researcher@university.edu",
                "password": "Research2024!",
                "name": "Dr. Researcher"
            }
        )
        assert register_response.status_code == 201
        
        login_response = auth_client.post(
            "/api/v1/auth/token",
            data={
                "username": "researcher@university.edu",
                "password": "Research2024!"
            }
        )
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # 2. Research query across all sources
        research_query = "machine learning neural networks fundamentals"
        
        # Start MCP server retrievers
        from src.server import startup
        await startup()
        
        # 3. Search all sources for comprehensive results
        all_search_request = {
            "jsonrpc": "2.0",
            "method": "search_all",
            "params": {
                "query": research_query,
                "limit": 10
            },
            "id": 1
        }
        
        with patch('src.auth.server.mcp_proxy.execute_request') as mock_proxy:
            # Simulate MCP proxy forwarding to actual tools
            async def simulate_search_all(*args, **kwargs):
                from src.server import search_all_tool
                result = await search_all_tool(research_query, limit=10)
                return {
                    "jsonrpc": "2.0",
                    "result": result,
                    "id": 1
                }
            
            mock_proxy.side_effect = simulate_search_all
            
            response = auth_client.post(
                "/api/v1/mcp/execute",
                json=all_search_request,
                headers=headers
            )
            
            assert response.status_code == 200
            result = response.json()
            
            # Verify comprehensive results
            assert result["result"]["status"] == "success"
            assert "tavily" in result["result"]["results"]
            assert "postgres" in result["result"]["results"]
            assert "qdrant" in result["result"]["results"]
            
            # Verify content from each source
            web_results = result["result"]["results"]["tavily"]
            assert len(web_results) > 0
            assert any("AI Research" in r.get("title", "") for r in web_results)
            
            db_results = result["result"]["results"]["postgres"]
            assert len(db_results) > 0
            
            vector_results = result["result"]["results"]["qdrant"]
            assert len(vector_results) > 0
            assert any("neural networks" in r.get("text", "").lower() for r in vector_results)
    
    async def test_data_analyst_scenario(self, auth_client, setup_mock_services):
        """Test a data analyst scenario focusing on database queries."""
        # 1. Analyst login
        auth_client.post(
            "/api/v1/auth/register",
            json={
                "email": "analyst@company.com",
                "password": "DataAnalyst2024!",
                "name": "Data Analyst"
            }
        )
        
        login_response = auth_client.post(
            "/api/v1/auth/token",
            data={
                "username": "analyst@company.com",
                "password": "DataAnalyst2024!"
            }
        )
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Start services
        from src.server import startup
        await startup()
        
        # 2. Complex SQL query
        sql_request = {
            "jsonrpc": "2.0",
            "method": "search_database",
            "params": {
                "query": """
                    SELECT p.id, p.title, p.content, COUNT(c.id) as comment_count
                    FROM posts p
                    LEFT JOIN comments c ON p.id = c.post_id
                    WHERE p.created_at > '2024-01-01'
                    GROUP BY p.id
                    ORDER BY comment_count DESC
                """,
                "limit": 20
            },
            "id": 1
        }
        
        with patch('src.auth.server.mcp_proxy.execute_request') as mock_proxy:
            async def simulate_db_search(*args, **kwargs):
                from src.server import search_database_tool
                result = await search_database_tool(
                    query=sql_request["params"]["query"],
                    limit=20
                )
                return {
                    "jsonrpc": "2.0",
                    "result": result,
                    "id": 1
                }
            
            mock_proxy.side_effect = simulate_db_search
            
            response = auth_client.post(
                "/api/v1/mcp/execute",
                json=sql_request,
                headers=headers
            )
            
            assert response.status_code == 200
            result = response.json()
            assert result["result"]["status"] == "success"
            assert len(result["result"]["results"]) > 0
    
    async def test_content_discovery_scenario(self, auth_client, setup_mock_services):
        """Test content discovery using vector search."""
        # Setup user
        auth_client.post(
            "/api/v1/auth/register",
            json={
                "email": "content@platform.com",
                "password": "Content2024!",
                "name": "Content Manager"
            }
        )
        
        login_response = auth_client.post(
            "/api/v1/auth/token",
            data={
                "username": "content@platform.com",
                "password": "Content2024!"
            }
        )
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Start services
        from src.server import startup
        await startup()
        
        # Find similar content
        vector_request = {
            "jsonrpc": "2.0",
            "method": "search_vectors",
            "params": {
                "query": "Introduction to deep learning and neural networks",
                "collection": "documents",
                "limit": 5,
                "score_threshold": 0.8
            },
            "id": 1
        }
        
        with patch('src.auth.server.mcp_proxy.execute_request') as mock_proxy:
            async def simulate_vector_search(*args, **kwargs):
                from src.server import search_vectors_tool
                result = await search_vectors_tool(
                    query=vector_request["params"]["query"],
                    collection="documents",
                    limit=5,
                    score_threshold=0.8
                )
                return {
                    "jsonrpc": "2.0",
                    "result": result,
                    "id": 1
                }
            
            mock_proxy.side_effect = simulate_vector_search
            
            response = auth_client.post(
                "/api/v1/mcp/execute",
                json=vector_request,
                headers=headers
            )
            
            assert response.status_code == 200
            result = response.json()
            assert result["result"]["status"] == "success"
            
            # Verify high-quality matches
            for item in result["result"]["results"]:
                assert item.get("score", 0) >= 0.8
    
    async def test_batch_processing_scenario(self, auth_client, setup_mock_services):
        """Test batch processing for multiple queries."""
        # Setup
        auth_client.post(
            "/api/v1/auth/register",
            json={
                "email": "batch@processor.com",
                "password": "Batch2024!",
                "name": "Batch Processor"
            }
        )
        
        login_response = auth_client.post(
            "/api/v1/auth/token",
            data={
                "username": "batch@processor.com",
                "password": "Batch2024!"
            }
        )
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Batch request with different query types
        batch_request = [
            {
                "jsonrpc": "2.0",
                "method": "search_web",
                "params": {"query": "latest AI trends 2024", "limit": 3},
                "id": 1
            },
            {
                "jsonrpc": "2.0",
                "method": "search_database",
                "params": {"query": "SELECT * FROM trends WHERE year = 2024", "limit": 5},
                "id": 2
            },
            {
                "jsonrpc": "2.0",
                "method": "search_vectors",
                "params": {
                    "query": "artificial intelligence trends",
                    "collection": "documents",
                    "limit": 3
                },
                "id": 3
            }
        ]
        
        with patch('src.auth.server.mcp_proxy.execute_batch_request') as mock_batch:
            mock_batch.return_value = [
                {
                    "jsonrpc": "2.0",
                    "result": {"status": "success", "results": [], "count": 0},
                    "id": i
                }
                for i in range(1, 4)
            ]
            
            response = auth_client.post(
                "/api/v1/mcp/execute",
                json=batch_request,
                headers=headers
            )
            
            assert response.status_code == 200
            results = response.json()
            assert len(results) == 3
            assert all(r["jsonrpc"] == "2.0" for r in results)
            assert [r["id"] for r in results] == [1, 2, 3]
    
    async def test_error_recovery_scenario(self, auth_client, setup_mock_services):
        """Test system behavior during partial failures."""
        # Setup
        auth_client.post(
            "/api/v1/auth/register",
            json={
                "email": "resilient@system.com",
                "password": "Resilient2024!",
                "name": "Resilient User"
            }
        )
        
        login_response = auth_client.post(
            "/api/v1/auth/token",
            data={
                "username": "resilient@system.com",
                "password": "Resilient2024!"
            }
        )
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Make one service fail
        setup_mock_services["postgres"].fetch.side_effect = Exception("Database connection lost")
        
        # Try search all
        request = {
            "jsonrpc": "2.0",
            "method": "search_all",
            "params": {"query": "resilience test", "limit": 5},
            "id": 1
        }
        
        with patch('src.auth.server.mcp_proxy.execute_request') as mock_proxy:
            from src.server import startup
            await startup()
            
            async def simulate_partial_failure(*args, **kwargs):
                from src.server import search_all_tool
                result = await search_all_tool("resilience test", limit=5)
                return {
                    "jsonrpc": "2.0",
                    "result": result,
                    "id": 1
                }
            
            mock_proxy.side_effect = simulate_partial_failure
            
            response = auth_client.post(
                "/api/v1/mcp/execute",
                json=request,
                headers=headers
            )
            
            assert response.status_code == 200
            result = response.json()
            
            # Should still get results from working services
            assert result["result"]["status"] == "success"
            assert "tavily" in result["result"]["results"]
            assert "qdrant" in result["result"]["results"]
            
            # Should have error for failed service
            assert "postgres" in result["result"]["errors"]
    
    async def test_performance_monitoring_scenario(self, auth_client, setup_mock_services):
        """Test performance with concurrent users."""
        import time
        import concurrent.futures
        
        # Create multiple users
        users = []
        for i in range(5):
            auth_client.post(
                "/api/v1/auth/register",
                json={
                    "email": f"user{i}@perf.com",
                    "password": "Perf2024!",
                    "name": f"User {i}"
                }
            )
            
            login_resp = auth_client.post(
                "/api/v1/auth/token",
                data={
                    "username": f"user{i}@perf.com",
                    "password": "Perf2024!"
                }
            )
            users.append(login_resp.json()["access_token"])
        
        # Define concurrent requests
        def make_request(user_token, query_id):
            start_time = time.time()
            
            request = {
                "jsonrpc": "2.0",
                "method": "search_web",
                "params": {"query": f"performance test {query_id}", "limit": 5},
                "id": query_id
            }
            
            response = auth_client.post(
                "/api/v1/mcp/execute",
                json=request,
                headers={"Authorization": f"Bearer {user_token}"}
            )
            
            elapsed = time.time() - start_time
            return response.status_code, elapsed
        
        # Execute concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for i in range(20):  # 20 total requests
                user_token = users[i % len(users)]
                future = executor.submit(make_request, user_token, i)
                futures.append(future)
            
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        # Verify performance
        status_codes = [r[0] for r in results]
        response_times = [r[1] for r in results]
        
        assert all(code == 200 for code in status_codes)
        assert max(response_times) < 5.0  # All requests complete within 5 seconds
        assert sum(response_times) / len(response_times) < 2.0  # Average under 2 seconds