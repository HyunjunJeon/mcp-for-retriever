"""FastHTML 재사용 가능한 Admin UI 컴포넌트 라이브러리"""

from typing import Any, Optional, Union, List, Dict
from fasthtml.common import *


def AdminTable(
    headers: List[str],
    rows: List[List[Union[str, FT]]], 
    table_id: Optional[str] = None,
    actions_header: str = "액션",
    empty_message: str = "데이터가 없습니다.",
    css_classes: Optional[str] = None
) -> Div:
    """재사용 가능한 관리자 테이블 컴포넌트
    
    Args:
        headers: 테이블 헤더 목록
        rows: 테이블 행 데이터 (각 행은 셀 데이터 리스트)
        table_id: 테이블 ID (HTMX 타겟용)
        actions_header: 액션 컬럼 헤더 이름
        empty_message: 데이터가 없을 때 표시할 메시지
        css_classes: 추가 CSS 클래스
    
    Returns:
        Table을 포함한 Div 컴포넌트
    """
    # 테이블 헤더 생성
    header_cells = [
        Th(header, cls="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider")
        for header in headers
    ]
    
    # 액션 헤더 추가 (행에 액션이 있는 경우)
    if rows and len(rows[0]) > len(headers):
        header_cells.append(
            Th(actions_header, cls="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider")
        )
    
    # 테이블 행 생성
    table_rows = []
    if rows:
        for row_data in rows:
            cells = []
            for i, cell_data in enumerate(row_data):
                cell_class = "px-6 py-4 whitespace-nowrap text-sm text-gray-900"
                if i == len(row_data) - 1 and len(row_data) > len(headers):
                    # 마지막 셀이 액션 셀인 경우
                    cell_class = "px-6 py-4 whitespace-nowrap text-sm font-medium"
                
                cells.append(Td(cell_data, cls=cell_class))
            
            table_rows.append(Tr(*cells, cls="hover:bg-gray-50"))
    else:
        # 빈 데이터 행
        table_rows.append(
            Tr(
                Td(
                    empty_message,
                    colspan=str(len(headers) + (1 if rows and len(rows[0]) > len(headers) else 0)),
                    cls="px-6 py-4 text-center text-gray-500"
                )
            )
        )
    
    # 테이블 컴포넌트 구성
    table_attrs = {"cls": f"min-w-full divide-y divide-gray-200 {css_classes or ''}".strip()}
    if table_id:
        table_attrs["id"] = table_id
    
    return Table(
        Thead(
            Tr(*header_cells, cls="bg-gray-50")
        ),
        Tbody(
            *table_rows,
            cls="bg-white divide-y divide-gray-200"
        ),
        **table_attrs
    )


def AdminModal(
    title: str,
    content: Union[str, FT],
    modal_id: str,
    size: str = "md",
    closable: bool = True,
    close_target: str = "#modal-container",
    close_endpoint: str = "/admin/empty"
) -> Div:
    """HTMX 기반 모달 컴포넌트
    
    Args:
        title: 모달 제목
        content: 모달 본문 내용
        modal_id: 모달 고유 ID
        size: 모달 크기 (sm, md, lg, xl)
        closable: 닫기 버튼 표시 여부
        close_target: 닫기 시 HTMX 타겟
        close_endpoint: 닫기 시 호출할 엔드포인트
    
    Returns:
        모달 컴포넌트
    """
    size_classes = {
        "sm": "max-w-sm",
        "md": "max-w-md", 
        "lg": "max-w-lg",
        "xl": "max-w-xl",
        "2xl": "max-w-2xl"
    }
    
    modal_class = size_classes.get(size, "max-w-md")
    
    close_attrs = {
        "hx-get": close_endpoint,
        "hx-target": close_target,
    }
    
    return Div(
        # 모달 오버레이
        Div(
            # 모달 컨테이너
            Div(
                # 모달 헤더
                Div(
                    H3(title, cls="text-lg font-medium text-gray-900"),
                    Button(
                        "×",
                        **close_attrs,
                        cls="text-gray-400 hover:text-gray-600 text-2xl font-bold"
                    ) if closable else "",
                    cls="flex justify-between items-center mb-4"
                ),
                
                # 모달 본문
                content,
                
                cls=f"bg-white rounded-lg p-6 {modal_class} mx-auto mt-20 relative"
            ),
            cls="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full",
            id=f"{modal_id}-overlay",
            **close_attrs if closable else {}
        ),
        id=modal_id
    )


