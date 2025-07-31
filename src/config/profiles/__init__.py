"""
환경별 설정 프로파일

각 환경(개발, 스테이징, 프로덕션)에 맞는 사전 정의된 설정을 제공합니다.
"""

from .dev import DEV_CONFIG
from .staging import STAGING_CONFIG
from .prod import PROD_CONFIG

__all__ = [
    "DEV_CONFIG",
    "STAGING_CONFIG", 
    "PROD_CONFIG",
]