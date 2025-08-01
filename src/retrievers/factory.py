"""
리트리버 팩토리 패턴 구현

이 모듈은 설정을 바탕으로 리트리버 인스턴스를 생성하는 팩토리 패턴을 구현합니다.
팩토리 패턴을 통해 객체 생성 로직을 중앙화하고, 런타임에 타입을 결정할 수 있습니다.

주요 기능:
    - 동적 리트리버 인스턴스 생성
    - 커스텀 리트리버 등록 지원
    - 기본 제공 리트리버 자동 등록
    - 설정 기반 객체 생성
    - 타입 안전성 보장

디자인 패턴:
    Factory Method Pattern - 구체적인 클래스를 지정하지 않고 객체 생성
    Singleton Pattern - 기본 팩토리 인스턴스는 싱글톤으로 관리
"""

from typing import Type, Any
import structlog

from src.retrievers.base import Retriever, RetrieverConfig


class RetrieverFactoryError(Exception):
    """
    리트리버 팩토리 전용 예외

    팩토리에서 리트리버 생성 중 발생하는 에러를 나타냅니다.
    등록되지 않은 타입이나 생성 실패 시 발생합니다.
    """

    pass


class RetrieverFactory:
    """
    리트리버 인스턴스 생성을 위한 팩토리 클래스

    설정 기반으로 적절한 리트리버 인스턴스를 생성하는 중앙화된 팩토리입니다.
    팩토리 메서드 패턴을 사용하여 객체 생성 로직을 캡슐화하고,
    새로운 리트리버 타입을 동적으로 등록할 수 있습니다.

    사용 예시:
        ```python
        # 기본 팩토리 사용
        factory = RetrieverFactory.get_default()
        config = {"type": "tavily", "api_key": "your-key"}
        retriever = factory.create(config)

        # 커스텀 리트리버 등록
        factory.register("custom", CustomRetriever)
        ```

    Attributes:
        _retrievers (dict[str, Type[Retriever]]): 등록된 리트리버 클래스들
        logger: 구조화된 로거 인스턴스
        _default_instance: 싱글톤 기본 인스턴스
    """

    _default_instance: "RetrieverFactory | None" = None

    def __init__(self, register_defaults: bool = False) -> None:
        """
        리트리버 팩토리 초기화

        빈 레지스트리로 시작하여 필요시 기본 리트리버들을 등록합니다.
        각 팩토리 인스턴스는 독립적인 레지스트리를 가집니다.

        Args:
            register_defaults (bool): 기본 리트리버 자동 등록 여부
                True: Tavily, PostgreSQL, Qdrant 리트리버 자동 등록
                False: 빈 레지스트리로 시작 (수동 등록 필요)
        """
        # 리트리버 클래스를 저장하는 레지스트리
        self._retrievers: dict[str, Type[Retriever]] = {}

        # 구조화된 로깅을 위한 로거 설정
        self.logger = structlog.get_logger(self.__class__.__name__)

        # 기본 리트리버 등록 (선택사항)
        if register_defaults:
            self._register_default_retrievers()

    def register(self, name: str, retriever_class: Any) -> None:
        """
        리트리버 클래스 등록

        새로운 리트리버 클래스를 팩토리에 등록하여 create() 메서드에서
        사용할 수 있도록 합니다. 등록 시 타입 검증을 수행합니다.

        Args:
            name (str): 리트리버를 식별하는 고유한 이름
                설정의 'type' 필드에서 사용될 이름
            retriever_class (Any): 등록할 리트리버 클래스
                Retriever를 상속받은 클래스여야 함

        Raises:
            ValueError: retriever_class가 유효하지 않은 경우
                - 클래스가 아닌 경우 (함수, 객체 등)
                - Retriever를 상속받지 않은 경우

        Example:
            ```python
            factory.register("custom", CustomRetriever)
            # 이후 {"type": "custom", ...} 설정으로 생성 가능
            ```
        """
        # 클래스 타입인지 검증
        if not isinstance(retriever_class, type):
            raise ValueError(f"Retriever must be a class, got {type(retriever_class)}")

        # Retriever 기본 클래스를 상속받았는지 검증
        if not issubclass(retriever_class, Retriever):
            raise ValueError("Retriever must be a subclass of Retriever")

        # 레지스트리에 클래스 등록
        self._retrievers[name] = retriever_class

        # 등록 성공 로깅 (구조화된 로그)
        self.logger.info(
            "Registered retriever", name=name, class_name=retriever_class.__name__
        )

    def create(self, config: RetrieverConfig) -> Retriever:
        """
        설정을 기반으로 리트리버 인스턴스 생성

        주어진 설정 딕셔너리에서 'type' 필드를 확인하여 해당하는
        리트리버 클래스를 찾고 인스턴스를 생성합니다. 팩토리 패턴의 핵심 메서드입니다.

        Args:
            config (RetrieverConfig): 리트리버 설정 딕셔너리
                반드시 'type' 필드를 포함해야 함
                예: {"type": "tavily", "api_key": "your-key", "timeout": 30}

        Returns:
            Retriever: 설정에 따라 생성된 리트리버 인스턴스
                생성된 인스턴스는 아직 연결되지 않은 상태 (connect() 호출 필요)

        Raises:
            TypeError: config이 딕셔너리가 아닌 경우
            ValueError: config에 'type' 필드가 없는 경우
            RetrieverFactoryError: 다음의 경우들
                - 알 수 없는 리트리버 타입인 경우
                - 리트리버 인스턴스 생성에 실패한 경우

        Example:
            ```python
            config = {
                "type": "tavily",
                "api_key": "your-api-key",
                "max_results": 10
            }
            retriever = factory.create(config)
            await retriever.connect()
            ```
        """
        # 설정이 딕셔너리인지 검증
        if not isinstance(config, dict):
            raise TypeError("Config must be a dictionary")

        # 필수 'type' 필드 존재 확인
        if "type" not in config:
            raise ValueError("Config must contain 'type' field")

        retriever_type = config["type"]

        # 등록된 리트리버 타입인지 확인
        if retriever_type not in self._retrievers:
            available = ", ".join(self._retrievers.keys())
            raise RetrieverFactoryError(
                f"Unknown retriever type: {retriever_type}. Available: {available}"
            )

        # 'type' 필드를 제외한 설정으로 리트리버별 설정 생성
        # 리트리버 생성자는 'type' 필드를 받지 않으므로 제거
        retriever_config = {k: v for k, v in config.items() if k != "type"}

        try:
            # 등록된 클래스로 인스턴스 생성
            retriever_class = self._retrievers[retriever_type]
            retriever = retriever_class(retriever_config)

            # 생성 성공 로깅
            self.logger.info(
                "Created retriever",
                type=retriever_type,
                class_name=retriever_class.__name__,
            )

            return retriever

        except Exception as e:
            # 생성 실패 시 원본 예외를 체인으로 연결하여 디버깅 정보 보존
            raise RetrieverFactoryError(
                f"Failed to create retriever of type '{retriever_type}': {e}"
            ) from e

    def list_available(self) -> list[str]:
        """
        등록된 리트리버 타입 목록 조회

        현재 팩토리에 등록된 모든 리트리버 타입의 이름을 반환합니다.
        create() 메서드에서 사용할 수 있는 'type' 값들입니다.

        Returns:
            list[str]: 등록된 리트리버 타입 이름 목록
                예: ["tavily", "postgres", "qdrant"]
        """
        return list(self._retrievers.keys())

    def get_retriever_class(self, name: str) -> Type[Retriever] | None:
        """
        이름으로 등록된 리트리버 클래스 조회

        등록된 리트리버 클래스를 직접 가져올 때 사용합니다.
        주로 디버깅이나 리플렉션 목적으로 사용됩니다.

        Args:
            name (str): 조회할 리트리버 타입 이름

        Returns:
            Type[Retriever] | None: 리트리버 클래스 또는 None (미등록 시)
                클래스 자체를 반환하므로 직접 인스턴스 생성 가능
        """
        return self._retrievers.get(name)

    def _register_default_retrievers(self) -> None:
        """
        기본 제공 리트리버들 등록

        프로젝트에서 기본으로 제공하는 리트리버들을 자동 등록합니다.
        순환 임포트를 방지하기 위해 필요할 때만 임포트합니다.

        등록되는 리트리버들:
            - tavily: Tavily 웹 검색 API
            - postgres: PostgreSQL 데이터베이스
            - qdrant: Qdrant 벡터 데이터베이스
        """
        # 순환 임포트 방지를 위해 지연 임포트 사용
        from src.retrievers.tavily import TavilyRetriever
        from src.retrievers.postgres import PostgresRetriever
        from src.retrievers.qdrant import QdrantRetriever

        # 각 리트리버를 고유한 이름으로 등록
        self.register("tavily", TavilyRetriever)
        self.register("postgres", PostgresRetriever)
        self.register("qdrant", QdrantRetriever)

    @classmethod
    def get_default(cls) -> "RetrieverFactory":
        """
        기본 리트리버들이 등록된 싱글톤 팩토리 인스턴스 조회

        애플리케이션 전체에서 공유하는 기본 팩토리 인스턴스를 반환합니다.
        싱글톤 패턴을 사용하여 메모리 효율성과 일관성을 보장합니다.

        첫 호출 시 팩토리를 생성하고 기본 리트리버들을 자동 등록합니다.
        이후 호출에서는 동일한 인스턴스를 반환합니다.

        Returns:
            RetrieverFactory: 기본 리트리버들이 등록된 팩토리 인스턴스
                tavily, postgres, qdrant 리트리버가 미리 등록된 상태

        Example:
            ```python
            # 애플리케이션 어디서든 동일한 팩토리 사용
            factory = RetrieverFactory.get_default()

            # 즉시 사용 가능한 리트리버 타입들
            print(factory.list_available())  # ["tavily", "postgres", "qdrant"]
            ```
        """
        if cls._default_instance is None:
            # 첫 호출 시 기본 리트리버들과 함께 인스턴스 생성
            cls._default_instance = cls(register_defaults=True)
        return cls._default_instance
