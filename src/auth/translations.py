"""국제화(i18n) 번역 시스템

한국어와 영어를 지원하는 간단한 번역 시스템을 제공합니다.
세션 기반 언어 설정과 빠른 번역 함수를 포함합니다.
"""

from typing import Dict, Any, Optional
from fastapi import Request

# 지원하는 언어 코드
SUPPORTED_LANGUAGES = {
    "ko": "한국어",
    "en": "English"
}

# 번역 딕셔너리
TRANSLATIONS: Dict[str, Dict[str, str]] = {
    # 공통 용어
    "admin": {
        "ko": "관리자",
        "en": "Admin"
    },
    "user": {
        "ko": "사용자",
        "en": "User"
    },
    "dashboard": {
        "ko": "대시보드",
        "en": "Dashboard"
    },
    "login": {
        "ko": "로그인",
        "en": "Login"
    },
    "logout": {
        "ko": "로그아웃",
        "en": "Logout"
    },
    "email": {
        "ko": "이메일",
        "en": "Email"
    },
    "password": {
        "ko": "비밀번호",
        "en": "Password"
    },
    "username": {
        "ko": "사용자명",
        "en": "Username"
    },
    "role": {
        "ko": "역할",
        "en": "Role"
    },
    "status": {
        "ko": "상태",
        "en": "Status"
    },
    "action": {
        "ko": "액션",
        "en": "Action"
    },
    "actions": {
        "ko": "액션",
        "en": "Actions"
    },
    "save": {
        "ko": "저장",
        "en": "Save"
    },
    "cancel": {
        "ko": "취소",
        "en": "Cancel"
    },
    "edit": {
        "ko": "편집",
        "en": "Edit"
    },
    "delete": {
        "ko": "삭제",
        "en": "Delete"
    },
    "view": {
        "ko": "보기",
        "en": "View"
    },
    "create": {
        "ko": "생성",
        "en": "Create"
    },
    "update": {
        "ko": "업데이트",
        "en": "Update"
    },
    "search": {
        "ko": "검색",
        "en": "Search"
    },
    "filter": {
        "ko": "필터",
        "en": "Filter"
    },
    "all": {
        "ko": "전체",
        "en": "All"
    },
    "active": {
        "ko": "활성",
        "en": "Active"
    },
    "inactive": {
        "ko": "비활성",
        "en": "Inactive"
    },
    "yes": {
        "ko": "예",
        "en": "Yes"
    },
    "no": {
        "ko": "아니오",
        "en": "No"
    },
    "confirm": {
        "ko": "확인",
        "en": "Confirm"
    },
    "loading": {
        "ko": "로딩 중...",
        "en": "Loading..."
    },
    "export": {
        "ko": "내보내기",
        "en": "Export"
    },
    "import": {
        "ko": "가져오기",
        "en": "Import"
    },
    "download": {
        "ko": "다운로드",
        "en": "Download"
    },
    "upload": {
        "ko": "업로드",
        "en": "Upload"
    },
    "language": {
        "ko": "언어",
        "en": "Language"
    },
    
    # 네비게이션
    "nav_dashboard": {
        "ko": "대시보드",
        "en": "Dashboard"
    },
    "nav_users": {
        "ko": "사용자 관리",
        "en": "User Management"
    },
    "nav_sessions": {
        "ko": "세션 관리",
        "en": "Session Management"
    },
    "nav_permissions": {
        "ko": "권한 관리",
        "en": "Permission Management"
    },
    "nav_roles": {
        "ko": "역할 관리",
        "en": "Role Management"
    },
    "nav_analytics": {
        "ko": "분석",
        "en": "Analytics"
    },
    
    # 대시보드
    "total_users": {
        "ko": "총 사용자",
        "en": "Total Users"
    },
    "active_users": {
        "ko": "활성 사용자",
        "en": "Active Users"
    },
    "admin_users": {
        "ko": "관리자",
        "en": "Admins"
    },
    "new_users_today": {
        "ko": "오늘 신규 가입",
        "en": "New Users Today"
    },
    "quick_actions": {
        "ko": "빠른 액션",
        "en": "Quick Actions"
    },
    "system_statistics": {
        "ko": "시스템 통계",
        "en": "System Statistics"
    },
    
    # 사용자 관리
    "user_list": {
        "ko": "사용자 목록",
        "en": "User List"
    },
    "user_details": {
        "ko": "사용자 정보",
        "en": "User Details"
    },
    "edit_user": {
        "ko": "사용자 편집",
        "en": "Edit User"
    },
    "change_role": {
        "ko": "역할 변경",
        "en": "Change Role"
    },
    "view_permissions": {
        "ko": "권한 보기",
        "en": "View Permissions"
    },
    "created_at": {
        "ko": "생성일",
        "en": "Created At"
    },
    "last_login": {
        "ko": "최종 로그인",
        "en": "Last Login"
    },
    
    # 세션 관리
    "session_list": {
        "ko": "세션 목록",
        "en": "Session List"
    },
    "active_sessions": {
        "ko": "활성 세션",
        "en": "Active Sessions"
    },
    "revoke_token": {
        "ko": "토큰 무효화",
        "en": "Revoke Token"
    },
    "revoke_all": {
        "ko": "모두 무효화",
        "en": "Revoke All"
    },
    "device_id": {
        "ko": "디바이스 ID",
        "en": "Device ID"
    },
    "issued_at": {
        "ko": "발급일",
        "en": "Issued At"
    },
    "expires_at": {
        "ko": "만료일",
        "en": "Expires At"
    },
    
    # 권한 관리
    "permission_list": {
        "ko": "권한 목록",
        "en": "Permission List"
    },
    "resource_type": {
        "ko": "리소스 타입",
        "en": "Resource Type"
    },
    "resource_name": {
        "ko": "리소스 이름",
        "en": "Resource Name"
    },
    "permission_action": {
        "ko": "액션",
        "en": "Action"
    },
    "granted_to": {
        "ko": "부여 대상",
        "en": "Granted To"
    },
    "web_search": {
        "ko": "웹 검색",
        "en": "Web Search"
    },
    "vector_db": {
        "ko": "벡터 DB",
        "en": "Vector DB"
    },
    "database": {
        "ko": "데이터베이스",
        "en": "Database"
    },
    "read": {
        "ko": "읽기",
        "en": "READ"
    },
    "write": {
        "ko": "쓰기",
        "en": "WRITE"
    },
    "delete_perm": {
        "ko": "삭제",
        "en": "DELETE"
    },
    
    # 역할 관리
    "role_list": {
        "ko": "역할 목록",
        "en": "Role List"
    },
    "permission_matrix": {
        "ko": "권한 매트릭스",
        "en": "Permission Matrix"
    },
    "role_permissions": {
        "ko": "역할 권한",
        "en": "Role Permissions"
    },
    "permission_count": {
        "ko": "권한 수",
        "en": "Permission Count"
    },
    
    # 분석 페이지
    "analytics_dashboard": {
        "ko": "분석 대시보드",
        "en": "Analytics Dashboard"
    },
    "tool_usage": {
        "ko": "도구 사용량",
        "en": "Tool Usage"
    },
    "user_activity": {
        "ko": "사용자 활동",
        "en": "User Activity"
    },
    "response_time": {
        "ko": "응답 시간",
        "en": "Response Time"
    },
    "success_rate": {
        "ko": "성공률",
        "en": "Success Rate"
    },
    "request_count": {
        "ko": "요청 수",
        "en": "Request Count"
    },
    "avg_response_time": {
        "ko": "평균 응답시간",
        "en": "Avg Response Time"
    },
    "error_count": {
        "ko": "오류 수",
        "en": "Error Count"
    },
    "last_used": {
        "ko": "마지막 사용",
        "en": "Last Used"
    },
    "trend": {
        "ko": "트렌드",
        "en": "Trend"
    },
    
    # 데이터 내보내기
    "export_users": {
        "ko": "사용자 내보내기",
        "en": "Export Users"
    },
    "export_permissions": {
        "ko": "권한 내보내기",
        "en": "Export Permissions"
    },
    "export_metrics": {
        "ko": "메트릭 내보내기",
        "en": "Export Metrics"
    },
    "csv_export": {
        "ko": "CSV 내보내기",
        "en": "CSV Export"
    },
    "json_export": {
        "ko": "JSON 내보내기",
        "en": "JSON Export"
    },
    
    # 메시지
    "no_data": {
        "ko": "데이터가 없습니다.",
        "en": "No data available."
    },
    "loading_data": {
        "ko": "데이터를 불러오는 중...",
        "en": "Loading data..."
    },
    "operation_successful": {
        "ko": "작업이 성공적으로 완료되었습니다.",
        "en": "Operation completed successfully."
    },
    "operation_failed": {
        "ko": "작업이 실패했습니다.",
        "en": "Operation failed."
    },
    "confirm_delete": {
        "ko": "정말 삭제하시겠습니까?",
        "en": "Are you sure you want to delete?"
    },
    "confirm_revoke": {
        "ko": "정말 토큰을 무효화하시겠습니까?",
        "en": "Are you sure you want to revoke the token?"
    },
    "session_revoked": {
        "ko": "세션이 무효화되었습니다.",
        "en": "Session has been revoked."
    },
    "role_changed": {
        "ko": "역할이 변경되었습니다.",
        "en": "Role has been changed."
    },
    "permission_created": {
        "ko": "권한이 생성되었습니다.",
        "en": "Permission has been created."
    },
    "permission_deleted": {
        "ko": "권한이 삭제되었습니다.",
        "en": "Permission has been deleted."
    },
    "language_changed": {
        "ko": "언어가 변경되었습니다.",
        "en": "Language has been changed."
    },
    
    # 폼 레이블
    "select_role": {
        "ko": "역할을 선택하세요",
        "en": "Select a role"
    },
    "select_language": {
        "ko": "언어를 선택하세요",
        "en": "Select a language"
    },
    "select_resource": {
        "ko": "리소스를 선택하세요",
        "en": "Select a resource"
    },
    "select_action": {
        "ko": "액션을 선택하세요",
        "en": "Select an action"
    },
    "enter_search": {
        "ko": "검색어를 입력하세요",
        "en": "Enter search term"
    },
    
    # 테이블 헤더
    "table_name": {
        "ko": "이름",
        "en": "Name"
    },
    "table_email": {
        "ko": "이메일",
        "en": "Email"
    },
    "table_role": {
        "ko": "역할",
        "en": "Role"
    },
    "table_status": {
        "ko": "상태",
        "en": "Status"
    },
    "table_created": {
        "ko": "생성일",
        "en": "Created"
    },
    "table_actions": {
        "ko": "액션",
        "en": "Actions"
    }
}