def AdminForm(
    fields: List[Dict[str, Any]],
    action: str,
    method: str = "POST",
    submit_text: str = "저장",
    cancel_text: Optional[str] = None,
    htmx_attrs: Optional[Dict[str, str]] = None,
    form_id: Optional[str] = None,
    grid_cols: int = 1
) -> Form:
    """관리자 폼 컴포넌트
    
    Args:
        fields: 폼 필드 정보 리스트
        action: 폼 액션 URL
        method: HTTP 메서드
        submit_text: 제출 버튼 텍스트
        cancel_text: 취소 버튼 텍스트 (None이면 표시 안함)
        htmx_attrs: HTMX 속성들
        form_id: 폼 ID
        grid_cols: 그리드 컬럼 수
    
    Returns:
        Form 컴포넌트
    """
    form_fields = []
    
    for field in fields:
        field_type = field.get("type", "text")
        field_name = field["name"]
        field_label = field.get("label", field_name)
        field_placeholder = field.get("placeholder", "")
        field_required = field.get("required", False)
        field_value = field.get("value", "")
        field_options = field.get("options", [])
        field_class = field.get("class", "")
        
        # 라벨 생성
        label_attrs = {"cls": "block text-sm font-medium text-gray-700 mb-2"}
        if field_required:
            label_attrs["cls"] += " required"
        
        # 필드별 입력 요소 생성
        if field_type == "select":
            input_element = Select(
                *[Option(opt.get("label", opt.get("value")), value=opt["value"]) 
                  for opt in field_options],
                name=field_name,
                cls=f"block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 {field_class}",
                required=field_required
            )
        elif field_type == "textarea":
            rows = field.get("rows", 3)
            input_element = Textarea(
                field_value,
                name=field_name,
                placeholder=field_placeholder,
                rows=str(rows),
                cls=f"block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 {field_class}",
                required=field_required
            )
        elif field_type == "checkbox":
            input_element = Div(
                *[
                    Label(
                        Input(
                            type="checkbox",
                            name=field_name,
                            value=opt["value"],
                            checked=opt.get("checked", False),
                            cls="mr-2"
                        ),
                        opt.get("label", opt["value"]),
                        cls="flex items-center mb-2 text-sm"
                    )
                    for opt in field_options
                ],
                cls="space-y-2"
            )
        else:
            input_element = Input(
                type=field_type,
                name=field_name,
                placeholder=field_placeholder,
                value=field_value,
                cls=f"block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 {field_class}",
                required=field_required
            )
        
        # 필드 컨테이너
        field_container = Div(
            Label(field_label, **label_attrs),
            input_element,
            cls="mb-4"
        )
        
        form_fields.append(field_container)
    
    # 그리드 레이아웃 적용
    if grid_cols > 1:
        grid_class = f"grid grid-cols-1 md:grid-cols-{grid_cols} gap-4"
        fields_container = Div(*form_fields, cls=grid_class)
    else:
        fields_container = Div(*form_fields, cls="space-y-4")
    
    # 버튼 영역
    buttons = [
        Button(
            submit_text,
            type="submit",
            cls="bg-blue-500 hover:bg-blue-600 text-white font-medium py-2 px-4 rounded-lg"
        )
    ]
    
    if cancel_text:
        buttons.insert(0, 
            Button(
                cancel_text,
                type="button",
                cls="mr-2 bg-gray-300 hover:bg-gray-400 text-gray-700 font-medium py-2 px-4 rounded-lg"
            )
        )
    
    button_container = Div(*buttons, cls="flex justify-end space-x-2 mt-6")
    
    # 폼 속성 구성
    form_attrs = {
        "method": method,
        "action": action,
        "cls": "space-y-4"
    }
    
    if form_id:
        form_attrs["id"] = form_id
    
    if htmx_attrs:
        form_attrs.update(htmx_attrs)
    
    return Form(
        fields_container,
        button_container,
        **form_attrs
    )


