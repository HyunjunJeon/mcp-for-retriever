"""
JWT 토큰 관리 서비스

이 모듈은 JWT(JSON Web Token) 기반 인증 시스템의 핵심 기능을 제공합니다.
액세스 토큰과 리프레시 토큰의 생성, 검증, 갱신을 담당합니다.

주요 기능:
    - JWT 액세스 토큰 생성 (단기 수명)
    - JWT 리프레시 토큰 생성 (장기 수명)
    - 토큰 서명 검증 및 디코딩
    - 토큰 만료 시간 관리
    - 리프레시 토큰을 통한 액세스 토큰 갱신

보안 특징:
    - HMAC SHA-256 서명 알고리즘 (HS256)
    - 토큰 타입별 분리된 검증 로직
    - 안전한 만료 시간 관리
    - 구조화된 로깅으로 감사 추적

JWT 표준 준수:
    - RFC 7519 준수
    - 표준 클레임 사용 (sub, exp, iat)
    - 추가 커스텀 클레임 지원

사용 예시:
    >>> jwt_service = JWTService(secret_key="your-secret")
    >>> access_token = jwt_service.create_access_token(user_id="123", email="user@example.com", roles=["user"])
    >>> token_data = jwt_service.decode_token(access_token)
"""

from datetime import datetime, timedelta, UTC
from typing import Any, Optional, Dict
import uuid

from jose import JWTError, jwt
import structlog
import os

from ..models import TokenData
from ..repositories.token_repository import TokenRepository
from ...auth.jwt_manager import (
    JWTManager as NewJWTManager,
    RefreshTokenStore,
    TokenPair,
    TokenRefreshError,
)


# 구조화된 로깅을 위한 로거
logger = structlog.get_logger()


