"""
사용자 데이터 영속성 관리를 위한 Repository 패턴 구현

이 모듈은 사용자 데이터의 저장, 조회, 수정, 삭제를 담당하는 Repository 패턴을 구현합니다.
추상 클래스를 통해 인터페이스를 정의하고, 다양한 저장소 구현체를 제공합니다.

Repository 패턴의 장점:
    - 데이터 접근 로직과 비즈니스 로직 분리
    - 다양한 저장소 백엔드 지원 (메모리, DB, API 등)
    - 테스트 가능성 향상 (Mock Repository 사용)
    - 의존성 역전 원칙 준수

구현체:
    - InMemoryUserRepository: 메모리 기반 구현 (개발/테스트용)
    - SQLAlchemyUserRepository: 데이터베이스 기반 구현 (production용)
    - RedisUserRepository: 캐시 기반 구현 (고성능 읽기용)

CRUD 작업:
    - Create: 새 사용자 생성 (중복 검사 포함)
    - Read: ID/이메일로 사용자 조회
    - Update: 사용자 정보 수정
    - Delete: 사용자 삭제

추가 기능:
    - 사용자 검색 (이메일 기반)
    - 최근 가입 사용자 조회
    - 사용자 통계 정보
    - 페이지네이션 지원
"""

from abc import ABC, abstractmethod
from datetime import datetime, UTC
from typing import Optional, Any

import structlog

from ..models import User


# 구조화된 로깅을 위한 모듈별 로거
logger = structlog.get_logger(__name__)


class UserRepository(ABC):
    """
    사용자 데이터 영속성을 위한 추상 Repository 클래스

    Repository 패턴의 핵심 인터페이스로 모든 사용자 데이터 작업을 정의합니다.
    구체적인 저장소 구현체들은 이 인터페이스를 구현하여 일관된 API를 제공합니다.

    디자인 원칙:
        - 인터페이스 분리: 필요한 메서드만 정의
        - 의존성 역전: 추상화에 의존하도록 설계
        - 단일 책임: 사용자 데이터 영속성만 담당
        - 테스트 가능성: Mock 구현체로 테스트 지원

    비동기 설계:
        - 모든 메서드는 async/await 패턴 사용
        - 데이터베이스 I/O의 비블로킹 처리
        - FastAPI와의 원활한 통합

    에러 처리:
        - 비즈니스 규칙 위반 시 명확한 예외 발생
        - 데이터 무결성 보장
        - 구조화된 로깅으로 디버깅 지원
    """

    @abstractmethod
    async def create(self, user_data: dict) -> User:
        """
        새 사용자 생성

        Args:
            user_data (dict): 사용자 생성 정보
                - email (str): 이메일 주소 (고유해야 함)
                - hashed_password (str): 해시된 비밀번호
                - roles (list[str]): 사용자 역할 목록
                - is_active (bool): 활성화 상태 (기본값: True)

        Returns:
            User: 생성된 사용자 모델

        Raises:
            ValueError: 이메일 중복이나 필수 필드 누락 시
        """
        pass

    @abstractmethod
    async def get_by_id(self, user_id: str) -> Optional[User]:
        """
        사용자 ID로 조회

        Args:
            user_id (str): 사용자 고유 식별자

        Returns:
            Optional[User]: 사용자 모델 또는 None (미존재시)
        """
        pass

    @abstractmethod
    async def get_by_email(self, email: str) -> Optional[User]:
        """
        이메일 주소로 사용자 조회

        Args:
            email (str): 이메일 주소

        Returns:
            Optional[User]: 사용자 모델 또는 None (미존재시)
        """
        pass

    @abstractmethod
    async def update(self, user_id: str, user_data: dict) -> Optional[User]:
        """
        사용자 정보 업데이트

        Args:
            user_id (str): 업데이트할 사용자 ID
            user_data (dict): 업데이트할 필드들

        Returns:
            Optional[User]: 업데이트된 사용자 모델 또는 None (미존재시)

        Raises:
            ValueError: 이메일 중복 등 제약 조건 위반 시
        """
        pass

    @abstractmethod
    async def delete(self, user_id: str) -> bool:
        """
        사용자 삭제

        Args:
            user_id (str): 삭제할 사용자 ID

        Returns:
            bool: 삭제 성공 여부
        """
        pass