def StatsCard(
    title: str,
    value: Union[str, int],
    color: str = "blue",
    icon: Optional[str] = None,
    subtitle: Optional[str] = None,
    trend: Optional[Dict[str, Any]] = None
) -> Div:
    """통계 카드 컴포넌트
    
    Args:
        title: 카드 제목
        value: 표시할 값
        color: 카드 색상 테마 (blue, green, red, yellow, purple)
        icon: 아이콘 (이모지 또는 텍스트)
        subtitle: 부제목
        trend: 증감 정보 {"value": "+5%", "positive": True}
    
    Returns:
        통계 카드 컴포넌트
    """
    color_classes = {
        "blue": {
            "bg": "bg-blue-50",
            "border": "border-blue-200",
            "icon": "text-blue-600",
            "title": "text-blue-900",
            "value": "text-blue-800"
        },
        "green": {
            "bg": "bg-green-50",
            "border": "border-green-200", 
            "icon": "text-green-600",
            "title": "text-green-900",
            "value": "text-green-800"
        },
        "red": {
            "bg": "bg-red-50",
            "border": "border-red-200",
            "icon": "text-red-600", 
            "title": "text-red-900",
            "value": "text-red-800"
        },
        "yellow": {
            "bg": "bg-yellow-50",
            "border": "border-yellow-200",
            "icon": "text-yellow-600",
            "title": "text-yellow-900", 
            "value": "text-yellow-800"
        },
        "purple": {
            "bg": "bg-purple-50",
            "border": "border-purple-200",
            "icon": "text-purple-600",
            "title": "text-purple-900",
            "value": "text-purple-800"
        }
    }
    
    colors = color_classes.get(color, color_classes["blue"])
    
    card_content = []
    
    # 헤더 (아이콘 + 제목)
    header_items = []
    if icon:
        header_items.append(
            Span(icon, cls=f"text-2xl {colors['icon']}")
        )
    header_items.append(
        H3(title, cls=f"text-sm font-medium {colors['title']}")
    )
    
    card_content.append(
        Div(*header_items, cls="flex items-center justify-between")
    )
    
    # 값과 트렌드
    value_section = [
        P(str(value), cls=f"text-2xl font-bold {colors['value']}")
    ]
    
    if trend:
        trend_color = "text-green-600" if trend.get("positive", True) else "text-red-600"
        trend_icon = "↗" if trend.get("positive", True) else "↘"
        value_section.append(
            Span(
                f"{trend_icon} {trend['value']}", 
                cls=f"text-sm {trend_color} font-medium"
            )
        )
    
    card_content.append(
        Div(*value_section, cls="mt-2")
    )
    
    # 부제목
    if subtitle:
        card_content.append(
            P(subtitle, cls="text-xs text-gray-500 mt-1")
        )
    
    return Div(
        *card_content,
        cls=f"p-6 {colors['bg']} {colors['border']} border rounded-lg shadow-sm"
    )


def FilterBar(
    filters: List[Dict[str, Any]],
    search_placeholder: str = "검색...",
    search_name: str = "search",
    htmx_target: str = "#filtered-content",
    htmx_endpoint: str = "/admin/filter",
    container_id: str = "filter-bar"
) -> Div:
    """필터 및 검색 바 컴포넌트
    
    Args:
        filters: 필터 정보 리스트
        search_placeholder: 검색 입력 플레이스홀더
        search_name: 검색 입력 name 속성
        htmx_target: HTMX 타겟 셀렉터
        htmx_endpoint: HTMX 요청 엔드포인트
        container_id: 컨테이너 ID
    
    Returns:
        필터 바 컴포넌트
    """
    filter_elements = []
    
    # 검색 입력
    search_input = Input(
        type="text",
        name=search_name,
        placeholder=search_placeholder,
        **{
            "hx-get": htmx_endpoint,
            "hx-target": htmx_target,
            "hx-trigger": "keyup changed delay:500ms",
            "hx-include": f"#{container_id}",
        },
        cls="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
    )
    
    filter_elements.append(
        Div(
            Label("검색", cls="block text-sm font-medium text-gray-700 mb-2"),
            search_input,
            cls="mb-4"
        )
    )
    
    # 필터 드롭다운들
    for filter_config in filters:
        filter_name = filter_config["name"]
        filter_label = filter_config.get("label", filter_name)
        filter_options = filter_config.get("options", [])
        
        select_element = Select(
            Option("전체", value=""),
            *[
                Option(opt.get("label", opt["value"]), value=opt["value"])
                for opt in filter_options
            ],
            name=filter_name,
            **{
                "hx-get": htmx_endpoint,
                "hx-target": htmx_target,
                "hx-trigger": "change",
                "hx-include": f"#{container_id}",
            },
            cls="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
        )
        
        filter_elements.append(
            Div(
                Label(filter_label, cls="block text-sm font-medium text-gray-700 mb-2"),
                select_element,
                cls="mb-4"
            )
        )
    
    return Div(
        *filter_elements,
        id=container_id,
        cls="p-4 bg-gray-50 rounded-lg space-y-4"
    )


