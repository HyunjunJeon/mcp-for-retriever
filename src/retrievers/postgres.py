"""
PostgreSQL 데이터베이스 리트리버 구현

이 모듈은 PostgreSQL 데이터베이스를 사용하여 SQL 쿼리 및 전체 텍스트 검색
기능을 제공하는 리트리버를 구현합니다.

주요 기능:
    - SQL 쿼리 직접 실행
    - 전체 텍스트 검색 (ILIKE)
    - 비동기 연결 풀 관리
    - 트랜잭션 지원
    - 준비된 문(Prepared Statement) 지원

환경 변수:
    POSTGRES_DSN: PostgreSQL 연결 문자열 (필수)
    예: postgresql://user:password@localhost:5432/dbname
"""

from typing import AsyncIterator, Any, Optional
from contextlib import asynccontextmanager
import asyncpg

from src.retrievers.base import (
    Retriever,
    RetrieverHealth,
    ConnectionError,
    QueryError,
    QueryResult,
    RetrieverConfig,
)
from src.utils.connection_manager import PostgreSQLPoolManager


class PostgresRetriever(Retriever):
    """
    PostgreSQL 데이터베이스를 사용하는 리트리버 구현체

    PostgreSQL의 강력한 기능을 활용하여 SQL 쿼리와 전체 텍스트 검색을
    지원합니다. asyncpg 라이브러리를 사용하여 고성능 비동기 처리를 보장합니다.

    Attributes:
        dsn (str): PostgreSQL 연결 문자열
        min_connections (int): 최소 연결 풀 크기
        max_connections (int): 최대 연결 풀 크기
        timeout (int): 연결 타임아웃 (초)
        _pool (Pool): 비동기 연결 풀
    """

    def __init__(self, config: RetrieverConfig):
        """
        PostgreSQL 리트리버 초기화

        설정 정보를 받아 PostgreSQL 연결을 위한 준비를 합니다.

        Args:
            config: 설정 딕셔너리
                - dsn (str): PostgreSQL 연결 문자열 (필수)
                    형식: postgresql://[user[:password]@][host][:port][/dbname][?param=value]
                    예: postgresql://user:pass@localhost:5432/mydb
                - min_connections (int): 최소 연결 풀 크기 (기본값: 1)
                    항상 유지할 최소 연결 수
                - max_connections (int): 최대 연결 풀 크기 (기본값: 10)
                    동시에 사용할 수 있는 최대 연결 수
                - timeout (int): 연결 타임아웃 (초 단위, 기본값: 30)

        Raises:
            ValueError: dsn이 제공되지 않은 경우
        """
        super().__init__(config)

        # 설정 추출 및 검증
        self.dsn = config.get("dsn")
        if not self.dsn:
            raise ValueError("dsn is required for PostgresRetriever")

        # Connection pool manager configuration
        pool_config = {
            "dsn": self.dsn,
            "min_size": config.get("min_connections", 10),  # Increased default
            "max_size": config.get("max_connections", 50),  # Increased default
            "timeout": config.get("timeout", 30),
            "command_timeout": config.get("command_timeout", 10),
            "max_queries": config.get("max_queries", 50000),
            "max_inactive_connection_lifetime": config.get(
                "max_inactive_connection_lifetime", 300
            ),
        }

        # Use connection pool manager
        self._pool_manager = PostgreSQLPoolManager(pool_config)

    async def connect(self) -> None:
        """
        PostgreSQL 연결 풀 생성

        Connection pool manager를 통해 최적화된 연결 풀을 초기화합니다.
        자동 크기 조정, 메트릭 수집, 연결 재사용이 포함됩니다.

        Raises:
            ConnectionError: PostgreSQL 연결 실패 시
                - 잘못된 DSN 형식
                - 네트워크 오류
                - 인증 실패
                - 데이터베이스 서버 중단
        """
        try:
            # Initialize connection pool through manager
            await self._pool_manager.initialize()

            # 연결 테스트
            await self._test_connection()

            self._connected = True
            self._log_operation("connect", status="success")

            # Log pool metrics
            health = await self._pool_manager.health_check()
            self._log_operation("pool_health", **health)

        except Exception as e:
            self._connected = False
            self._log_operation("connect", status="failed", error=str(e))
            raise ConnectionError(
                f"Failed to connect to PostgreSQL: {e}", "PostgresRetriever"
            )

    async def disconnect(self) -> None:
        """
        PostgreSQL 연결 종료

        Connection pool manager를 통해 연결 풀을 안전하게 종료합니다.
        모든 활성 연결이 정리될 때까지 대기합니다.
        """
        await self._pool_manager.close()

        self._connected = False
        self._log_operation(
            "disconnect",
            total_requests=self._pool_manager.metrics.total_requests,
            reuse_rate=self._pool_manager.metrics.calculate_reuse_rate(),
        )

    async def retrieve(
        self, query: str, limit: int = 10, **kwargs: Any
    ) -> AsyncIterator[QueryResult]:
        """
        쿼리 실행 및 결과 반환

        SQL 쿼리 또는 텍스트 검색을 실행하고 결과를 비동기 스트리밍으로 반환합니다.
        SQL 키워드로 시작하는 문자열은 SQL 쿼리로, 그렇지 않으면 텍스트 검색으로 처리합니다.

        Args:
            query (str): SQL 쿼리 또는 검색 텍스트
            limit (int): 반환할 최대 결과 수 (기본값: 10)
            **kwargs: 추가 매개변수
                - table (str): 텍스트 검색할 테이블 이름
                - search_columns (list[str]): 검색할 컴럼 리스트
                - filters (dict[str, Any]): 추가 WHERE 조건
                - params (list): SQL 쿼리 매개변수 (Prepared Statement)

        Yields:
            QueryResult: 결과 딕셔너리
                - 모든 컴럼 필드와 값
                - source: 데이터 출처 ("postgres")

        Raises:
            ConnectionError: 연결되지 않은 경우
            QueryError: 쿼리 실행 실패 시
                - SQL 구문 오류
                - 테이블/컴럼이 없는 경우
                - 권한 부족
        """
        if not self._connected:
            raise ConnectionError("Not connected to PostgreSQL", "PostgresRetriever")

        try:
            # SQL 쿼리인지 텍스트 검색인지 판단
            if self._is_sql_query(query):
                # SQL 쿼리: LIMIT 절 추가
                sql_query = self._add_limit_to_query(query, limit)
                params = kwargs.get("params", [])
            else:
                # 텍스트 검색: 전체 텍스트 검색 쿼리 생성
                sql_query = self._build_text_search_query(
                    query,
                    kwargs.get("table"),
                    kwargs.get("search_columns", []),
                    kwargs.get("filters", {}),
                    limit,
                )
                params = [query]  # 검색 텍스트를 매개변수로

            # 쿼리 실행
            async with self._pool_manager.acquire() as conn:
                if self._is_sql_query(query) and limit not in params:
                    # SQL 쿼리에 LIMIT 플레이스홀더가 있는 경우
                    results = await conn.fetch(sql_query, limit)
                else:
                    results = await conn.fetch(sql_query, *params)

                # 결과를 하나씩 yield
                for row in results:
                    yield self._format_result(dict(row))

        except asyncpg.PostgresError as e:
            self._log_operation("retrieve", status="failed", error=str(e))
            raise QueryError(f"Query failed: {e}", "PostgresRetriever")

    async def health_check(self) -> RetrieverHealth:
        """
        PostgreSQL 연결 상태 확인

        데이터베이스 연결 상태와 연결 풀 정보를 확인합니다.

        Returns:
            RetrieverHealth: 현재 상태 정보
                - healthy: 정상 작동 여부
                - service_name: "PostgresRetriever"
                - details: 연결 상태, 풀 크기, 사용 가능한 연결 수
                - error: 에러 메시지 (문제 발생 시)
        """
        if not self._connected:
            return RetrieverHealth(
                healthy=False,
                service_name="PostgresRetriever",
                details={"connected": False},
                error="Not connected",
            )

        try:
            # Connection pool manager의 health check 사용
            pool_health = await self._pool_manager.health_check()

            return RetrieverHealth(
                healthy=pool_health["status"] == "healthy",
                service_name="PostgresRetriever",
                details={
                    "connected": True,
                    "pool_size": pool_health.get("pool_size", 0),
                    "pool_free": pool_health.get("idle_connections", 0),
                    "active_connections": pool_health.get("active_connections", 0),
                    "reuse_rate": pool_health.get("reuse_rate", 0),
                    "avg_wait_time_ms": pool_health.get("avg_wait_time_ms", 0),
                },
            )

        except Exception as e:
            return RetrieverHealth(
                healthy=False,
                service_name="PostgresRetriever",
                details={"connected": self._connected},
                error=str(e),
            )

    async def execute(self, query: str, *args: Any) -> None:
        """
        쓰기 작업 실행 (INSERT, UPDATE, DELETE)

        데이터를 변경하는 SQL 문을 실행합니다.
        자동으로 트랜잭션에 감싸여 실행됩니다.

        Args:
            query (str): 실행할 SQL 쿼리
            *args: 쿼리 매개변수
                플레이스홀더 $1, $2 등에 대응하는 값들

        Raises:
            ConnectionError: 연결되지 않은 경우
            QueryError: 실행 실패 시
                - SQL 구문 오류
                - 제약 조건 위반
                - 권한 부족
        """
        if not self._connected:
            raise ConnectionError("Not connected to PostgreSQL", "PostgresRetriever")

        try:
            async with self._pool_manager.acquire() as conn:
                await conn.execute(query, *args)

        except asyncpg.PostgresError as e:
            raise QueryError(f"Execute failed: {e}", "PostgresRetriever")

    async def execute_returning(
        self, query: str, *args: Any
    ) -> Optional[dict[str, Any]]:
        """
        RETURNING 절이 있는 쓰기 작업 실행 (INSERT, UPDATE, DELETE)

        데이터를 변경하고 결과를 반환하는 SQL 문을 실행합니다.

        Args:
            query (str): RETURNING 절이 포함된 SQL 쿼리
            *args: 쿼리 매개변수

        Returns:
            반환된 레코드 (dict) 또는 None

        Raises:
            ConnectionError: 연결되지 않은 경우
            QueryError: 실행 실패 시
        """
        if not self._connected:
            raise ConnectionError("Not connected to PostgreSQL", "PostgresRetriever")

        try:
            async with self._pool_manager.acquire() as conn:
                result = await conn.fetchrow(query, *args)
                return dict(result) if result else None

        except asyncpg.PostgresError as e:
            raise QueryError(f"Execute failed: {e}", "PostgresRetriever")

    async def execute_returning_scalar(self, query: str, *args: Any) -> Any:
        """
        스칼라 값을 반환하는 쓰기 작업 실행

        단일 값을 반환하는 SQL 문을 실행합니다.

        Args:
            query (str): RETURNING 절이 포함된 SQL 쿼리
            *args: 쿼리 매개변수

        Returns:
            반환된 스칼라 값

        Raises:
            ConnectionError: 연결되지 않은 경우
            QueryError: 실행 실패 시
        """
        if not self._connected:
            raise ConnectionError("Not connected to PostgreSQL", "PostgresRetriever")

        try:
            async with self._pool_manager.acquire() as conn:
                return await conn.fetchval(query, *args)

        except asyncpg.PostgresError as e:
            raise QueryError(f"Execute failed: {e}", "PostgresRetriever")

    async def compose_insert_query(
        self, table: str, data: dict[str, Any], returning: Optional[str] = "*"
    ) -> tuple[str, list[Any]]:
        """
        안전한 INSERT 쿼리 생성

        SQL 인젝션을 방지하기 위해 테이블명과 컬럼명을 안전하게 이스케이핑합니다.

        Args:
            table: 테이블 이름
            data: 삽입할 데이터 (컬럼명: 값)
            returning: RETURNING 절 (기본값: "*")

        Returns:
            (쿼리 문자열, 값 리스트) 튜플
        """
        if not self._connected:
            raise ConnectionError("Not connected to PostgreSQL", "PostgresRetriever")

        columns = list(data.keys())
        values = list(data.values())

        # asyncpg는 identifier escaping을 자동으로 처리
        # 파라미터 플레이스홀더 생성
        placeholders = [f"${i + 1}" for i in range(len(values))]

        # 안전한 identifier escaping을 위해 connection의 quote_ident 사용
        async with self._pool_manager.acquire() as conn:
            # 테이블명과 컬럼명을 안전하게 이스케이핑
            quoted_table = conn._protocol.get_settings().quote_ident(table)
            quoted_columns = [
                conn._protocol.get_settings().quote_ident(col) for col in columns
            ]

            query = f"""
                INSERT INTO {quoted_table} ({", ".join(quoted_columns)})
                VALUES ({", ".join(placeholders)})
            """

            if returning:
                query += f" RETURNING {returning}"

            return query, values

    async def compose_update_query(
        self,
        table: str,
        data: dict[str, Any],
        where_clause: str,
        where_values: list[Any],
        returning: Optional[str] = "*",
    ) -> tuple[str, list[Any]]:
        """
        안전한 UPDATE 쿼리 생성

        Args:
            table: 테이블 이름
            data: 업데이트할 데이터
            where_clause: WHERE 절 (예: "id = $1")
            where_values: WHERE 절의 파라미터 값
            returning: RETURNING 절

        Returns:
            (쿼리 문자열, 전체 값 리스트) 튜플
        """
        if not self._connected:
            raise ConnectionError("Not connected to PostgreSQL", "PostgresRetriever")

        set_clauses = []
        values = []

        async with self._pool_manager.acquire() as conn:
            quoted_table = conn._protocol.get_settings().quote_ident(table)

            # SET 절 구성
            for i, (col, val) in enumerate(data.items()):
                quoted_col = conn._protocol.get_settings().quote_ident(col)
                set_clauses.append(f"{quoted_col} = ${i + 1}")
                values.append(val)

            # WHERE 절의 플레이스홀더 번호 조정
            offset = len(values)
            adjusted_where = where_clause
            for i in range(len(where_values)):
                # $1, $2 등을 새로운 번호로 교체
                adjusted_where = adjusted_where.replace(
                    f"${i + 1}", f"${i + 1 + offset}"
                )

            # WHERE 절 값 추가
            values.extend(where_values)

            query = f"""
                UPDATE {quoted_table}
                SET {", ".join(set_clauses)}
                WHERE {adjusted_where}
            """

            if returning:
                query += f" RETURNING {returning}"

            return query, values

    async def compose_delete_query(
        self,
        table: str,
        where_clause: str,
        where_values: list[Any],
        returning: Optional[str] = "id",
    ) -> tuple[str, list[Any]]:
        """
        안전한 DELETE 쿼리 생성

        Args:
            table: 테이블 이름
            where_clause: WHERE 절
            where_values: WHERE 절의 파라미터 값
            returning: RETURNING 절

        Returns:
            (쿼리 문자열, 값 리스트) 튜플
        """
        if not self._connected:
            raise ConnectionError("Not connected to PostgreSQL", "PostgresRetriever")

        async with self._pool_manager.acquire() as conn:
            quoted_table = conn._protocol.get_settings().quote_ident(table)

            query = f"""
                DELETE FROM {quoted_table}
                WHERE {where_clause}
            """

            if returning:
                query += f" RETURNING {returning}"

            return query, where_values

    @asynccontextmanager
    async def transaction(self):
        """
        데이터베이스 트랜잭션 컨텍스트 생성

        여러 작업을 하나의 트랜잭션으로 묶어 처리합니다.
        모든 작업이 성공해야 커밋되고, 에러 발생 시 자동 롤백됩니다.

        Yields:
            asyncpg.Connection: 트랜잭션 컨텍스트 내의 연결 객체

        Raises:
            ConnectionError: 연결되지 않은 경우

        Example:
            ```python
            async with retriever.transaction() as conn:
                await conn.execute("INSERT INTO users (name) VALUES ($1)", "Alice")
                await conn.execute("UPDATE counts SET value = value + 1")
            # 여기서 자동 커밋
            ```
        """
        if not self._connected:
            raise ConnectionError("Not connected to PostgreSQL", "PostgresRetriever")

        async with self._pool_manager.acquire() as conn:
            async with conn.transaction():
                yield conn

    async def retrieve_prepared(
        self, query: str, *args: Any, limit: int = 10
    ) -> AsyncIterator[QueryResult]:
        """
        준비된 문(Prepared Statement) 실행 및 결과 반환

        SQL 인젝션 공격을 방지하고 성능을 향상시키기 위해
        준비된 문을 사용합니다. 동일한 쿼리를 여러 번 실행할 때 효율적입니다.

        Args:
            query (str): SQL 쿼리 (플레이스홀더 $1, $2 등 포함)
            *args: 쿼리 매개변수
            limit (int): 최대 결과 수 (기본값: 10)

        Yields:
            QueryResult: 쿼리 결과

        Raises:
            ConnectionError: 연결되지 않은 경우
            QueryError: 쿼리 실행 실패 시
        """
        if not self._connected:
            raise ConnectionError("Not connected to PostgreSQL", "PostgresRetriever")

        try:
            async with self._pool_manager.acquire() as conn:
                # 문장 준비 (파싱 및 최적화)
                stmt = await conn.prepare(query)

                # 실행 및 결과 가져오기
                results = await stmt.fetch(*args)

                # 제한된 수만큼 결과 yield
                for i, row in enumerate(results):
                    if i >= limit:
                        break
                    yield self._format_result(dict(row))

        except asyncpg.PostgresError as e:
            raise QueryError(f"Prepared query failed: {e}", "PostgresRetriever")

    async def _test_connection(self) -> None:
        """
        데이터베이스 연결 테스트

        간단한 SELECT 문을 실행하여 연결 상태를 확인합니다.

        Raises:
            Exception: 연결 테스트 실패 시
        """
        # Connection pool manager를 통한 연결 테스트
        async with self._pool_manager.acquire() as conn:
            await conn.fetchrow("SELECT 1")

    def _is_sql_query(self, query: str) -> bool:
        """
        쿼리가 SQL 문인지 확인

        SQL 키워드로 시작하는지 확인하여 SQL 쿼리와
        텍스트 검색을 구분합니다.

        Args:
            query (str): 검사할 쿼리 문자열

        Returns:
            bool: SQL 쿼리면 True, 텍스트 검색이면 False
        """
        # 주요 SQL 키워드
        sql_keywords = ["SELECT", "INSERT", "UPDATE", "DELETE", "WITH"]
        query_upper = query.strip().upper()
        return any(query_upper.startswith(kw) for kw in sql_keywords)

    def _add_limit_to_query(self, query: str, limit: int) -> str:
        """
        SQL 쿼리에 LIMIT 절 추가

        LIMIT이 없는 쿼리에 자동으로 LIMIT를 추가하여
        과도한 결과 반환을 방지합니다.

        Args:
            query (str): SQL 쿼리
            limit (int): 결과 제한

        Returns:
            str: LIMIT 절이 추가된 쿼리
                $1 플레이스홀더를 사용하여 SQL 인젝션 방지
        """
        query_upper = query.strip().upper()
        if "LIMIT" not in query_upper:
            # 세미콜론 제거 후 LIMIT 추가
            return f"{query.rstrip(';')} LIMIT ${1}"
        return query

    def _build_text_search_query(
        self,
        search_text: str,
        table: Optional[str],
        search_columns: list[str],
        filters: dict[str, Any],
        limit: int,
    ) -> str:
        """
        전체 텍스트 검색 쿼리 생성

        ILIKE 연산자를 사용하여 대소문자 구분 없는 텍스트 검색
        쿼리를 생성합니다. 와일드카드 패턴으로 부분 문자열 검색을 지원합니다.

        Args:
            search_text (str): 검색할 텍스트
            table (Optional[str]): 검색할 테이블 이름
            search_columns (list[str]): 검색할 컴럼 리스트
            filters (dict[str, Any]): 추가 필터 조건
            limit (int): 결과 제한

        Returns:
            str: 텍스트 검색용 SQL 쿼리
        """
        if not table:
            # 테이블이 지정되지 않은 경우 에러 반환
            return "SELECT 'No table specified for text search' as error LIMIT 0"

        # 검색 컴럼 조건 생성
        if search_columns:
            # ILIKE를 사용한 부분 문자열 검색
            # $1은 search_text 매개변수로 대체됨
            search_conditions = [
                f"{col} ILIKE '%' || $1 || '%'" for col in search_columns
            ]
            where_clause = f"({' OR '.join(search_conditions)})"
        else:
            # 컴럼이 지정되지 않은 경우 (실제 구현에서는 스키마 검사 필요)
            where_clause = "true"

        # 추가 필터 조건 적용
        if filters:
            filter_conditions = [f"{key} = {value!r}" for key, value in filters.items()]
            where_clause = f"{where_clause} AND {' AND '.join(filter_conditions)}"

        return f"""
            SELECT * FROM {table}
            WHERE {where_clause}
            LIMIT {limit}
        """

    def _format_result(self, row: dict[str, Any]) -> QueryResult:
        """
        데이터베이스 행을 표준 QueryResult 형식으로 변환

        PostgreSQL의 결과를 MCP 서버의 표준 결과 형식으로
        변환합니다. 모든 리트리버가 동일한 형식을 사용하도록 합니다.

        Args:
            row (dict[str, Any]): 데이터베이스 행

        Returns:
            QueryResult: 표준화된 결과
                - 모든 원본 컴럼과 값
                - source: 데이터 출처 ("postgres" 고정)
        """
        # 원본 행 데이터에 소스 정보 추가
        result = dict(row)
        result["source"] = "postgres"
        return result
