# MCP 서버 Clean Code Architecture 리팩토링 계획

## 🎯 목표

1. **Clean Code Architecture 원칙 적용**
2. **코드 중복 제거 및 모듈화**
3. **유지보수성 및 확장성 향상**
4. **보안 및 성능 최적화**

## 📊 현재 코드베이스 분석

### 1. 아키텍처 문제점

#### 1.1 서버 파일 중복 (높은 우선순위)
- **문제**: 4개의 서버 파일이 유사한 구조와 중복 코드 포함
  - `server_auth.py`: 기본 인증 서버
  - `server_context.py`: 컨텍스트 추적 서버
  - `server_with_cache.py`: 캐싱 통합 서버
  - `server_complete.py`: 모든 기능 통합 서버
- **중복 코드**:
  - 리트리버 초기화 로직 (100% 동일)
  - 도구 함수 구현 (80% 유사)
  - 메인 실행부 (100% 동일)
  - 환경 변수 로딩 (90% 동일)

#### 1.2 계층 혼재
- **문제**: 인프라, 도메인, 애플리케이션 로직이 혼재
  - `database.py`: 엔진 설정과 모델이 같은 파일에
  - 리트리버: 비즈니스 로직과 인프라 코드 혼재
  - 미들웨어: 횡단 관심사가 각 서버에 분산

#### 1.3 설정 관리 분산
- **문제**: 환경 변수가 여러 파일에 분산되어 관리
- **보안 이슈**: API 키가 코드에 하드코딩된 부분 존재

### 2. 코드 품질 이슈

#### 2.1 중복 함수
- 각 서버 파일의 `search_*` 함수들이 거의 동일
- `_search_single_source` 헬퍼 함수 중복
- 리트리버 초기화 코드 중복

#### 2.2 테스트 커버리지
- 현재 테스트 커버리지 미확인
- 통합 테스트는 있으나 단위 테스트 부족
- 모킹 전략 일관성 부족

## 🏗️ 리팩토링 계획

### Phase 1: 서버 통합 (1주차)

#### 1.1 통합 서버 구조 설계

```
src/
├── server.py              # 통합 서버 (새로 생성)
├── config/               # 설정 관리 (새로 생성)
│   ├── __init__.py
│   ├── settings.py       # 설정 클래스
│   ├── profiles/         # 환경별 프로파일
│   │   ├── dev.py
│   │   ├── staging.py
│   │   └── prod.py
│   └── validators.py     # 설정 검증
├── core/                 # 핵심 도메인 (새로 생성)
│   ├── __init__.py
│   ├── interfaces/       # 인터페이스 정의
│   │   ├── retriever.py
│   │   └── cache.py
│   └── tools/           # 도구 함수 구현
│       ├── search.py
│       ├── cache.py
│       └── metrics.py
```

#### 1.2 통합 서버 구현

```python
# src/config/settings.py
from dataclasses import dataclass, field
from typing import Optional, List, Dict
import os
from enum import Enum

class ServerProfile(Enum):
    """서버 프로파일"""
    BASIC = "basic"          # 기본 서버
    AUTH = "auth"            # 인증 서버
    CONTEXT = "context"      # 컨텍스트 서버
    CACHED = "cached"        # 캐싱 서버
    COMPLETE = "complete"    # 완전 통합 서버
    CUSTOM = "custom"        # 사용자 정의

@dataclass
class ServerConfig:
    """통합 서버 설정"""
    # 기본 설정
    name: str = "mcp-retriever"
    profile: ServerProfile = ServerProfile.BASIC
    transport: str = "stdio"
    port: int = 8001
    
    # 기능 플래그
    features: Dict[str, bool] = field(default_factory=lambda: {
        "auth": False,
        "context": False,
        "cache": False,
        "rate_limit": False,
        "metrics": False,
        "validation": False,
        "error_handler": True,
        "enhanced_logging": False,
    })
    
    # 컴포넌트별 설정
    auth_config: Optional['AuthConfig'] = None
    cache_config: Optional['CacheConfig'] = None
    rate_limit_config: Optional['RateLimitConfig'] = None
    
    @classmethod
    def from_profile(cls, profile: ServerProfile) -> 'ServerConfig':
        """프로파일 기반 설정 생성"""
        base_config = cls(profile=profile)
        
        if profile == ServerProfile.BASIC:
            base_config.features.update({
                "auth": False,
                "context": False,
                "cache": False,
            })
        elif profile == ServerProfile.AUTH:
            base_config.features.update({
                "auth": True,
                "context": False,
                "cache": False,
            })
        elif profile == ServerProfile.CONTEXT:
            base_config.features.update({
                "auth": True,
                "context": True,
                "cache": False,
            })
        elif profile == ServerProfile.CACHED:
            base_config.features.update({
                "auth": True,
                "context": False,
                "cache": True,
            })
        elif profile == ServerProfile.COMPLETE:
            base_config.features.update({
                "auth": True,
                "context": True,
                "cache": True,
                "rate_limit": True,
                "metrics": True,
                "validation": True,
                "enhanced_logging": True,
            })
            
        return base_config
    
    @classmethod
    def from_env(cls) -> 'ServerConfig':
        """환경 변수에서 설정 로드"""
        profile_name = os.getenv("MCP_PROFILE", "BASIC").upper()
        try:
            profile = ServerProfile[profile_name]
            config = cls.from_profile(profile)
        except KeyError:
            config = cls(profile=ServerProfile.CUSTOM)
            
        # 개별 기능 오버라이드
        for feature in config.features:
            env_key = f"MCP_ENABLE_{feature.upper()}"
            if env_value := os.getenv(env_key):
                config.features[feature] = env_value.lower() == "true"
                
        return config
```