def AdminCard(
    title: str,
    content: Union[str, FT],
    actions: Optional[List[FT]] = None,
    color: str = "white"
) -> Div:
    """관리자 카드 컴포넌트
    
    Args:
        title: 카드 제목
        content: 카드 내용
        actions: 액션 버튼들
        color: 카드 배경색
    
    Returns:
        카드 컴포넌트
    """
    color_classes = {
        "white": "bg-white",
        "gray": "bg-gray-50",
        "blue": "bg-blue-50",
        "green": "bg-green-50"
    }
    
    bg_class = color_classes.get(color, "bg-white")
    
    card_elements = [
        H2(title, cls="text-xl font-semibold text-gray-900 mb-4"),
        content
    ]
    
    if actions:
        card_elements.append(
            Div(*actions, cls="flex space-x-2 mt-4")
        )
    
    return Div(
        *card_elements,
        cls=f"{bg_class} rounded-lg shadow-md p-6"
    )


def AdminBreadcrumb(
    items: List[Dict[str, str]]
) -> Nav:
    """관리자 breadcrumb 컴포넌트
    
    Args:
        items: breadcrumb 항목들 [{"label": "홈", "url": "/admin"}, ...]
    
    Returns:
        breadcrumb 네비게이션
    """
    breadcrumb_items = []
    
    for i, item in enumerate(items):
        if i > 0:
            breadcrumb_items.append(
                Span("/", cls="mx-2 text-gray-500")
            )
        
        if item.get("url") and i < len(items) - 1:
            breadcrumb_items.append(
                A(item["label"], href=item["url"], cls="text-blue-600 hover:text-blue-800")
            )
        else:
            # 마지막 항목이거나 URL이 없는 경우
            breadcrumb_items.append(
                Span(item["label"], cls="text-gray-500")
            )
    
    return Nav(
        *breadcrumb_items,
        cls="text-sm text-gray-600 mb-4"
    )


def ConfirmDialog(
    message: str,
    confirm_text: str = "확인",
    cancel_text: str = "취소",
    dialog_id: str = "confirm-dialog"
) -> str:
    """확인 대화상자 (JavaScript)
    
    Args:
        message: 확인 메시지
        confirm_text: 확인 버튼 텍스트
        cancel_text: 취소 버튼 텍스트
        dialog_id: 대화상자 ID
    
    Returns:
        JavaScript 코드 문자열
    """
    return f"""
    function showConfirmDialog_{dialog_id}(callback) {{
        if (confirm("{message}")) {{
            callback();
        }}
    }}
    """


def LoadingSpinner(
    size: str = "md",
    color: str = "blue"
) -> Div:
    """로딩 스피너 컴포넌트
    
    Args:
        size: 스피너 크기 (sm, md, lg)
        color: 스피너 색상
    
    Returns:
        로딩 스피너
    """
    size_classes = {
        "sm": "w-4 h-4",
        "md": "w-8 h-8", 
        "lg": "w-12 h-12"
    }
    
    color_classes = {
        "blue": "text-blue-600",
        "green": "text-green-600",
        "red": "text-red-600",
        "gray": "text-gray-600"
    }
    
    size_class = size_classes.get(size, "w-8 h-8")
    color_class = color_classes.get(color, "text-blue-600")
    
    return Div(
        Div(
            cls=f"animate-spin rounded-full border-2 border-gray-300 border-t-current {size_class} {color_class}"
        ),
        cls="flex justify-center items-center"
    )