class JWTService:
    """
    JWT 토큰 생성 및 검증 서비스

    JWT 기반 인증 시스템의 핵심 컴포넌트로 토큰의 전체 생명주기를 관리합니다.
    액세스 토큰과 리프레시 토큰을 구분하여 처리하며, 보안을 위해
    각 토큰 타입별로 다른 만료 시간과 검증 로직을 적용합니다.

    토큰 설계 철학:
        - 액세스 토큰: 짧은 수명(30분), API 접근용
        - 리프레시 토큰: 긴 수명(7일), 토큰 갱신용
        - 서명 검증: HMAC-SHA256으로 무결성 보장
        - 페이로드: 최소한의 사용자 정보만 포함

    사용 예시:
        ```python
        jwt_service = JWTService(
            secret_key="your-secret-key",
            access_token_expire_minutes=30,
            refresh_token_expire_minutes=7*24*60
        )

        # 토큰 생성
        access_token = jwt_service.create_access_token(
            user_id="123", email="user@example.com", roles=["user"]
        )

        # 토큰 검증
        token_data = jwt_service.decode_token(access_token)
        if token_data:
            print(f"User ID: {token_data.user_id}")
        ```

    Attributes:
        secret_key (str): JWT 서명용 비밀 키
        algorithm (str): 서명 알고리즘 (기본: HS256)
        access_token_expire_minutes (int): 액세스 토큰 만료 시간 (분)
        refresh_token_expire_minutes (int): 리프레시 토큰 만료 시간 (분)
    """

    def __init__(
        self,
        secret_key: str,
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 30,
        refresh_token_expire_minutes: int = 60 * 24 * 7,  # 7일
        enable_auto_refresh: bool = False,
        redis_url: Optional[str] = None,
        token_repository: Optional[TokenRepository] = None,
    ) -> None:
        """
        JWT 서비스 초기화

        JWT 토큰 생성 및 검증에 필요한 설정을 초기화합니다.
        보안을 위해 강력한 비밀 키와 적절한 만료 시간을 설정해야 합니다.

        Args:
            secret_key (str): JWT 서명에 사용할 비밀 키
                최소 32자 이상의 무작위 문자열 권장
                production에서는 환경 변수나 비밀 관리 시스템에서 로드
            algorithm (str): JWT 서명 알고리즘 (기본값: "HS256")
                지원 알고리즘: HS256, HS384, HS512
                대칭키 알고리즘으로 성능과 보안의 균형
            access_token_expire_minutes (int): 액세스 토큰 만료 시간 (분, 기본값: 30)
                짧은 수명으로 설정하여 보안 위험 최소화
                일반적으로 15분~2시간 사이로 설정
            refresh_token_expire_minutes (int): 리프레시 토큰 만료 시간 (분, 기본값: 7일)
                장기간 유효하지만 재사용 가능한 토큰
                일반적으로 1주일~1개월 사이로 설정
            enable_auto_refresh (bool): 자동 갱신 기능 활성화 여부
            redis_url (Optional[str]): Redis 연결 URL (자동 갱신 사용 시)
            token_repository (Optional[TokenRepository]): 토큰 무효화를 위한 저장소
                토큰 추적 및 무효화 기능 제공

        보안 고려사항:
            - secret_key는 충분히 길고 무작위여야 함
            - production 환경에서는 secret_key를 코드에 하드코딩 금지
            - 토큰 만료 시간은 보안과 사용성의 균형을 고려하여 설정
        """
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.access_token_expire_minutes = access_token_expire_minutes
        self.refresh_token_expire_minutes = refresh_token_expire_minutes
        self.enable_auto_refresh = enable_auto_refresh
        self.token_repository = token_repository

        # 새로운 JWT 매니저 초기화 (자동 갱신 기능이 활성화된 경우)
        self._new_jwt_manager: Optional[NewJWTManager] = None
        self._refresh_token_store: Optional[RefreshTokenStore] = None

        if enable_auto_refresh:
            if not redis_url:
                redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

            # 리프레시 토큰 저장소 초기화
            self._refresh_token_store = RefreshTokenStore(
                redis_url=redis_url,
                default_refresh_token_expire_days=refresh_token_expire_minutes
                // (60 * 24),
            )

            # JWT 매니저 초기화
            self._new_jwt_manager = NewJWTManager(
                secret_key=secret_key,
                algorithm=algorithm,
                access_token_expire_minutes=access_token_expire_minutes,
                refresh_token_store=self._refresh_token_store,
            )

            logger.info(
                "JWT 자동 갱신 기능 활성화",
                redis_url=redis_url,
                access_token_expire_minutes=access_token_expire_minutes,
                refresh_token_expire_days=refresh_token_expire_minutes // (60 * 24),
            )

        logger.info(
            "JWT 서비스 초기화",
            algorithm=algorithm,
            access_token_expire_minutes=access_token_expire_minutes,
            refresh_token_expire_minutes=refresh_token_expire_minutes,
        )

    def create_access_token(
        self,
        user_id: str,
        email: str,
        roles: list[str],
        scopes: Optional[list[str]] = None,
        resource_permissions: Optional[dict[str, list[str]]] = None,
        additional_claims: Optional[dict[str, Any]] = None,
    ) -> str:
        """
        JWT 액세스 토큰 생성

        사용자 정보를 바탕으로 API 접근용 액세스 토큰을 생성합니다.
        짧은 수명(30분)으로 보안 위험을 최소화하며, 사용자 인증 정보와 권한 스코프를 포함합니다.

        Args:
            user_id (str): 사용자 고유 식별자
                JWT의 'sub' (subject) 클레임으로 사용
            email (str): 사용자 이메일 주소
                사용자 식별 및 로깅 목적
            roles (list[str]): 사용자 역할 목록
                권한 검사에 사용되는 역할 정보
                예: ["user", "admin", "moderator"]
            scopes (Optional[list[str]]): OAuth2 스타일 권한 스코프 목록
                세밀한 권한 제어를 위한 스코프 정보
                예: ["read:vectors", "write:database", "admin:users"]
                None인 경우 역할 기반 기본 권한만 사용
            resource_permissions (Optional[dict[str, list[str]]]): 리소스별 세밀한 권한 맵
                특정 리소스에 대한 액션 권한 정의
                예: {"collection1": ["read", "write"], "table_users": ["read"]}
                None인 경우 리소스 권한 검사 없음
            additional_claims (Optional[dict[str, Any]]): 추가 커스텀 클레임
                애플리케이션별 추가 정보를 토큰에 포함
                예: {"department": "engineering", "team": "backend"}

        Returns:
            str: JWT 액세스 토큰 (서명된 문자열)
                Bearer 인증 헤더에 사용할 토큰
                예: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

        JWT 토큰 구조:
            - Header: 알고리즘 및 토큰 타입
            - Payload: 사용자 정보 및 권한
            - Signature: HMAC-SHA256 서명

        토큰 페이로드 예시:
            ```json
            {
                "sub": "user123",
                "email": "user@example.com",
                "roles": ["user"],
                "scopes": ["read:vectors", "write:database"],
                "resource_permissions": {"collection1": ["read", "write"]},
                "type": "access",
                "exp": 1234567890,
                "iat": 1234567890
            }
            ```

        Example:
            ```python
            token = jwt_service.create_access_token(
                user_id="user123",
                email="user@example.com",
                roles=["user"],
                scopes=["read:vectors", "write:database"],
                resource_permissions={"collection1": ["read", "write"]},
                additional_claims={"department": "engineering"}
            )
            ```
        """
        # UTC 기준 현재 시각과 만료 시각 계산
        now = datetime.now(UTC)
        expire = now + timedelta(minutes=self.access_token_expire_minutes)

        # JWT 페이로드 구성 (표준 + 커스텀 클레임)
        payload = {
            "sub": str(
                user_id
            ),  # Subject (사용자 식별자) - JWT 표준에 따라 문자열이어야 함
            "email": email,  # 사용자 이메일
            "roles": roles,  # 권한 역할 목록
            "type": "access",  # 토큰 타입 (액세스)
            "exp": expire,  # Expiration time
            "iat": now,  # Issued at
            "jti": str(uuid.uuid4()),  # JWT ID for uniqueness
        }

        # 새로운 권한 필드들 추가 (하위 호환성을 위해 None이 아닌 경우만 포함)
        if scopes is not None:
            payload["scopes"] = scopes

        if resource_permissions is not None:
            payload["resource_permissions"] = resource_permissions

        # 추가 클레임이 있으면 페이로드에 병합
        if additional_claims:
            payload.update(additional_claims)

        # JWT 토큰 생성 (서명 포함)
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

        # 로깅 (민감 정보 제외)
        logger.info(
            "액세스 토큰 생성",
            user_id=user_id,
            email=email,
            roles=roles,
            has_scopes=scopes is not None,
            has_resource_permissions=resource_permissions is not None,
            expires_in_minutes=self.access_token_expire_minutes,
        )

        return token

    def create_refresh_token(
        self, user_id: str, device_id: Optional[str] = None
    ) -> str:
        """리프레시 토큰 생성

        Args:
            user_id: 사용자 ID
            device_id: 디바이스 식별자 (자동 갱신 기능 사용 시)

        Returns:
            JWT 리프레시 토큰
        """
        # 자동 갱신 기능이 활성화되고 device_id가 있는 경우 새 매니저 사용
        if self.enable_auto_refresh and self._new_jwt_manager and device_id:
            return self._new_jwt_manager.create_refresh_token(user_id, device_id)

        # 기존 방식 (하위 호환성)
        now = datetime.now(UTC)
        expire = now + timedelta(minutes=self.refresh_token_expire_minutes)

        payload = {
            "sub": str(user_id),  # JWT sub는 문자열이어야 함
            "type": "refresh",
            "exp": expire,
            "iat": now,
            "jti": str(uuid.uuid4()),  # JWT ID for uniqueness
        }

        if device_id:
            payload["device_id"] = device_id

        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

        # 토큰 저장소에 저장 (무효화 추적용)
        if self.token_repository:
            import asyncio

            try:
                # 동기 컨텍스트에서 비동기 호출
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 이미 실행 중인 루프가 있으면 태스크로 스케줄
                    asyncio.create_task(
                        self.token_repository.store_refresh_token(
                            jti=payload["jti"],
                            user_id=str(user_id),
                            expires_at=expire,
                            metadata={"device_id": device_id} if device_id else None,
                        )
                    )
                else:
                    # 루프가 없으면 새로 실행
                    loop.run_until_complete(
                        self.token_repository.store_refresh_token(
                            jti=payload["jti"],
                            user_id=str(user_id),
                            expires_at=expire,
                            metadata={"device_id": device_id} if device_id else None,
                        )
                    )
            except Exception as e:
                logger.warning(
                    "토큰 저장 실패, 토큰은 발급되었지만 추적되지 않음", error=str(e)
                )

        logger.info(
            "리프레시 토큰 생성",
            user_id=user_id,
            device_id=device_id,
            expires_in_minutes=self.refresh_token_expire_minutes,
            jti=payload["jti"],
        )

        return token

    def decode_token(self, token: str) -> Optional[TokenData]:
        """
        JWT 토큰 디코딩 및 검증

        주어진 JWT 토큰을 디코딩하고 서명을 검증합니다.
        성공 시 토큰에 포함된 사용자 정보를 반환하고,
        실패 시 None을 반환합니다.

        검증 단계:
            1. JWT 서명 검증 (HMAC-SHA256)
            2. 토큰 만료 시간 확인
            3. 필수 필드 존재 여부 확인
            4. 토큰 타입 검증

        Args:
            token (str): 검증할 JWT 토큰 문자열
                Bearer 접두사 없이 순수 토큰만 전달

        Returns:
            Optional[TokenData]: 토큰 검증 성공 시 사용자 정보
                - user_id: 사용자 식별자
                - email: 사용자 이메일 (Optional)
                - roles: 역할 목록
                - token_type: 토큰 타입 (access/refresh)
                - exp: 만료 시간
                - iat: 발급 시간
                - scopes: 권한 스코프 (Optional, 새로운 필드)
                - resource_permissions: 리소스 권한 (Optional, 새로운 필드)
                검증 실패 시 None 반환

        하위 호환성:
            - 이전 버전의 토큰도 정상적으로 디코딩
            - 새로운 필드들은 Optional로 안전하게 처리
            - 필드가 없는 경우 None으로 기본값 설정

        실패 원인:
            - 잘못된 서명 (토큰 위변조)
            - 만료된 토큰
            - 잘못된 토큰 형식
            - 필수 필드 누락

        Example:
            ```python
            token_data = jwt_service.decode_token(access_token)
            if token_data:
                user_id = token_data.user_id
                roles = token_data.roles
                scopes = token_data.scopes or []  # 하위 호환성
                resource_perms = token_data.resource_permissions or {}
            else:
                # 토큰 검증 실패 처리
                raise AuthenticationError("Invalid token")
            ```
        """
        try:
            # JWT 디코딩 및 서명 검증
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],  # 허용된 알고리즘만 사용
            )

            # 필수 필드 존재 확인
            if "sub" not in payload or "type" not in payload:
                logger.warning("토큰에 필수 필드 누락", payload=payload)
                return None

            # 리프레시 토큰의 경우 저장소에서 유효성 확인
            if (
                payload["type"] == "refresh"
                and self.token_repository
                and "jti" in payload
            ):
                import asyncio

                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # 비동기 환경에서는 동기 호출 불가, 일단 통과
                        logger.debug("비동기 환경에서 토큰 유효성 확인 건너뜀")
                    else:
                        # 동기 환경에서 비동기 호출
                        is_valid = loop.run_until_complete(
                            self.token_repository.is_token_valid(payload["jti"])
                        )
                        if not is_valid:
                            logger.warning("무효화된 리프레시 토큰", jti=payload["jti"])
                            return None
                except Exception as e:
                    logger.error("토큰 유효성 확인 실패", error=str(e))

            # TokenData 객체 생성 (안전한 타입 변환 및 하위 호환성 보장)
            token_data = TokenData(
                user_id=payload["sub"],
                email=payload.get("email") if payload.get("email") else None,
                roles=payload.get("roles", []),
                token_type=payload["type"],
                # timestamp를 datetime 객체로 변환
                exp=datetime.fromtimestamp(payload["exp"], UTC)
                if "exp" in payload
                else None,
                iat=datetime.fromtimestamp(payload["iat"], UTC)
                if "iat" in payload
                else None,
                # 새로운 권한 필드들 (하위 호환성을 위해 안전하게 처리)
                scopes=payload.get("scopes") if "scopes" in payload else None,
                resource_permissions=payload.get("resource_permissions")
                if "resource_permissions" in payload
                else None,
                jti=payload.get("jti") if "jti" in payload else None,  # JWT ID
            )

            return token_data

        except JWTError as e:
            # JWT 관련 오류 (서명 실패, 만료, 형식 오류 등)
            logger.warning("JWT 디코드 오류", error=str(e))
            return None
        except Exception as e:
            # 예상치 못한 오류 (timestamp 변환 실패 등)
            logger.error("예상치 못한 토큰 디코드 오류", error=str(e))
            return None

    def verify_refresh_token(self, refresh_token: str) -> Optional[str]:
        """
        리프레시 토큰 검증

        리프레시 토큰을 검증하고 사용자 ID를 반환합니다.
        액세스 토큰 갱신 시 사용됩니다.

        Args:
            refresh_token: 검증할 리프레시 토큰

        Returns:
            검증 성공 시 사용자 ID, 실패 시 None
        """
        token_data = self.decode_token(refresh_token)

        if not token_data:
            return None

        if token_data.token_type != "refresh":
            logger.warning(
                "잘못된 토큰 타입", expected="refresh", actual=token_data.token_type
            )
            return None

        return token_data.user_id

    def is_token_near_expiry(self, token: str, threshold_minutes: int = 5) -> bool:
        """
        토큰이 곧 만료되는지 확인

        Args:
            token: 확인할 JWT 토큰
            threshold_minutes: 만료 임계값 (분)

        Returns:
            임계값 내에 만료되면 True
        """
        token_data = self.decode_token(token)
        if not token_data or not token_data.exp:
            return True

        time_until_expiry = token_data.exp - datetime.now(UTC)
        return time_until_expiry.total_seconds() < threshold_minutes * 60

    # 자동 갱신 관련 메서드들 (하위 호환성)
    async def create_token_pair_async(
        self,
        user_id: str,
        email: str,
        roles: list[str],
        device_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[TokenPair]:
        """비동기 토큰 쌍 생성 (자동 갱신 기능용)"""
        if not self.enable_auto_refresh or not self._new_jwt_manager:
            logger.warning("자동 갱신 기능이 비활성화되어 있습니다")
            return None

        try:
            access_token = await self._new_jwt_manager.create_access_token(
                user_id=user_id, email=email, roles=roles
            )

            refresh_token = await self._new_jwt_manager.create_refresh_token(
                user_id=user_id, device_id=device_id
            )

            # 메타데이터와 함께 저장
            if metadata and self._refresh_token_store:
                await self._refresh_token_store.store_token(
                    user_id=user_id,
                    device_id=device_id,
                    refresh_token=refresh_token,
                    metadata=metadata,
                )

            return TokenPair(access_token=access_token, refresh_token=refresh_token)

        except Exception as e:
            logger.error("토큰 쌍 생성 실패", error=str(e))
            return None

    async def refresh_tokens_async(
        self,
        refresh_token: str,
        device_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[TokenPair]:
        """비동기 토큰 갱신 (자동 갱신 기능용)"""
        if not self.enable_auto_refresh or not self._new_jwt_manager:
            logger.warning("자동 갱신 기능이 비활성화되어 있습니다")
            return None

        try:
            # 기존 리프레시 토큰 무효화
            if self.token_repository:
                token_data = self.decode_token(refresh_token)
                if token_data and hasattr(token_data, "jti"):
                    await self.token_repository.revoke_token(token_data.jti)

            return await self._new_jwt_manager.refresh_tokens(
                refresh_token=refresh_token, device_id=device_id, metadata=metadata
            )
        except TokenRefreshError as e:
            logger.warning("토큰 갱신 실패", error=str(e))
            return None
        except Exception as e:
            logger.error("예상치 못한 토큰 갱신 오류", error=str(e))
            return None

    async def revoke_refresh_token(
        self, user_id: str, device_id: Optional[str] = None
    ) -> bool:
        """리프레시 토큰 무효화"""
        if self.enable_auto_refresh and self._refresh_token_store:
            # 새 시스템 사용
            if device_id:
                return await self._refresh_token_store.revoke_token(user_id, device_id)
            else:
                count = await self._refresh_token_store.revoke_all_tokens(user_id)
                return count > 0

        # 기존 토큰 저장소 사용
        if self.token_repository:
            if device_id:
                # device_id로는 직접 무효화 불가, user의 모든 토큰 무효화
                count = await self.token_repository.revoke_user_tokens(user_id)
                return count > 0
            else:
                count = await self.token_repository.revoke_user_tokens(user_id)
                return count > 0

        return False

    async def revoke_all_user_tokens(self, user_id: str) -> int:
        """사용자의 모든 토큰 무효화"""
        count = 0

        # 새 시스템에서 무효화
        if self.enable_auto_refresh and self._refresh_token_store:
            count += await self._refresh_token_store.revoke_all_tokens(user_id)

        # 기존 토큰 저장소에서 무효화
        if self.token_repository:
            count += await self.token_repository.revoke_user_tokens(user_id)

        return count

    async def get_active_sessions(self, user_id: str) -> list[dict[str, Any]]:
        """사용자의 활성 세션 조회"""
        sessions = []

        # 새 시스템에서 조회
        if self.enable_auto_refresh and self._refresh_token_store:
            new_sessions = await self._refresh_token_store.get_user_tokens(user_id)
            sessions.extend(new_sessions)

        # 기존 토큰 저장소에서 조회
        if self.token_repository:
            old_sessions = await self.token_repository.get_user_active_tokens(user_id)
            sessions.extend(old_sessions)

        return sessions
