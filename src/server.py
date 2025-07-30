"""
기존 server.py 호환성 레이어

기존 테스트와의 호환성을 위해 server_test_adapter로 리다이렉션합니다.
프로덕션에서는 server_unified.py를 직접 사용하세요.
"""

# 테스트 어댑터로 모든 것을 리다이렉션
from src.server_test_adapter import *