#### 1.3 구현 단계

1. **통합 서버 클래스 생성**
   ```python
   # src/server.py
   class UnifiedMCPServer:
       def __init__(self, config: ServerConfig):
           self.config = config
           self.components = self._init_components()
           
       def _init_components(self):
           """설정 기반 컴포넌트 초기화"""
           components = {}
           
           if self.config.features["auth"]:
               components["auth"] = self._create_auth_component()
           if self.config.features["cache"]:
               components["cache"] = self._create_cache_component()
           # ... 기타 컴포넌트
           
           return components
   ```

2. **기존 서버 파일 마이그레이션**
   - 각 서버의 고유 기능을 컴포넌트로 추출
   - 공통 코드를 base 클래스로 이동
   - 도구 함수를 `core/tools/`로 이동

3. **하위 호환성 유지**
   ```python
   # src/server_auth.py (임시 유지)
   import warnings
   from src.server import UnifiedMCPServer, ServerConfig, ServerProfile
   
   warnings.warn(
       "server_auth.py는 deprecated되었습니다. "
       "src.server를 사용하고 MCP_PROFILE=AUTH를 설정하세요.",
       DeprecationWarning
   )
   
   if __name__ == "__main__":
       config = ServerConfig.from_profile(ServerProfile.AUTH)
       server = UnifiedMCPServer(config)
       server.run()
   ```

### Phase 2: 인프라 계층 분리 (2주차)

#### 2.1 설정 중앙화

```
src/
├── infrastructure/       # 인프라 계층
│   ├── __init__.py
│   ├── database/        # DB 관련
│   │   ├── engine.py    # DB 엔진 설정
│   │   ├── session.py   # 세션 관리
│   │   └── migrations/  # 마이그레이션
│   ├── cache/          # 캐시 인프라
│   │   ├── redis.py
│   │   └── memory.py
│   └── external/       # 외부 서비스
│       ├── tavily.py
│       └── qdrant.py
```

#### 2.2 의존성 주입

```python
# src/infrastructure/container.py
from dependency_injector import containers, providers

class Container(containers.DeclarativeContainer):
    """DI 컨테이너"""
    
    # 설정
    config = providers.Singleton(
        ServerConfig.from_env
    )
    
    # 인프라
    database = providers.Singleton(
        DatabaseEngine,
        config=config.provided.database_config
    )
    
    redis_client = providers.Singleton(
        RedisClient,
        url=config.provided.cache_config.redis_url
    )
    
    # 리트리버
    tavily_retriever = providers.Factory(
        TavilyRetriever,
        api_key=config.provided.external_apis.tavily_key
    )
```

### Phase 3: 코드 정리 및 최적화 (3주차)

#### 3.1 Utils 모듈 중앙화

```
src/
├── utils/              # 유틸리티 모듈
│   ├── __init__.py
│   ├── logging.py     # 로깅 유틸
│   ├── decorators.py  # 공통 데코레이터
│   ├── validators.py  # 입력 검증
│   └── helpers.py     # 기타 헬퍼
```

#### 3.2 중복 코드 제거

1. **도구 함수 통합**
   ```python
   # src/core/tools/search.py
   class SearchTools:
       """검색 도구 통합 클래스"""
       
       def __init__(self, retrievers: Dict[str, Retriever]):
           self.retrievers = retrievers
           
       async def search_web(self, query: str, **kwargs):
           """웹 검색 (기존 중복 코드 통합)"""
           return await self._search_with_retriever(
               "tavily", query, **kwargs
           )
           
       async def _search_with_retriever(
           self, retriever_name: str, query: str, **kwargs
       ):
           """공통 검색 로직"""
           # 중복 제거된 검색 구현
   ```

2. **리트리버 팩토리 개선**
   ```python
   # src/retrievers/factory.py
   class RetrieverFactory:
       """개선된 리트리버 팩토리"""
       
       def __init__(self, container: Container):
           self.container = container
           
       def create_all(self, config: ServerConfig) -> Dict[str, Retriever]:
           """설정 기반 모든 리트리버 생성"""
           retrievers = {}
           
           for name, retriever_config in config.retrievers.items():
               if retriever_config.enabled:
                   retrievers[name] = self._create_retriever(
                       name, retriever_config
                   )
                   
           return retrievers
   ```

### Phase 4: 보안 및 성능 강화 (4주차)

#### 4.1 환경 변수 관리