def AnalyticsChart(
    chart_type: str,
    data: Dict[str, Any],
    canvas_id: str,
    width: int = 400,
    height: int = 300,
    title: Optional[str] = None
) -> Div:
    """Chart.js 기반 분석 차트 컴포넌트
    
    Args:
        chart_type: 차트 타입 (line, bar, pie, doughnut)
        data: Chart.js 데이터 형식
        canvas_id: Canvas 요소 고유 ID
        width: 차트 너비
        height: 차트 높이
        title: 차트 제목
    
    Returns:
        Chart.js 차트를 포함한 컴포넌트
    """
    import json
    
    # Chart.js 설정
    chart_config = {
        "type": chart_type,
        "data": data,
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "plugins": {
                "title": {
                    "display": bool(title),
                    "text": title or ""
                },
                "legend": {
                    "position": "bottom"
                }
            }
        }
    }
    
    # 차트 초기화 스크립트 (전역 chartInstances에 저장)
    init_script = f"""
    <script>
        document.addEventListener('DOMContentLoaded', function() {{
            const ctx = document.getElementById('{canvas_id}');
            if (ctx) {{
                // 전역 chartInstances 객체가 없으면 생성
                if (typeof window.chartInstances === 'undefined') {{
                    window.chartInstances = {{}};
                }}
                
                // 차트 생성 및 전역 변수에 저장
                window.chartInstances['{canvas_id}'] = new Chart(ctx, {json.dumps(chart_config)});
            }}
        }});
    </script>
    """
    
    chart_content = [
        Canvas(
            id=canvas_id,
            width=str(width),
            height=str(height),
            cls="max-w-full"
        )
    ]
    
    if title:
        chart_content.insert(0, 
            H3(title, cls="text-lg font-semibold text-gray-900 mb-4 text-center")
        )
    
    return Div(
        *chart_content,
        Script(init_script),
        cls="bg-white p-6 rounded-lg shadow-sm border"
    )


def ExportButton(
    export_type: str,
    endpoint: str,
    filename: str,
    icon: str = "📊",
    color: str = "blue",
    size: str = "md",
    disabled: bool = False
) -> A:
    """데이터 내보내기 전용 버튼 컴포넌트
    
    Args:
        export_type: 내보내기 타입 (CSV, JSON, PDF 등)
        endpoint: 내보내기 엔드포인트 URL
        filename: 다운로드 파일명
        icon: 버튼 아이콘
        color: 버튼 색상 테마
        size: 버튼 크기
        disabled: 비활성화 여부
    
    Returns:
        다운로드 링크 스타일의 버튼
    """
    color_classes = {
        "blue": "bg-blue-500 hover:bg-blue-600 disabled:bg-blue-300",
        "green": "bg-green-500 hover:bg-green-600 disabled:bg-green-300",
        "red": "bg-red-500 hover:bg-red-600 disabled:bg-red-300",
        "yellow": "bg-yellow-500 hover:bg-yellow-600 disabled:bg-yellow-300",
        "purple": "bg-purple-500 hover:bg-purple-600 disabled:bg-purple-300",
        "indigo": "bg-indigo-500 hover:bg-indigo-600 disabled:bg-indigo-300",
        "gray": "bg-gray-500 hover:bg-gray-600 disabled:bg-gray-300"
    }
    
    size_classes = {
        "sm": "py-1 px-3 text-sm",
        "md": "py-2 px-4 text-base",
        "lg": "py-3 px-6 text-lg"
    }
    
    color_class = color_classes.get(color, color_classes["blue"])
    size_class = size_classes.get(size, size_classes["md"])
    
    disabled_class = "cursor-not-allowed opacity-50" if disabled else "cursor-pointer"
    
    button_class = f"{color_class} {size_class} text-white font-medium rounded-lg inline-flex items-center space-x-2 transition-colors {disabled_class}"
    
    if disabled:
        return Div(
            Span(icon, cls="text-lg"),
            Span(f"{icon} {export_type} 내보내기"),
            cls=button_class
        )
    
    return A(
        Span(icon, cls="text-lg"),
        Span(f"{export_type} 내보내기"),
        href=endpoint,
        download=filename,
        cls=button_class
    )


