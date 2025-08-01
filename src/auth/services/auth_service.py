"""
사용자 인증 및 권한 관리 서비스

이 모듈은 MCP 서버의 핵심 인증 로직을 담당합니다.
사용자 등록, 로그인, 토큰 관리, 사용자 정보 조회 등의 기능을 제공합니다.

주요 기능:
    - 사용자 등록 및 중복 이메일 검증
    - bcrypt를 사용한 안전한 비밀번호 해싱
    - JWT 기반 인증 토큰 생성 및 검증
    - 리프레시 토큰을 통한 토큰 갱신
    - 사용자 검색 및 관리 기능

보안 특징:
    - 타이밍 공격 방지를 위한 일관된 에러 메시지
    - 비밀번호는 bcrypt로 해싱하여 안전하게 저장
    - JWT 토큰 만료 시간 관리
    - 계정 활성화 상태 검증

의존성:
    - UserRepository: 사용자 데이터 영속성
    - JWTService: JWT 토큰 생성 및 검증
    - passlib: 비밀번호 해싱
"""

from typing import Any

from passlib.context import CryptContext
import structlog

from ..models import UserCreate, UserLogin, AuthTokens, UserResponse
from ..repositories.user_repository import UserRepository
from .jwt_service import JWTService


# 구조화된 로깅을 위한 로거
logger = structlog.get_logger()


class AuthenticationError(Exception):
    """
    인증 관련 에러

    사용자 인증 실패, 토큰 검증 실패, 권한 부족 등
    인증과 관련된 모든 에러에 사용됩니다.

    보안상 구체적인 실패 원인은 로그에만 기록하고
    사용자에게는 일반적인 메시지를 표시합니다.
    """

    pass