```python
# src/config/env.py
from pydantic import BaseSettings, SecretStr, validator

class EnvironmentSettings(BaseSettings):
    """환경 변수 설정 (Pydantic 기반)"""
    
    # API 키 (자동 마스킹)
    tavily_api_key: SecretStr
    qdrant_api_key: Optional[SecretStr] = None
    
    # 데이터베이스
    postgres_dsn: SecretStr
    
    # Redis
    redis_url: str = "redis://localhost:6379/0"
    
    # JWT
    jwt_secret_key: SecretStr
    jwt_algorithm: str = "HS256"
    
    @validator("postgres_dsn")
    def validate_postgres_dsn(cls, v):
        """PostgreSQL DSN 검증"""
        # DSN 형식 검증
        return v
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
```

#### 4.2 보안 강화

1. **시크릿 관리**
   ```python
   # src/infrastructure/secrets.py
   class SecretManager:
       """시크릿 관리자"""
       
       def __init__(self, provider: str = "env"):
           self.provider = self._get_provider(provider)
           
       def get_secret(self, key: str) -> str:
           """시크릿 조회 (캐싱 포함)"""
           return self.provider.get(key)
   ```

2. **API 키 로테이션**
   ```python
   # src/infrastructure/security/rotation.py
   class APIKeyRotation:
       """API 키 자동 로테이션"""
       
       async def rotate_keys(self):
           """주기적 키 로테이션"""
           # 구현
   ```

### Phase 5: 테스트 강화 (5주차)

#### 5.1 테스트 구조 개선

```
tests/
├── unit/              # 단위 테스트
│   ├── test_config.py
│   ├── test_tools.py
│   └── test_retrievers.py
├── integration/       # 통합 테스트
│   ├── test_server.py
│   └── test_middleware.py
├── e2e/              # E2E 테스트
│   └── test_scenarios.py
└── fixtures/         # 테스트 픽스처
    ├── config.py
    └── mocks.py
```

#### 5.2 테스트 커버리지 목표

- 단위 테스트: 90% 이상
- 통합 테스트: 80% 이상
- E2E 테스트: 주요 시나리오 100%

## 📅 구현 일정

### Week 1: 서버 통합
- [ ] 통합 서버 클래스 구현
- [ ] 설정 시스템 구현
- [ ] 기존 서버 마이그레이션
- [ ] 기본 테스트 작성

### Week 2: 인프라 분리
- [ ] 인프라 계층 구조 생성
- [ ] DI 컨테이너 구현
- [ ] 데이터베이스 설정 분리
- [ ] 외부 서비스 추상화

### Week 3: 코드 정리
- [ ] Utils 모듈 중앙화
- [ ] 중복 코드 제거
- [ ] 리팩토링된 코드 테스트
- [ ] 문서 업데이트

### Week 4: 보안/성능
- [ ] 환경 변수 관리 개선
- [ ] 시크릿 관리 구현
- [ ] 성능 최적화
- [ ] 보안 감사

### Week 5: 테스트/마무리
- [ ] 테스트 커버리지 향상
- [ ] E2E 테스트 작성
- [ ] 성능 테스트
- [ ] 최종 문서화

## ✅ 성공 지표

1. **코드 품질**
   - 코드 중복 50% 이상 감소
   - 순환 복잡도 10 이하
   - 테스트 커버리지 85% 이상

2. **성능**
   - 서버 시작 시간 30% 단축
   - 메모리 사용량 20% 감소
   - API 응답 시간 10% 개선

3. **유지보수성**
   - 새 기능 추가 시간 50% 단축
   - 버그 수정 시간 40% 단축
   - 온보딩 시간 30% 단축

## 🚨 위험 요소 및 대응

1. **하위 호환성**
   - 위험: 기존 사용자 영향
   - 대응: Deprecation 경고 및 마이그레이션 가이드

2. **성능 저하**
   - 위험: 추상화로 인한 오버헤드
   - 대응: 프로파일링 및 최적화

3. **복잡도 증가**
   - 위험: 과도한 추상화
   - 대응: KISS 원칙 준수

## 📝 마이그레이션 가이드

### 기존 사용자를 위한 가이드

```bash
# 기존 방식 (deprecated)
python -m src.server_auth

# 새로운 방식
MCP_PROFILE=AUTH python -m src.server

# 또는 통합된 환경 변수 파일 사용
cp .env.example .env
# .env 파일에서 MCP_PROFILE=AUTH로 설정
python -m src.server_unified
```

### Docker 사용자

```dockerfile
# 기존 Dockerfile
CMD ["python", "-m", "src.server_complete"]

# 새로운 Dockerfile
ENV MCP_PROFILE=COMPLETE
CMD ["python", "-m", "src.server"]
```

## 🔄 지속적 개선

1. **월간 리뷰**
   - 성능 메트릭 분석
   - 사용자 피드백 수집
   - 개선 사항 도출

2. **분기별 업데이트**
   - 새로운 기능 추가
   - 보안 패치
   - 의존성 업데이트

3. **연간 메이저 업데이트**
   - 아키텍처 재검토
   - 새로운 패턴 적용
   - 성능 최적화