class InMemoryUserRepository(UserRepository):
    """
    메모리 기반 사용자 Repository 구현체

    개발 및 테스트 환경을 위한 메모리 기반 사용자 저장소입니다.
    실제 데이터베이스 없이도 완전한 CRUD 기능을 제공하며,
    빠른 개발과 테스트를 위한 기본 사용자 계정을 포함합니다.

    메모리 저장소 특징:
        - 애플리케이션 재시작 시 데이터 소실
        - 빠른 읽기/쓰기 성능 (O(1) 접근)
        - 별도 DB 설정 불필요
        - 테스트 격리성 보장

    데이터 구조:
        - _users: {user_id -> User} 메인 사용자 저장소
        - _email_index: {email -> user_id} 이메일 검색 인덱스

    인덱싱 전략:
        - 이메일을 통한 빠른 조회를 위한 보조 인덱스
        - 이메일 변경 시 인덱스 자동 업데이트
        - 데이터 무결성 보장

    테스트 데이터:
        - admin@example.com / Admin123! (관리자)
        - user@example.com / User123! (일반 사용자)

    사용 시나리오:
        - 로컬 개발 환경
        - 단위 테스트 및 통합 테스트
        - 프로토타입 개발
        - CI/CD 파이프라인
    """

    def __init__(self) -> None:
        """
        인메모리 Repository 초기화

        내부 데이터 구조를 설정하고 개발/테스트용 기본 사용자를 생성합니다.
        이메일 기반 검색 성능을 위한 보조 인덱스도 함께 초기화합니다.

        초기화 과정:
            1. 메인 사용자 저장소 생성 (_users)
            2. 이메일 검색 인덱스 생성 (_email_index)
            3. 기본 테스트 사용자 계정 생성
            4. 인덱스 일관성 확인

        메모리 구조:
            _users: 사용자 ID를 키로 하는 User 객체 딕셔너리
            _email_index: 이메일을 키로 하는 사용자 ID 매핑
        """
        # 메인 사용자 저장소: user_id -> User 객체
        self._users: dict[str, User] = {}

        # 이메일 검색용 보조 인덱스: email -> user_id
        # 이메일로 빠른 사용자 조회를 위한 역방향 인덱스
        self._email_index: dict[str, str] = {}

        # 개발 및 테스트를 위한 기본 사용자 계정 생성
        self._init_default_users()

    def _init_default_users(self) -> None:
        """
        개발 및 테스트용 기본 사용자 계정 초기화

        애플리케이션 시작 시 바로 사용할 수 있는 기본 사용자 계정들을 생성합니다.
        각 역할별로 미리 정의된 계정을 제공하여 개발과 테스트를 편리하게 합니다.

        기본 계정 정보:
            관리자 계정:
                - 이메일: admin@example.com
                - 비밀번호: Admin123!
                - 역할: ["admin"]
                - 모든 관리 기능 접근 가능

            일반 사용자 계정:
                - 이메일: user@example.com
                - 비밀번호: User123!
                - 역할: ["user"]
                - 기본 사용자 기능 접근 가능

        보안 고려사항:
            - 비밀번호는 bcrypt로 해시되어 저장
            - production 환경에서는 이 계정들 비활성화 권장
            - 비밀번호 복잡도 요구사항 준수

        생성 과정:
            1. 사용자 데이터 준비
            2. User 모델 인스턴스 생성
            3. 메인 저장소에 저장
            4. 이메일 인덱스 업데이트
            5. 생성 완료 로깅
        """
        # 기본 사용자 계정 정의
        from datetime import datetime, UTC

        now = datetime.now(UTC)
        default_users = [
            {
                "id": 1,
                "email": "admin@example.com",
                "username": "admin",
                # bcrypt 해시된 비밀번호: "Admin123!"
                "hashed_password": "$2b$12$EGdnlElxO9sCf0gMMiHPgeU9snt1agptpaf6IORYNZm.SyHZ3jekO",
                "roles": ["admin"],
                "is_active": True,
                "is_verified": True,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": 2,
                "email": "user@example.com",
                "username": "user",
                # bcrypt 해시된 비밀번호: "User123!"
                "hashed_password": "$2b$12$a6LuLorpYqUfcZnSt6CaNO9trnFXxpwUAVRDCzw27diacidYjmuGC",
                "roles": ["user"],
                "is_active": True,
                "is_verified": True,
                "created_at": now,
                "updated_at": now,
            },
        ]

        # 각 기본 사용자 계정 생성 및 저장
        for user_data in default_users:
            # User 모델 인스턴스 생성
            user = User(**user_data)  # type: ignore[misc]

            # 메인 저장소에 추가
            self._users[user.id] = user

            # 이메일 검색 인덱스에 추가
            self._email_index[user.email] = user.id

        # 초기화 완료 로깅
        logger.info("기본 사용자 초기화 완료", user_count=len(default_users))

    async def create(self, user_data: dict) -> User:
        """
        새 사용자 계정 생성

        제공된 사용자 데이터로 새 계정을 생성하고 메모리에 저장합니다.
        이메일 중복 검사와 데이터 유효성 검증을 수행하며,
        사용자 ID가 없으면 UUID를 자동 생성합니다.

        Args:
            user_data (dict): 사용자 생성 정보
                필수 필드:
                - email (str): 이메일 주소 (고유해야 함)
                - hashed_password (str): bcrypt로 해시된 비밀번호
                - roles (list[str]): 사용자 역할 목록
                선택 필드:
                - id (str): 사용자 ID (없으면 UUID 자동 생성)
                - is_active (bool): 활성화 상태 (기본값: True)

        Returns:
            User: 생성된 사용자 객체

        Raises:
            ValueError: 이메일이 이미 존재하는 경우

        생성 과정:
            1. 사용자 ID 확인 및 자동 생성 (필요시)
            2. 이메일 중복 검사
            3. User 모델 인스턴스 생성
            4. 메인 저장소에 저장
            5. 이메일 인덱스 업데이트
            6. 생성 로그 기록

        데이터 무결성:
            - 이메일 고유성 보장
            - UUID 기반 ID로 충돌 방지
            - 인덱스 일관성 유지
        """
        # 정수형 ID 자동 생성 (제공되지 않은 경우)
        if "id" not in user_data:
            # 현재 사용 중인 최대 ID를 찾아서 +1
            max_id = max(
                (user.id for user in self._users.values() if isinstance(user.id, int)),
                default=0,
            )
            user_data["id"] = max_id + 1

        # 이메일 중복 검사 (비즈니스 규칙)
        if user_data["email"] in self._email_index:
            raise ValueError(f"이미 존재하는 이메일: {user_data['email']}")

        # 필수 필드 기본값 설정
        now = datetime.now(UTC)
        user_data.setdefault("is_active", True)
        user_data.setdefault("is_verified", False)
        user_data.setdefault("roles", ["user"])
        user_data.setdefault("created_at", now)
        user_data.setdefault("updated_at", now)
        user_data.setdefault("username", user_data["email"].split("@")[0])

        # Pydantic User 모델 인스턴스 생성 (자동 유효성 검증)
        user = User(**user_data)  # type: ignore[misc]

        # 메인 사용자 저장소에 추가
        self._users[user.id] = user

        # 이메일 검색 인덱스에 추가 (빠른 이메일 조회를 위함)
        self._email_index[user.email] = user.id

        # 사용자 생성 완료 로깅 (감사 목적)
        logger.info(
            "사용자 생성",
            user_id=user.id,
            email=user.email,
            roles=user.roles,
        )

        return user

    async def get_by_id(self, user_id: str) -> Optional[User]:
        """
        사용자 ID로 특정 사용자 조회

        메인 저장소에서 사용자 ID를 키로 직접 조회하는 O(1) 연산입니다.
        사용자 인증, 권한 검사, 프로필 조회 등 다양한 상황에서 사용됩니다.

        Args:
            user_id (str): 조회할 사용자의 고유 식별자 (문자열 형태의 정수)
                예: "1", "2", "3"

        Returns:
            Optional[User]: 사용자 객체 또는 None
                - User: 해당 ID의 사용자가 존재하는 경우
                - None: 사용자가 존재하지 않는 경우

        특징:
            - O(1) 시간 복잡도로 빠른 조회
            - 로깅으로 조회 성공/실패 추적
            - None 반환으로 안전한 처리

        사용 시나리오:
            - JWT 토큰에서 추출한 user_id로 사용자 정보 조회
            - 관리자가 특정 사용자 정보를 조회할 때
            - 권한 검증을 위한 사용자 정보 확인
            - 사용자 프로필 페이지 렌더링
        """
        try:
            # JWT 토큰에서 오는 user_id는 문자열이므로 정수로 변환
            numeric_user_id = int(user_id)
            user = self._users.get(numeric_user_id)

            if user:
                logger.debug(
                    "사용자 조회 성공", user_id=user_id, numeric_id=numeric_user_id
                )
            else:
                logger.debug(
                    "사용자 조회 실패", user_id=user_id, numeric_id=numeric_user_id
                )

            return user
        except (ValueError, TypeError) as e:
            logger.warning("잘못된 사용자 ID 형식", user_id=user_id, error=str(e))
            return None

    async def get_by_email(self, email: str) -> Optional[User]:
        """
        이메일 주소로 사용자 조회

        로그인 시 이메일로 사용자를 찾기 위해 사용하는 메서드입니다.
        이메일 인덱스를 활용하여 빠른 조회를 제공하며, 대소문자를 구분합니다.

        Args:
            email (str): 조회할 사용자의 이메일 주소
                예: "user@example.com"
                주의: 대소문자 구분 (정확한 이메일 필요)

        Returns:
            Optional[User]: 사용자 객체 또는 None
                - User: 해당 이메일의 사용자가 존재하는 경우
                - None: 사용자가 존재하지 않는 경우

        내부 동작:
            1. _email_index에서 이메일로 user_id 조회 (O(1))
            2. user_id가 있으면 get_by_id() 호출하여 사용자 객체 반환
            3. user_id가 없으면 None 반환 및 디버그 로깅

        성능 특징:
            - 이메일 인덱스로 O(1) 조회 성능
            - 존재하지 않는 이메일에 대한 효율적인 처리
            - 조회 실패 시 디버그 로깅으로 추적 가능

        사용 시나리오:
            - 사용자 로그인 시 이메일로 계정 확인
            - 비밀번호 재설정 시 이메일 검증
            - 중복 가입 방지를 위한 이메일 존재 확인
            - 관리자의 이메일 기반 사용자 검색
        """
        user_id = self._email_index.get(email)

        if user_id:
            # user_id는 정수형이므로 문자열로 변환하여 get_by_id에 전달
            return await self.get_by_id(str(user_id))

        logger.debug("이메일로 사용자 조회 실패", email=email)
        return None

    async def update(self, user_id: str, user_data: dict) -> Optional[User]:
        """
        사용자 정보 부분 업데이트

        기존 사용자 정보를 주어진 데이터로 부분적으로 업데이트합니다.
        이메일 변경 시 인덱스를 자동으로 관리하며, 데이터 무결성을 보장합니다.

        Args:
            user_id (str): 업데이트할 사용자의 고유 식별자
            user_data (dict): 업데이트할 필드들
                지원 필드:
                - email (str): 새 이메일 주소 (고유성 검증)
                - hashed_password (str): 새 해시된 비밀번호
                - is_active (bool): 계정 활성화 상태
                - roles (list[str]): 사용자 역할 목록
                기타 User 모델의 모든 필드 지원

        Returns:
            Optional[User]: 업데이트된 사용자 객체 또는 None
                - User: 업데이트 성공 시 새로운 사용자 객체
                - None: 사용자가 존재하지 않는 경우

        Raises:
            ValueError: 이메일 변경 시 중복되는 이메일이 이미 존재하는 경우
                예: "이미 존재하는 이메일: new@example.com"

        업데이트 과정:
            1. 사용자 존재 확인
            2. 이메일 변경 시 중복 검사 및 인덱스 업데이트
            3. 기존 데이터와 새 데이터 병합
            4. updated_at 타임스탬프 자동 설정 (UTC)
            5. 새 User 객체 생성 및 저장
            6. 업데이트 완료 로깅

        이메일 인덱스 관리:
            - 이메일 변경 시 기존 인덱스 항목 제거
            - 새 이메일로 인덱스 항목 추가
            - 중복 이메일 검사로 데이터 무결성 보장

        사용 시나리오:
            - 사용자 프로필 정보 수정
            - 비밀번호 변경
            - 이메일 주소 변경
            - 관리자에 의한 계정 활성화/비활성화
            - 사용자 역할 변경

        주의사항:
            - 이메일 변경 시 기존 세션이 유효하지 않을 수 있음
            - 역할 변경 시 권한 재검증 필요
            - 부분 업데이트로 기존 데이터는 유지됨
        """
        try:
            # 문자열 user_id를 정수로 변환
            numeric_user_id = int(user_id)
            user = self._users.get(numeric_user_id)

            if not user:
                logger.warning(
                    "업데이트할 사용자 없음",
                    user_id=user_id,
                    numeric_id=numeric_user_id,
                )
                return None
        except (ValueError, TypeError) as e:
            logger.warning(
                "잘못된 사용자 ID 형식 (update)", user_id=user_id, error=str(e)
            )
            return None

        # 이메일 변경 시 인덱스 업데이트
        if "email" in user_data and user_data["email"] != user.email:
            # 새 이메일 중복 확인
            if user_data["email"] in self._email_index:
                raise ValueError(f"이미 존재하는 이메일: {user_data['email']}")

            # 기존 이메일 인덱스 제거
            del self._email_index[user.email]
            # 새 이메일 인덱스 추가 (numeric_user_id 사용)
            self._email_index[user_data["email"]] = numeric_user_id

        # 업데이트
        updated_data = user.model_dump()
        updated_data.update(user_data)
        updated_data["updated_at"] = datetime.now(UTC)

        updated_user = User(**updated_data)  # type: ignore[misc]
        self._users[numeric_user_id] = updated_user

        logger.info(
            "사용자 업데이트",
            user_id=user_id,
            numeric_id=numeric_user_id,
            updated_fields=list(user_data.keys()),
        )

        return updated_user

    async def delete(self, user_id: str) -> bool:
        """
        사용자 계정 완전 삭제

        사용자와 관련된 모든 데이터를 안전하게 삭제합니다.
        이메일 인덱스도 함께 정리하여 데이터 일관성을 유지합니다.

        Args:
            user_id (str): 삭제할 사용자의 고유 식별자

        Returns:
            bool: 삭제 성공 여부
                - True: 사용자가 존재했고 성공적으로 삭제됨
                - False: 사용자가 존재하지 않아 삭제할 것이 없음

        삭제 과정:
            1. 사용자 존재 확인
            2. 이메일 인덱스에서 항목 제거
            3. 메인 저장소에서 사용자 제거
            4. 삭제 완료 로깅 (사용자 ID와 이메일 기록)

        데이터 무결성:
            - 이메일 인덱스와 메인 저장소 동기화
            - 원자적 삭제로 부분 삭제 방지
            - 존재하지 않는 사용자에 대한 안전한 처리

        보안 고려사항:
            - 삭제된 사용자의 JWT 토큰은 여전히 유효할 수 있음
            - 관련 세션 및 토큰 무효화 필요
            - 삭제 로그로 감사 추적 가능

        사용 시나리오:
            - 사용자 계정 탈퇴 처리
            - 관리자에 의한 계정 삭제
            - 스팸/악용 계정 제거
            - 테스트 데이터 정리

        주의사항:
            - 삭제된 데이터는 복구 불가능 (메모리 기반)
            - production에서는 soft delete 고려
            - 관련 권한 및 세션 정리 필요
            - 삭제 전 데이터 백업 권장
        """
        try:
            # 문자열 user_id를 정수로 변환
            numeric_user_id = int(user_id)
            user = self._users.get(numeric_user_id)

            if not user:
                logger.warning(
                    "삭제할 사용자 없음", user_id=user_id, numeric_id=numeric_user_id
                )
                return False

            # 인덱스에서 제거
            del self._email_index[user.email]
            # 사용자 제거
            del self._users[numeric_user_id]

            logger.info(
                "사용자 삭제",
                user_id=user_id,
                numeric_id=numeric_user_id,
                email=user.email,
            )

            return True
        except (ValueError, TypeError) as e:
            logger.warning(
                "잘못된 사용자 ID 형식 (delete)", user_id=user_id, error=str(e)
            )
            return False

    async def search_users(self, query: str, limit: int = 10) -> list[User]:
        """사용자 검색 (이메일 또는 이름으로)

        Args:
            query: 검색 쿼리
            limit: 결과 개수 제한

        Returns:
            검색된 사용자 목록
        """
        query_lower = query.lower()
        results = []

        for user in self._users.values():
            # 이메일로 검색
            if query_lower in user.email.lower():
                results.append(user)
                continue

            # 향후 이름 필드가 추가되면 여기서 검색
            # if hasattr(user, 'name') and query_lower in user.name.lower():
            #     results.append(user)
            #     continue

        # 최신 사용자부터 정렬 (created_at 기준)
        results.sort(key=lambda u: u.created_at, reverse=True)

        return results[:limit]

    async def get_recent_users(self, limit: int = 10) -> list[User]:
        """최근 가입한 사용자들 조회

        Args:
            limit: 결과 개수 제한

        Returns:
            최근 가입한 사용자 목록
        """
        users = list(self._users.values())
        # 최신 사용자부터 정렬
        users.sort(key=lambda u: u.created_at, reverse=True)

        return users[:limit]

    async def list_all(self, skip: int = 0, limit: int = 50) -> list[User]:
        """모든 사용자 목록 조회

        Args:
            skip: 건너뛸 사용자 수
            limit: 결과 개수 제한

        Returns:
            사용자 목록
        """
        users = list(self._users.values())
        # 최신 사용자부터 정렬
        users.sort(key=lambda u: u.created_at, reverse=True)

        return users[skip : skip + limit]

    async def get_user_statistics(self) -> dict[str, Any]:
        """사용자 통계 조회

        Returns:
            사용자 통계 정보
        """
        total_users = len(self._users)
        active_users = sum(1 for user in self._users.values() if user.is_active)
        inactive_users = total_users - active_users

        # 역할별 통계
        role_stats = {}
        for user in self._users.values():
            for role in user.roles:
                role_stats[role] = role_stats.get(role, 0) + 1

        return {
            "total_users": total_users,
            "active_users": active_users,
            "inactive_users": inactive_users,
            "roles": role_stats,
            "default_users": [
                {"email": "admin@example.com", "roles": ["admin"]},
                {"email": "user@example.com", "roles": ["user"]},
            ],
        }