class AuthService:
    """
    사용자 인증 및 권한 관리 서비스

    MCP 서버의 인증 시스템의 핵심 비즈니스 로직을 담당합니다.
    Repository 패턴과 Service 패턴을 결합하여 데이터 접근과
    비즈니스 로직을 분리합니다.

    보안 원칙:
        - 방어적 프로그래밍: 모든 입력값 검증
        - 최소 권한 원칙: 필요한 권한만 부여
        - 오류 정보 노출 최소화: 공격자에게 유용한 정보 차단
        - 감사 로깅: 모든 인증 시도 기록

    사용 예시:
        ```python
        auth_service = AuthService(user_repo, jwt_service)

        # 사용자 등록
        user = await auth_service.register(user_create_data)

        # 로그인
        tokens = await auth_service.login(login_data)

        # 토큰으로 사용자 조회
        user = await auth_service.get_current_user(access_token)
        ```

    Attributes:
        user_repository (UserRepository): 사용자 데이터 저장소
        jwt_service (JWTService): JWT 토큰 관리 서비스
        pwd_context (CryptContext): 비밀번호 해싱 컨텍스트
    """

    def __init__(
        self,
        user_repository: UserRepository,
        jwt_service: JWTService,
    ) -> None:
        """
        인증 서비스 초기화

        의존성 주입을 통해 필요한 서비스들을 설정하고
        bcrypt 비밀번호 해싱 컨텍스트를 초기화합니다.

        Args:
            user_repository (UserRepository): 사용자 데이터 영속성 계층
                사용자 CRUD 작업을 담당
            jwt_service (JWTService): JWT 토큰 관리 서비스
                토큰 생성, 검증, 갱신을 담당

        Note:
            bcrypt는 adaptive hashing으로 시간이 지남에 따라
            보안 강도를 조정할 수 있어 선택했습니다.
        """
        self.user_repository = user_repository
        self.jwt_service = jwt_service
        # bcrypt를 사용한 안전한 비밀번호 해싱 컨텍스트
        # deprecated="auto"로 설정하여 안전하지 않은 해시는 자동 업그레이드
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def hash_password(self, password: str) -> str:
        """
        비밀번호 안전한 해싱

        bcrypt 알고리즘을 사용하여 비밀번호를 해싱합니다.
        bcrypt는 salt가 자동으로 포함되어 레인보우 테이블 공격을 방지합니다.

        Args:
            password (str): 평문 비밀번호
                사용자가 입력한 원본 비밀번호

        Returns:
            str: bcrypt로 해싱된 비밀번호
                salt와 hash가 결합된 형태로 저장 가능

        보안 특징:
            - 자동 salt 생성으로 동일한 비밀번호도 다른 해시 생성
            - adaptive cost로 하드웨어 발전에 대응 가능
            - timing attack에 안전한 검증
        """
        return self.pwd_context.hash(password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """
        비밀번호 검증

        평문 비밀번호와 해시된 비밀번호를 비교하여 일치 여부를 확인합니다.
        타이밍 공격을 방지하기 위해 일정한 시간이 소요됩니다.

        Args:
            plain_password (str): 검증할 평문 비밀번호
                사용자가 로그인 시 입력한 비밀번호
            hashed_password (str): 저장된 해시된 비밀번호
                데이터베이스에 저장된 bcrypt 해시

        Returns:
            bool: 비밀번호 일치 여부
                True: 비밀번호 일치
                False: 비밀번호 불일치

        보안 특징:
            - 상수 시간 비교로 타이밍 공격 방지
            - 잘못된 해시 형식에 대한 안전한 처리
        """
        return self.pwd_context.verify(plain_password, hashed_password)

    async def register(self, user_create: UserCreate) -> UserResponse:
        """
        새 사용자 등록

        이메일 중복 확인 후 안전한 비밀번호 해싱을 통해 새 사용자를 생성합니다.
        Pydantic 모델의 검증을 통과한 데이터만 처리됩니다.

        Args:
            user_create (UserCreate): 사용자 생성 정보
                이미 Pydantic으로 검증된 데이터
                - email: 유효한 이메일 형식
                - password: 복잡도 요구사항을 만족하는 비밀번호
                - roles: 부여할 역할 목록

        Returns:
            UserResponse: 생성된 사용자 정보
                민감한 정보(해시된 비밀번호)는 제외된 안전한 응답

        Raises:
            AuthenticationError: 등록 실패 시
                - 이미 등록된 이메일인 경우
                - 데이터베이스 제약 조건 위반

        보안 고려사항:
            - 이메일 존재 여부가 노출되지만 일반적으로 허용되는 수준
            - 비밀번호는 SecretStr로 처리되어 로그에 노출되지 않음
            - 사용자 ID는 UUID로 생성되어 추측 불가능

        Example:
            ```python
            user_data = UserCreate(
                email="user@example.com",
                password=SecretStr("StrongPass123!"),
                roles=["user"]
            )
            user = await auth_service.register(user_data)
            ```
        """
        # 이메일 중복 확인 (비즈니스 규칙)
        existing_user = await self.user_repository.get_by_email(user_create.email)
        if existing_user:
            raise AuthenticationError(f"이미 등록된 이메일입니다: {user_create.email}")

        # 비밀번호 안전한 해싱
        hashed_password = self.hash_password(user_create.password)

        # 사용자 데이터 준비 (ID는 repository에서 자동 생성)
        user_data = {
            "email": user_create.email,
            "hashed_password": hashed_password,
            "roles": user_create.roles or ["user"],  # None인 경우 기본값 설정
        }

        # 데이터베이스에 사용자 생성
        user = await self.user_repository.create(user_data)

        # 등록 성공 로깅 (감사 목적)
        logger.info(
            "사용자 등록 완료",
            user_id=user.id,
            email=user.email,
            roles=user.roles,
        )

        # 안전한 사용자 정보 응답 (비밀번호 해시 제외)
        return UserResponse(
            id=user.id,
            email=user.email,
            is_active=user.is_active,
            is_verified=user.is_verified,
            roles=user.roles,
            created_at=user.created_at,
        )

    async def login(self, user_login: UserLogin) -> AuthTokens:
        """
        사용자 로그인 인증

        이메일과 비밀번호를 검증하여 JWT 토큰을 발급합니다.
        보안을 위해 여러 단계의 검증을 거치며, 모든 실패 사례를 로깅합니다.

        Args:
            user_login (UserLogin): 로그인 정보
                - email: 사용자 이메일
                - password: SecretStr로 보호된 비밀번호

        Returns:
            AuthTokens: 인증 토큰 쌍
                - access_token: API 호출용 단기 토큰
                - refresh_token: 토큰 갱신용 장기 토큰

        Raises:
            AuthenticationError: 인증 실패 시
                - 존재하지 않는 사용자
                - 비밀번호 불일치
                - 계정 비활성화 상태

        보안 특징:
            - 타이밍 공격 방지를 위한 일관된 에러 메시지
            - 모든 로그인 시도 로깅 (성공/실패 모두)
            - 계정 상태 검증 (활성화 여부)
            - 구체적인 실패 원인은 로그에만 기록

        인증 흐름:
            1. 이메일로 사용자 조회
            2. 비밀번호 해시 검증 (bcrypt)
            3. 계정 활성화 상태 확인
            4. JWT 토큰 쌍 생성 및 반환
        """
        # 1단계: 사용자 존재 확인
        user = await self.user_repository.get_by_email(user_login.email)
        if not user:
            # 보안: 존재하지 않는 사용자도 로깅하되 일반적인 에러 메시지 반환
            logger.warning("존재하지 않는 사용자로 로그인 시도", email=user_login.email)
            raise AuthenticationError("이메일 또는 비밀번호가 올바르지 않습니다")

        # 2단계: 비밀번호 검증 (bcrypt 상수 시간 비교)
        if not self.verify_password(
            user_login.password,
            user.hashed_password,
        ):
            # 보안: 비밀번호 실패도 로깅하되 일반적인 에러 메시지 반환
            logger.warning("잘못된 비밀번호로 로그인 시도", email=user_login.email)
            raise AuthenticationError("이메일 또는 비밀번호가 올바르지 않습니다")

        # 3단계: 계정 활성화 상태 확인
        if not user.is_active:
            logger.warning("비활성화된 계정으로 로그인 시도", email=user_login.email)
            raise AuthenticationError("계정이 비활성화되었습니다")

        # 4단계: JWT 토큰 쌍 생성
        access_token = self.jwt_service.create_access_token(
            user_id=user.id,
            email=user.email,
            roles=user.roles,
        )
        refresh_token = self.jwt_service.create_refresh_token(
            user_id=user.id,
        )

        # 성공 로깅 (감사 목적)
        logger.info(
            "로그인 성공",
            user_id=user.id,
            email=user.email,
            roles=user.roles,
        )

        return AuthTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self.jwt_service.access_token_expire_minutes
            * 60,  # 분을 초로 변환
        )

    async def refresh_tokens(self, refresh_token: str) -> AuthTokens:
        """
        JWT 토큰 갱신

        리프레시 토큰을 검증하여 새로운 액세스 토큰을 발급합니다.
        사용자의 현재 상태를 재확인하여 보안을 유지합니다.

        Args:
            refresh_token (str): 유효한 리프레시 토큰
                로그인 시 발급받은 장기 토큰

        Returns:
            AuthTokens: 갱신된 토큰 쌍
                - access_token: 새로 생성된 액세스 토큰
                - refresh_token: 기존 리프레시 토큰 재사용

        Raises:
            AuthenticationError: 갱신 실패 시
                - 유효하지 않은 리프레시 토큰
                - 만료된 토큰
                - 사용자 불존재 또는 계정 비활성화

        보안 고려사항:
            - 리프레시 토큰의 타입과 유효성 검증
            - 사용자 현재 상태 재확인 (계정 비활성화 등)
            - 토큰 갱신 시도 로깅
            - 실패 시 구체적인 원인 숨김

        토큰 갱신 흐름:
            1. 리프레시 토큰 디코딩 및 타입 검증
            2. 토큰에서 사용자 ID 추출
            3. 사용자 현재 상태 조회 및 검증
            4. 새 액세스 토큰 생성 (최신 역할 정보 반영)
            5. 기존 리프레시 토큰과 함께 반환
        """
        # 1단계: 리프레시 토큰 검증 및 디코딩
        token_data = self.jwt_service.decode_token(refresh_token)
        if not token_data or token_data.token_type != "refresh":
            raise AuthenticationError("유효하지 않은 리프레시 토큰입니다")

        # 2단계: 토큰에서 사용자 정보 추출 및 조회
        user = await self.user_repository.get_by_id(token_data.user_id)
        if not user:
            # 사용자가 삭제된 경우 토큰 무효화
            raise AuthenticationError("사용자를 찾을 수 없습니다")

        # 3단계: 사용자 현재 상태 검증
        if not user.is_active:
            # 사용자가 비활성화된 경우 토큰 갱신 거부
            raise AuthenticationError("계정이 비활성화되었습니다")

        # 4단계: 새 액세스 토큰 생성 (현재 사용자 정보 반영)
        new_access_token = self.jwt_service.refresh_access_token(
            refresh_token=refresh_token,
            email=user.email,
            roles=user.roles,  # 최신 역할 정보 반영
        )

        if not new_access_token:
            # JWT 서비스에서 토큰 생성 실패
            raise AuthenticationError("토큰 갱신에 실패했습니다")

        # 갱신 성공 로깅 (감사 목적)
        logger.info(
            "토큰 갱신 성공",
            user_id=user.id,
            email=user.email,
        )

        return AuthTokens(
            access_token=new_access_token,
            refresh_token=refresh_token,  # 리프레시 토큰은 재사용 (보안상 문제없음)
            expires_in=self.jwt_service.access_token_expire_minutes
            * 60,  # 분을 초로 변환
        )

    async def get_current_user(self, token: str) -> UserResponse:
        """
        액세스 토큰으로 현재 사용자 조회

        JWT 액세스 토큰을 검증하여 현재 요청의 사용자 정보를 반환합니다.
        인증 미들웨어와 API 엔드포인트에서 사용자 식별을 위해 사용됩니다.

        Args:
            token (str): JWT 액세스 토큰
                Authorization 헤더에서 추출된 Bearer 토큰

        Returns:
            UserResponse: 현재 사용자 정보
                민감한 정보는 제외된 안전한 응답 모델

        Raises:
            AuthenticationError: 인증 실패 시
                - 유효하지 않은 토큰 (잘못된 서명, 만료 등)
                - 잘못된 토큰 타입 (refresh 토큰 사용 등)
                - 사용자 불존재 (토큰은 유효하지만 사용자 삭제됨)
                - 계정 비활성화 상태

        사용 사례:
            - FastAPI Depends를 통한 현재 사용자 주입
            - API 엔드포인트에서 요청자 신원 확인
            - 권한 검사 전 사용자 정보 획득

        보안 검증 단계:
            1. JWT 토큰 구조 및 서명 검증
            2. 토큰 타입 확인 (access여야 함)
            3. 토큰 만료 시간 검증
            4. 사용자 존재 여부 확인
            5. 계정 활성화 상태 확인

        Example:
            ```python
            # FastAPI dependency
            async def get_current_user_dep(
                token: str = Depends(oauth2_scheme)
            ) -> UserResponse:
                return await auth_service.get_current_user(token)
            ```
        """
        # 1단계: 액세스 토큰 디코딩 및 검증
        token_data = self.jwt_service.decode_token(token)
        if not token_data or token_data.token_type != "access":
            raise AuthenticationError("유효하지 않은 액세스 토큰입니다")

        # 2단계: 토큰에서 사용자 ID 추출하여 사용자 조회
        user = await self.user_repository.get_by_id(token_data.user_id)
        if not user:
            # 토큰은 유효하지만 사용자가 삭제된 경우
            raise AuthenticationError("사용자를 찾을 수 없습니다")

        # 3단계: 계정 활성화 상태 검증
        if not user.is_active:
            # 사용자가 비활성화된 경우 접근 거부
            raise AuthenticationError("계정이 비활성화되었습니다")

        # 안전한 사용자 정보 반환 (비밀번호 해시 제외)
        return UserResponse(
            id=user.id,
            email=user.email,
            is_active=user.is_active,
            is_verified=user.is_verified,
            roles=user.roles,
            created_at=user.created_at,
        )

    async def search_users(self, query: str, limit: int = 10) -> list[UserResponse]:
        """사용자 검색 (이메일 또는 이름으로)

        Args:
            query: 검색 쿼리 (이메일 또는 이름)
            limit: 결과 개수 제한

        Returns:
            검색된 사용자 목록
        """
        users = await self.user_repository.search_users(query, limit)

        return [
            UserResponse(
                id=user.id,
                email=user.email,
                is_active=user.is_active,
                is_verified=user.is_verified,
                roles=user.roles,
                created_at=user.created_at,
            )
            for user in users
        ]

    async def get_user_by_id(self, user_id: str) -> UserResponse | None:
        """ID로 사용자 조회

        Args:
            user_id: 사용자 ID

        Returns:
            사용자 정보 또는 None
        """
        user = await self.user_repository.get_by_id(user_id)
        if not user:
            return None

        return UserResponse(
            id=user.id,
            email=user.email,
            is_active=user.is_active,
            is_verified=user.is_verified,
            roles=user.roles,
            created_at=user.created_at,
        )

    async def get_recent_users(self, limit: int = 10) -> list[UserResponse]:
        """최근 가입한 사용자들 조회

        Args:
            limit: 결과 개수 제한

        Returns:
            최근 가입한 사용자 목록
        """
        users = await self.user_repository.get_recent_users(limit)

        return [
            UserResponse(
                id=user.id,
                email=user.email,
                is_active=user.is_active,
                is_verified=user.is_verified,
                roles=user.roles,
                created_at=user.created_at,
            )
            for user in users
        ]

    async def list_all_users(
        self, skip: int = 0, limit: int = 50
    ) -> list[UserResponse]:
        """모든 사용자 목록 조회 (관리자용)

        Args:
            skip: 건너뛸 사용자 수
            limit: 결과 개수 제한

        Returns:
            사용자 목록
        """
        users = await self.user_repository.list_all(skip=skip, limit=limit)

        return [
            UserResponse(
                id=user.id,
                email=user.email,
                is_active=user.is_active,
                is_verified=user.is_verified,
                roles=user.roles,
                created_at=user.created_at,
            )
            for user in users
        ]

    async def get_user_statistics(self) -> dict[str, Any]:
        """사용자 통계 조회 (관리자용)

        Returns:
            사용자 통계 정보
        """
        stats = await self.user_repository.get_user_statistics()
        return stats