def MetricsTable(
    metrics_data: List[Dict[str, Any]],
    metric_type: str = "tools",
    show_trends: bool = True,
    sortable: bool = True,
    table_id: Optional[str] = None
) -> Div:
    """메트릭 전용 테이블 컴포넌트 (AdminTable 확장)
    
    Args:
        metrics_data: 메트릭 데이터 리스트
        metric_type: 메트릭 타입 (tools, users, requests)
        show_trends: 트렌드 표시 여부
        sortable: 정렬 가능 여부
        table_id: 테이블 고유 ID
    
    Returns:
        메트릭 전용 테이블 컴포넌트
    """
    if not metrics_data:
        return AdminTable(
            headers=["데이터 없음"],
            rows=[],
            table_id=table_id,
            empty_message="메트릭 데이터가 없습니다."
        )
    
    # 메트릭 타입별 헤더 설정
    headers_config = {
        "tools": ["도구명", "사용 횟수", "평균 응답시간", "성공률", "마지막 사용"],
        "users": ["사용자", "요청 수", "평균 세션 시간", "마지막 활동", "상태"],
        "requests": ["시간", "요청 수", "성공률", "평균 응답시간", "오류 수"]
    }
    
    headers = headers_config.get(metric_type, ["항목", "값", "상태"])
    
    # 데이터 행 생성
    rows = []
    for item in metrics_data:
        if metric_type == "tools":
            row = [
                item.get("name", ""),
                str(item.get("count", 0)),
                f"{item.get('avg_duration', 0):.1f}ms",
                f"{item.get('success_rate', 0):.1f}%",
                item.get("last_used", "N/A")
            ]
        elif metric_type == "users":
            row = [
                item.get("username", ""),
                str(item.get("request_count", 0)),
                f"{item.get('avg_session_time', 0):.1f}분",
                item.get("last_activity", "N/A"),
                "🟢 활성" if item.get("active") else "🔴 비활성"
            ]
        elif metric_type == "requests":
            row = [
                item.get("timestamp", ""),
                str(item.get("count", 0)),
                f"{item.get('success_rate', 0):.1f}%",
                f"{item.get('avg_duration', 0):.1f}ms",
                str(item.get("errors", 0))
            ]
        else:
            # 일반적인 키-값 표시
            row = [str(v) for v in item.values()]
        
        # 트렌드 정보 추가
        if show_trends and "trend" in item:
            trend = item["trend"]
            trend_icon = "📈" if trend.get("positive", True) else "📉"
            trend_text = f"{trend_icon} {trend.get('value', '')}"
            row.append(trend_text)
        
        rows.append(row)
    
    # 트렌드 헤더 추가
    if show_trends:
        headers.append("트렌드")
    
    # 정렬 가능한 테이블 생성
    table_attrs = {}
    if sortable:
        table_attrs["data-sortable"] = "true"
    
    return Div(
        AdminTable(
            headers=headers,
            rows=rows,
            table_id=table_id or f"metrics-{metric_type}-table",
            empty_message=f"{metric_type} 메트릭 데이터가 없습니다.",
            css_classes="sortable" if sortable else ""
        ),
        **table_attrs,
        cls="metrics-table-container"
    )