def get_user_language(request: Request) -> str:
    """요청에서 사용자 언어 설정을 가져옵니다.
    
    Args:
        request: FastAPI 요청 객체
        
    Returns:
        언어 코드 (기본값: 'ko')
    """
    # 세션에서 언어 설정 확인
    if hasattr(request, 'session') and request.session:
        lang = request.session.get('language', 'ko')
        if lang in SUPPORTED_LANGUAGES:
            return lang
    
    # Accept-Language 헤더에서 언어 추론
    accept_language = request.headers.get('accept-language', '')
    if 'ko' in accept_language:
        return 'ko'
    elif 'en' in accept_language:
        return 'en'
    
    # 기본값: 한국어
    return 'ko'

def set_user_language(request: Request, language: str) -> bool:
    """사용자 언어 설정을 저장합니다.
    
    Args:
        request: FastAPI 요청 객체
        language: 설정할 언어 코드
        
    Returns:
        설정 성공 여부
    """
    if language not in SUPPORTED_LANGUAGES:
        return False
    
    if hasattr(request, 'session'):
        request.session['language'] = language
        return True
    
    return False

def T(key: str, request: Optional[Request] = None, default_lang: str = 'ko') -> str:
    """번역 함수
    
    Args:
        key: 번역할 키
        request: FastAPI 요청 객체 (언어 설정 추론용)
        default_lang: 기본 언어 (request가 없을 때 사용)
        
    Returns:
        번역된 텍스트 (키가 없으면 원본 키 반환)
    """
    # 언어 결정
    if request:
        lang = get_user_language(request)
    else:
        lang = default_lang
    
    # 번역 조회
    if key in TRANSLATIONS:
        return TRANSLATIONS[key].get(lang, TRANSLATIONS[key].get('ko', key))
    
    # 키가 없으면 원본 키 반환
    return key

def get_all_translations(language: str = 'ko') -> Dict[str, str]:
    """특정 언어의 모든 번역을 반환합니다.
    
    Args:
        language: 언어 코드
        
    Returns:
        번역 딕셔너리
    """
    if language not in SUPPORTED_LANGUAGES:
        language = 'ko'
    
    result = {}
    for key, translations in TRANSLATIONS.items():
        result[key] = translations.get(language, translations.get('ko', key))
    
    return result

def get_language_name(language_code: str) -> str:
    """언어 코드에 해당하는 언어명을 반환합니다.
    
    Args:
        language_code: 언어 코드
        
    Returns:
        언어명 (예: 'ko' -> '한국어')
    """
    return SUPPORTED_LANGUAGES.get(language_code, language_code)