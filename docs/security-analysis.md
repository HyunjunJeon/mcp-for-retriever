# 보안 분석 및 강화 방안

## 현재 보안 취약점 분석

### 1. 인증 및 인가
- **문제점**: 
  - JWT 비밀 키가 환경 변수로만 관리됨
  - 토큰 탈취 시 세션 무효화 어려움
  - 비밀번호 복잡성 검증이 있지만 브루트포스 공격에 대한 방어 부족

- **개선 방안**:
  ```python
  # Redis를 활용한 토큰 블랙리스트
  class TokenBlacklist:
      async def revoke_token(self, token: str, expires_in: int):
          await self.redis.setex(f"blacklist:{token}", expires_in, "1")
      
      async def is_revoked(self, token: str) -> bool:
          return await self.redis.exists(f"blacklist:{token}")
  ```

### 2. Rate Limiting
- **문제점**: API 레벨에서 rate limiting이 없음
- **개선 방안**:
  ```python
  # Redis 기반 Rate Limiter
  from src.cache.redis_cache import RedisCache
  
  class RateLimiter:
      def __init__(self, redis: RedisCache):
          self.redis = redis
      
      async def check_rate_limit(
          self, 
          key: str, 
          max_requests: int, 
          window_seconds: int
      ) -> tuple[bool, int]:
          current = await self.redis.increment(key)
          if current == 1:
              await self.redis.expire(key, window_seconds)
          
          remaining = max(0, max_requests - current)
          return current <= max_requests, remaining
  ```

### 3. 입력 검증
- **문제점**: SQL 인젝션 가능성 (PostgresRetriever에서 raw SQL 허용)
- **개선 방안**:
  ```python
  # PostgresRetriever 개선
  ALLOWED_TABLES = ["users", "documents", "logs"]
  
  async def retrieve(self, query: str, **kwargs):
      # SQL 쿼리인 경우 파라미터화된 쿼리만 허용
      if "SELECT" in query.upper():
          # Prepared statement 사용 강제
          return await self.retrieve_prepared(query, **kwargs)
      
      # 테이블 이름 검증
      table = kwargs.get("table")
      if table and table not in ALLOWED_TABLES:
          raise QueryError(f"Access to table '{table}' is not allowed")
  ```

### 4. 시크릿 관리
- **문제점**: API 키가 환경 변수로만 관리됨
- **개선 방안**:
  - AWS Secrets Manager / HashiCorp Vault 연동
  - 키 로테이션 자동화
  ```python
  class SecretManager:
      async def get_secret(self, key: str) -> str:
          # AWS Secrets Manager 예시
          client = boto3.client('secretsmanager')
          response = client.get_secret_value(SecretId=key)
          return response['SecretString']
  ```

### 5. CORS 설정
- **개선된 설정**:
  ```python
  app.add_middleware(
      CORSMiddleware,
      allow_origins=["https://app.example.com"],  # 특정 도메인만
      allow_credentials=True,
      allow_methods=["GET", "POST"],
      allow_headers=["Authorization", "Content-Type"],
      expose_headers=["X-Total-Count"],
      max_age=3600
  )
  ```

## Nginx를 통한 보안 강화

### 1. SSL/TLS 설정
```nginx
server {
    listen 443 ssl http2;
    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;
    
    # 강화된 SSL 설정
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256';
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    
    # HSTS
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
}
```

### 2. 보안 헤더
```nginx
# 이미 nginx.conf에 포함된 헤더들
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;

# 추가 권장 헤더
add_header Permissions-Policy "geolocation=(), microphone=(), camera=()" always;
add_header X-Permitted-Cross-Domain-Policies "none" always;
```

### 3. Rate Limiting (nginx.conf에 이미 구현됨)
```nginx
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
limit_req zone=api_limit burst=20 nodelay;
```

### 4. 요청 크기 제한
```nginx
client_max_body_size 10M;
client_body_buffer_size 128k;
client_header_buffer_size 1k;
large_client_header_buffers 4 4k;
```

## 애플리케이션 레벨 보안 개선

### 1. 보안 미들웨어 추가
```python
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.sessions import SessionMiddleware

# 신뢰할 수 있는 호스트만 허용
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["api.mcp-retriever.com", "*.mcp-retriever.com"]
)

# 세션 보안
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SESSION_SECRET,
    https_only=True,
    same_site="strict"
)
```

### 2. 로깅 및 모니터링
```python
# 보안 이벤트 로깅
class SecurityLogger:
    async def log_failed_login(self, email: str, ip: str):
        logger.warning(
            "Failed login attempt",
            email=email,
            ip=ip,
            timestamp=datetime.utcnow()
        )
    
    async def log_suspicious_activity(self, user_id: str, action: str):
        logger.error(
            "Suspicious activity detected",
            user_id=user_id,
            action=action
        )
```

### 3. 데이터 암호화
```python
from cryptography.fernet import Fernet

class DataEncryption:
    def __init__(self, key: bytes):
        self.cipher = Fernet(key)
    
    def encrypt_sensitive_data(self, data: str) -> str:
        return self.cipher.encrypt(data.encode()).decode()
    
    def decrypt_sensitive_data(self, encrypted: str) -> str:
        return self.cipher.decrypt(encrypted.encode()).decode()
```

## 컨테이너 보안

### 1. Docker 이미지 보안
```dockerfile
# 비 root 사용자 실행 (이미 구현됨)
RUN useradd -m -u 1000 appuser
USER appuser

# 읽기 전용 파일시스템
# docker-compose.yml에 추가
security_opt:
  - no-new-privileges:true
read_only: true
tmpfs:
  - /tmp
```

### 2. 시크릿 관리
```yaml
# Kubernetes Secret
apiVersion: v1
kind: Secret
metadata:
  name: mcp-secrets
type: Opaque
data:
  jwt-secret-key: <base64-encoded>
  tavily-api-key: <base64-encoded>
```

## 추가 보안 권장사항

### 1. 정기적인 보안 스캔
- Dependency 취약점 스캔: `pip-audit`, `safety`
- 컨테이너 이미지 스캔: `trivy`, `clair`
- 코드 정적 분석: `bandit`, `semgrep`

### 2. 침입 탐지
- Fail2ban 설정으로 반복된 실패 시도 차단
- WAF(Web Application Firewall) 도입 고려

### 3. 백업 및 복구
- 데이터베이스 자동 백업
- 재해 복구 계획 수립

### 4. 규정 준수
- GDPR 준수: 개인정보 처리 동의, 삭제 권한
- 로그 보관 정책 수립

## 구현 우선순위

1. **즉시 구현**: Rate limiting, 토큰 블랙리스트, SQL 인젝션 방지
2. **단기 구현**: 시크릿 관리 개선, 보안 헤더 강화
3. **장기 구현**: WAF 도입, 자동화된 보안 스캔