def NotificationBanner(
    message: str,
    type: str = "info",
    dismissible: bool = True,
    icon: Optional[str] = None,
    action_text: Optional[str] = None,
    action_url: Optional[str] = None,
    banner_id: Optional[str] = None
) -> Div:
    """실시간 알림 표시용 배너 컴포넌트
    
    Args:
        message: 알림 메시지
        type: 알림 타입 (success, warning, error, info)
        dismissible: 닫기 버튼 표시 여부
        icon: 알림 아이콘
        action_text: 액션 버튼 텍스트
        action_url: 액션 버튼 URL
        banner_id: 배너 고유 ID
    
    Returns:
        알림 배너 컴포넌트
    """
    type_config = {
        "success": {
            "bg": "bg-green-50",
            "border": "border-green-200",
            "text": "text-green-800",
            "icon_color": "text-green-600",
            "button": "bg-green-100 hover:bg-green-200 text-green-800",
            "default_icon": "✅"
        },
        "warning": {
            "bg": "bg-yellow-50",
            "border": "border-yellow-200", 
            "text": "text-yellow-800",
            "icon_color": "text-yellow-600",
            "button": "bg-yellow-100 hover:bg-yellow-200 text-yellow-800",
            "default_icon": "⚠️"
        },
        "error": {
            "bg": "bg-red-50",
            "border": "border-red-200",
            "text": "text-red-800", 
            "icon_color": "text-red-600",
            "button": "bg-red-100 hover:bg-red-200 text-red-800",
            "default_icon": "❌"
        },
        "info": {
            "bg": "bg-blue-50",
            "border": "border-blue-200",
            "text": "text-blue-800",
            "icon_color": "text-blue-600", 
            "button": "bg-blue-100 hover:bg-blue-200 text-blue-800",
            "default_icon": "ℹ️"
        }
    }
    
    config = type_config.get(type, type_config["info"])
    display_icon = icon or config["default_icon"]
    
    banner_content = []
    
    # 아이콘과 메시지
    message_section = [
        Span(display_icon, cls=f"text-lg {config['icon_color']}"),
        Span(message, cls=f"ml-2 {config['text']} font-medium")
    ]
    
    # 액션 버튼
    if action_text and action_url:
        message_section.append(
            A(
                action_text,
                href=action_url,
                cls=f"ml-4 {config['button']} px-3 py-1 rounded text-sm font-medium"
            )
        )
    
    banner_content.append(
        Div(*message_section, cls="flex items-center")
    )
    
    # 닫기 버튼
    if dismissible:
        close_attrs = {
            "onclick": f"this.parentElement.style.display='none'",
            "cls": f"ml-auto {config['text']} hover:bg-opacity-20 p-1 rounded"
        }
        
        banner_content.append(
            Button("×", **close_attrs)
        )
    
    banner_attrs = {
        "cls": f"flex items-center justify-between p-4 mb-4 {config['bg']} {config['border']} border rounded-lg"
    }
    
    if banner_id:
        banner_attrs["id"] = banner_id
    
    return Div(
        *banner_content,
        **banner_attrs
    )


def LanguageSelector(
    current_language: str = "ko",
    endpoint: str = "/admin/change-language",
    target: str = "body",
    size: str = "sm",
    show_flag: bool = True,
    selector_id: Optional[str] = None
) -> Div:
    """언어 선택 드롭다운 컴포넌트
    
    Args:
        current_language: 현재 선택된 언어 코드
        endpoint: 언어 변경 엔드포인트
        target: HTMX 타겟 (전체 페이지 새로고침용)
        size: 드롭다운 크기 (sm, md, lg)
        show_flag: 국기 이모지 표시 여부
        selector_id: 컴포넌트 고유 ID
    
    Returns:
        언어 선택 드롭다운 컴포넌트
    """
    from .translations import SUPPORTED_LANGUAGES
    
    # 언어별 국기 이모지
    language_flags = {
        "ko": "🇰🇷",
        "en": "🇺🇸"
    }
    
    # 크기별 스타일
    size_classes = {
        "sm": "text-sm py-1 px-2",
        "md": "text-base py-2 px-3", 
        "lg": "text-lg py-2 px-4"
    }
    
    size_class = size_classes.get(size, size_classes["sm"])
    
    # 현재 언어 정보
    current_flag = language_flags.get(current_language, "🌐") if show_flag else ""
    current_name = SUPPORTED_LANGUAGES.get(current_language, current_language)
    
    # 드롭다운 옵션 생성
    options = []
    for lang_code, lang_name in SUPPORTED_LANGUAGES.items():
        flag = language_flags.get(lang_code, "🌐") if show_flag else ""
        display_text = f"{flag} {lang_name}" if show_flag else lang_name
        
        options.append(
            Option(
                display_text,
                value=lang_code,
                selected=(lang_code == current_language)
            )
        )
    
    # HTMX 속성
    htmx_attrs = {
        "hx-post": endpoint,
        "hx-target": target,
        "hx-trigger": "change",
        "hx-include": "this",
        "hx-swap": "outerHTML"
    }
    
    # 드롭다운 컴포넌트
    select_element = Select(
        *options,
        name="language",
        **htmx_attrs,
        cls=f"border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 {size_class}"
    )
    
    # 컨테이너 속성
    container_attrs = {
        "cls": "flex items-center space-x-2"
    }
    
    if selector_id:
        container_attrs["id"] = selector_id
    
    # 라벨과 드롭다운 조합
    return Div(
        Label(
            "🌐",
            cls="text-gray-600 text-sm font-medium",
            **{"for": "language-selector"}
        ),
        select_element,
        **container_attrs
    )