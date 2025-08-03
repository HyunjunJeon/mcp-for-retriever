"""FastHTML 컴포넌트 라이브러리 단위 테스트."""

import pytest
from fasthtml.common import to_xml
from src.auth.components import (
    AdminTable,
    AdminModal, 
    AdminForm,
    StatsCard,
    FilterBar,
    AdminCard,
    AdminBreadcrumb,
    ConfirmDialog,
    LoadingSpinner,
    AnalyticsChart,
    ExportButton,
    MetricsTable,
    NotificationBanner,
    LanguageSelector
)


def is_fasthtml_component(component):
    """FastHTML 컴포넌트인지 확인하는 헬퍼 함수."""
    return hasattr(component, 'tag') or hasattr(component, '__html__') or callable(getattr(component, 'to_xml', None))


class TestAdminTable:
    """AdminTable 컴포넌트 테스트."""
    
    def test_admin_table_basic(self):
        """기본 테이블 생성 테스트."""
        headers = ["이름", "이메일", "역할"]
        rows = [
            ["홍길동", "hong@example.com", "admin"],
            ["김철수", "kim@example.com", "user"]
        ]
        
        table = AdminTable(headers, rows)
        
        assert table is not None
        assert hasattr(table, 'attrs')
        assert "min-w-full" in table.attrs.get("class", "")
        
    def test_admin_table_with_actions(self):
        """액션 컬럼이 있는 테이블 테스트."""
        headers = ["이름", "이메일"]
        rows = [
            ["홍길동", "hong@example.com", "편집 버튼"]
        ]
        
        table = AdminTable(headers, rows, actions_header="액션")
        
        # 테이블이 올바르게 생성되는지 확인
        assert table is not None
        assert hasattr(table, 'attrs')
        
    def test_admin_table_empty(self):
        """빈 테이블 테스트."""
        headers = ["이름", "이메일", "역할"] 
        rows = []
        
        table = AdminTable(headers, rows, empty_message="데이터가 없습니다.")
        
        assert table is not None
        assert hasattr(table, 'attrs')
        
    def test_admin_table_with_id(self):
        """테이블 ID 설정 테스트."""
        headers = ["이름"]
        rows = [["홍길동"]]
        table_id = "test-table"
        
        table = AdminTable(headers, rows, table_id=table_id)
        
        assert table.attrs.get("id") == table_id


class TestAdminModal:
    """AdminModal 컴포넌트 테스트."""
    
    def test_admin_modal_basic(self):
        """기본 모달 생성 테스트."""
        modal = AdminModal(
            title="테스트 모달",
            content="모달 내용",
            modal_id="test-modal"
        )
        
        assert modal is not None
        assert hasattr(modal, 'attrs')
        assert modal.attrs.get("id") == "test-modal"
        
    def test_admin_modal_sizes(self):
        """모달 크기 옵션 테스트."""
        sizes = ["sm", "md", "lg", "xl", "2xl"]
        
        for size in sizes:
            modal = AdminModal(
                title="테스트",
                content="내용",
                modal_id=f"modal-{size}",
                size=size
            )
            assert modal is not None
            assert hasattr(modal, 'attrs')
            
    def test_admin_modal_not_closable(self):
        """닫기 불가능한 모달 테스트."""
        modal = AdminModal(
            title="테스트 모달",
            content="모달 내용", 
            modal_id="test-modal",
            closable=False
        )
        
        assert modal is not None
        assert hasattr(modal, 'attrs')


class TestAdminForm:
    """AdminForm 컴포넌트 테스트."""
    
    def test_admin_form_basic(self):
        """기본 폼 생성 테스트."""
        fields = [
            {
                "name": "email",
                "label": "이메일",
                "type": "email",
                "required": True
            },
            {
                "name": "password",
                "label": "비밀번호",
                "type": "password", 
                "required": True
            }
        ]
        
        form = AdminForm(
            fields=fields,
            action="/submit",
            method="POST"
        )
        
        assert form is not None
        assert hasattr(form, 'attrs')
        assert form.attrs.get("action") == "/submit"
        assert form.attrs.get("method") == "POST"
        
    def test_admin_form_select_field(self):
        """셀렉트 필드가 있는 폼 테스트."""
        fields = [
            {
                "name": "role",
                "label": "역할",
                "type": "select",
                "options": [
                    {"value": "admin", "label": "관리자"},
                    {"value": "user", "label": "사용자"}
                ]
            }
        ]
        
        form = AdminForm(fields=fields, action="/submit")
        
        assert form is not None
        assert hasattr(form, 'attrs')
        
    def test_admin_form_textarea_field(self):
        """텍스트에어리어 필드가 있는 폼 테스트."""
        fields = [
            {
                "name": "description",
                "label": "설명",
                "type": "textarea",
                "rows": 5
            }
        ]
        
        form = AdminForm(fields=fields, action="/submit")
        
        assert form is not None
        assert hasattr(form, 'attrs')
        
    def test_admin_form_checkbox_field(self):
        """체크박스 필드가 있는 폼 테스트."""
        fields = [
            {
                "name": "permissions",
                "label": "권한",
                "type": "checkbox",
                "options": [
                    {"value": "read", "label": "읽기", "checked": True},
                    {"value": "write", "label": "쓰기", "checked": False}
                ]
            }
        ]
        
        form = AdminForm(fields=fields, action="/submit")
        
        assert form is not None
        assert hasattr(form, 'attrs')
        
    def test_admin_form_grid_layout(self):
        """그리드 레이아웃 폼 테스트."""
        fields = [
            {"name": "field1", "label": "필드 1"},
            {"name": "field2", "label": "필드 2"}
        ]
        
        form = AdminForm(
            fields=fields,
            action="/submit",
            grid_cols=2
        )
        
        assert form is not None
        assert hasattr(form, 'attrs')


class TestStatsCard:
    """StatsCard 컴포넌트 테스트."""
    
    def test_stats_card_basic(self):
        """기본 통계 카드 테스트."""
        card = StatsCard(
            title="총 사용자",
            value=150
        )
        
        assert card is not None
        assert hasattr(card, 'attrs')
        assert "p-6" in card.attrs.get("class", "")
        
    def test_stats_card_with_icon(self):
        """아이콘이 있는 통계 카드 테스트."""
        card = StatsCard(
            title="총 사용자",
            value=150,
            icon="👥"
        )
        
        assert card is not None
        assert hasattr(card, 'attrs')
        
    def test_stats_card_with_trend(self):
        """트렌드가 있는 통계 카드 테스트."""
        card = StatsCard(
            title="총 사용자",
            value=150,
            trend={"value": "+5%", "positive": True}
        )
        
        assert card is not None
        assert hasattr(card, 'attrs')
        
    def test_stats_card_colors(self):
        """다양한 색상의 통계 카드 테스트."""
        colors = ["blue", "green", "red", "yellow", "purple"]
        
        for color in colors:
            card = StatsCard(
                title="테스트",
                value=100,
                color=color
            )
            assert card is not None
            assert hasattr(card, 'attrs')
            
    def test_stats_card_with_subtitle(self):
        """부제목이 있는 통계 카드 테스트."""
        card = StatsCard(
            title="총 사용자",
            value=150,
            subtitle="지난 달 대비"
        )
        
        assert card is not None
        assert hasattr(card, 'attrs')


class TestFilterBar:
    """FilterBar 컴포넌트 테스트."""
    
    def test_filter_bar_basic(self):
        """기본 필터 바 테스트."""
        filters = [
            {
                "name": "status",
                "label": "상태",
                "options": [
                    {"value": "active", "label": "활성"},
                    {"value": "inactive", "label": "비활성"}
                ]
            }
        ]
        
        filter_bar = FilterBar(
            filters=filters,
            htmx_endpoint="/filter"
        )
        
        assert filter_bar is not None
        assert hasattr(filter_bar, 'attrs')
        assert filter_bar.attrs.get("id") == "filter-bar"
        
    def test_filter_bar_custom_search(self):
        """커스텀 검색 플레이스홀더 테스트."""
        filters = []
        
        filter_bar = FilterBar(
            filters=filters,
            search_placeholder="사용자 검색...",
            search_name="user_search",
            htmx_endpoint="/search"
        )
        
        assert filter_bar is not None
        assert hasattr(filter_bar, 'attrs')
        
    def test_filter_bar_custom_container_id(self):
        """커스텀 컨테이너 ID 테스트."""
        filters = []
        container_id = "custom-filter"
        
        filter_bar = FilterBar(
            filters=filters,
            container_id=container_id,
            htmx_endpoint="/filter"
        )
        
        assert filter_bar.attrs.get("id") == container_id


class TestAdminCard:
    """AdminCard 컴포넌트 테스트."""
    
    def test_admin_card_basic(self):
        """기본 카드 테스트."""
        card = AdminCard(
            title="테스트 카드",
            content="카드 내용"
        )
        
        assert card is not None
        assert hasattr(card, 'attrs')
        assert "rounded-lg" in card.attrs.get("class", "")
        
    def test_admin_card_with_actions(self):
        """액션 버튼이 있는 카드 테스트."""
        from fasthtml.common import Button
        
        actions = [
            Button("편집", cls="btn-primary"),
            Button("삭제", cls="btn-danger")
        ]
        
        card = AdminCard(
            title="테스트 카드",
            content="카드 내용",
            actions=actions
        )
        
        assert card is not None
        assert hasattr(card, 'attrs')
        
    def test_admin_card_colors(self):
        """다양한 색상의 카드 테스트."""
        colors = ["white", "gray", "blue", "green"]
        
        for color in colors:
            card = AdminCard(
                title="테스트",
                content="내용",
                color=color
            )
            assert card is not None
            assert hasattr(card, 'attrs')


class TestAdminBreadcrumb:
    """AdminBreadcrumb 컴포넌트 테스트."""
    
    def test_admin_breadcrumb_basic(self):
        """기본 breadcrumb 테스트."""
        items = [
            {"label": "홈", "url": "/"},
            {"label": "관리자", "url": "/admin"},
            {"label": "사용자"}
        ]
        
        breadcrumb = AdminBreadcrumb(items)
        
        assert breadcrumb is not None
        assert hasattr(breadcrumb, 'attrs')
        
    def test_admin_breadcrumb_single_item(self):
        """단일 항목 breadcrumb 테스트."""
        items = [{"label": "홈"}]
        
        breadcrumb = AdminBreadcrumb(items)
        
        assert breadcrumb is not None
        assert hasattr(breadcrumb, 'attrs')
        
    def test_admin_breadcrumb_without_urls(self):
        """URL이 없는 breadcrumb 테스트."""
        items = [
            {"label": "홈"},
            {"label": "관리자"},
            {"label": "사용자"}
        ]
        
        breadcrumb = AdminBreadcrumb(items)
        
        assert breadcrumb is not None
        assert hasattr(breadcrumb, 'attrs')


class TestConfirmDialog:
    """ConfirmDialog 컴포넌트 테스트."""
    
    def test_confirm_dialog_basic(self):
        """기본 확인 대화상자 테스트."""
        dialog_js = ConfirmDialog(
            message="정말 삭제하시겠습니까?",
            confirm_text="삭제",
            cancel_text="취소"
        )
        
        assert isinstance(dialog_js, str)
        assert "confirm(" in dialog_js
        assert "정말 삭제하시겠습니까?" in dialog_js
        
    def test_confirm_dialog_custom_id(self):
        """커스텀 ID 확인 대화상자 테스트."""
        dialog_js = ConfirmDialog(
            message="삭제하시겠습니까?",
            dialog_id="delete-confirm"
        )
        
        assert isinstance(dialog_js, str)
        assert "showConfirmDialog_delete-confirm" in dialog_js


class TestLoadingSpinner:
    """LoadingSpinner 컴포넌트 테스트."""
    
    def test_loading_spinner_basic(self):
        """기본 로딩 스피너 테스트."""
        spinner = LoadingSpinner()
        
        assert spinner is not None
        assert hasattr(spinner, 'attrs')
        assert "flex justify-center items-center" in spinner.attrs.get("class", "")
        
    def test_loading_spinner_sizes(self):
        """다양한 크기의 로딩 스피너 테스트."""
        sizes = ["sm", "md", "lg"]
        
        for size in sizes:
            spinner = LoadingSpinner(size=size)
            assert spinner is not None
            assert hasattr(spinner, 'attrs')
            
    def test_loading_spinner_colors(self):
        """다양한 색상의 로딩 스피너 테스트."""
        colors = ["blue", "green", "red", "gray"]
        
        for color in colors:
            spinner = LoadingSpinner(color=color)
            assert spinner is not None
            assert hasattr(spinner, 'attrs')
            
    def test_loading_spinner_custom_size_and_color(self):
        """커스텀 크기와 색상 로딩 스피너 테스트."""
        spinner = LoadingSpinner(size="lg", color="green")
        
        assert spinner is not None
        assert hasattr(spinner, 'attrs')


class TestComponentIntegration:
    """컴포넌트 통합 테스트."""
    
    def test_components_work_together(self):
        """여러 컴포넌트가 함께 작동하는지 테스트."""
        # StatsCard를 포함한 AdminCard
        stats_content = StatsCard(
            title="총 사용자",
            value=150,
            color="blue"
        )
        
        card = AdminCard(
            title="사용자 통계",
            content=stats_content
        )
        
        assert card is not None
        assert hasattr(card, 'attrs')
        
        # AdminForm을 포함한 AdminModal
        form_fields = [
            {"name": "name", "label": "이름", "required": True}
        ]
        
        form = AdminForm(
            fields=form_fields,
            action="/submit"
        )
        
        modal = AdminModal(
            title="사용자 추가",
            content=form,
            modal_id="user-add-modal"
        )
        
        assert modal is not None
        assert hasattr(modal, 'attrs')
        
    def test_component_css_classes(self):
        """컴포넌트의 CSS 클래스가 올바른지 테스트."""
        # 각 컴포넌트가 적절한 Tailwind CSS 클래스를 가지는지 확인
        table = AdminTable(["헤더"], [["데이터"]])
        table_classes = table.attrs.get("class", "")
        assert "min-w-full" in table_classes
        assert "divide-y" in table_classes
        
        card = StatsCard("제목", 100)
        card_classes = card.attrs.get("class", "")
        assert "p-6" in card_classes
        assert "rounded-lg" in card_classes
        assert "shadow-sm" in card_classes
        
    def test_component_accessibility(self):
        """컴포넌트의 접근성 요소 테스트."""
        # AdminForm의 label과 input 연결 확인
        fields = [
            {
                "name": "email",
                "label": "이메일 주소",
                "type": "email",
                "required": True
            }
        ]
        
        form = AdminForm(fields=fields, action="/submit")
        
        # Form이 올바르게 생성되는지 확인
        assert form is not None
        assert hasattr(form, 'attrs')
        
        # AdminBreadcrumb의 네비게이션 구조 확인
        items = [
            {"label": "홈", "url": "/"},
            {"label": "현재 페이지"}
        ]
        
        breadcrumb = AdminBreadcrumb(items)
        assert breadcrumb is not None
        assert hasattr(breadcrumb, 'attrs')


class TestComponentHTML:
    """컴포넌트 HTML 출력 테스트."""
    
    def test_admin_table_html_output(self):
        """AdminTable HTML 출력 테스트."""
        headers = ["이름", "이메일"]
        rows = [["홍길동", "hong@example.com"]]
        
        table = AdminTable(headers, rows, table_id="test-table")
        html_output = to_xml(table)
        
        assert 'id="test-table"' in html_output
        assert "홍길동" in html_output
        assert "hong@example.com" in html_output
        
    def test_stats_card_html_output(self):
        """StatsCard HTML 출력 테스트."""
        card = StatsCard(
            title="사용자 수",
            value=42,
            icon="👥",
            color="blue"
        )
        html_output = to_xml(card)
        
        assert "사용자 수" in html_output
        assert "42" in html_output
        assert "👥" in html_output
        
    def test_admin_form_html_output(self):
        """AdminForm HTML 출력 테스트."""
        fields = [
            {
                "name": "username",
                "label": "사용자명",
                "type": "text",
                "required": True
            }
        ]
        
        form = AdminForm(
            fields=fields,
            action="/submit",
            method="POST",
            form_id="test-form"
        )
        html_output = to_xml(form)
        
        assert 'action="/submit"' in html_output
        assert 'method="POST"' in html_output
        assert 'name="username"' in html_output
        assert "사용자명" in html_output


class TestAnalyticsChart:
    """AnalyticsChart 컴포넌트 테스트."""
    
    def test_analytics_chart_basic(self):
        """기본 차트 생성 테스트."""
        chart_data = {
            "labels": ["1월", "2월", "3월"],
            "datasets": [{
                "label": "사용량",
                "data": [10, 20, 30]
            }]
        }
        
        chart = AnalyticsChart(
            chart_type="line",
            data=chart_data,
            canvas_id="test-chart"
        )
        
        assert chart is not None
        assert hasattr(chart, 'attrs')
        
    def test_analytics_chart_types(self):
        """다양한 차트 타입 테스트."""
        chart_data = {"labels": ["A", "B"], "datasets": [{"data": [1, 2]}]}
        chart_types = ["line", "bar", "pie", "doughnut", "radar"]
        
        for chart_type in chart_types:
            chart = AnalyticsChart(
                chart_type=chart_type,
                data=chart_data,
                canvas_id=f"chart-{chart_type}"
            )
            assert chart is not None
            assert hasattr(chart, 'attrs')
            
    def test_analytics_chart_with_title(self):
        """제목이 있는 차트 테스트."""
        chart_data = {"labels": ["A"], "datasets": [{"data": [1]}]}
        
        chart = AnalyticsChart(
            chart_type="bar",
            data=chart_data,
            canvas_id="titled-chart",
            title="차트 제목"
        )
        
        assert chart is not None
        assert hasattr(chart, 'attrs')
        
    def test_analytics_chart_dimensions(self):
        """커스텀 차트 크기 테스트."""
        chart_data = {"labels": ["A"], "datasets": [{"data": [1]}]}
        
        chart = AnalyticsChart(
            chart_type="line",
            data=chart_data,
            canvas_id="sized-chart",
            width=600,
            height=400
        )
        
        assert chart is not None
        assert hasattr(chart, 'attrs')


class TestExportButton:
    """ExportButton 컴포넌트 테스트."""
    
    def test_export_button_basic(self):
        """기본 내보내기 버튼 테스트."""
        button = ExportButton(
            export_type="csv",
            endpoint="/export/users.csv",
            filename="users.csv"
        )
        
        assert button is not None
        assert hasattr(button, 'attrs')
        assert button.attrs.get("href") == "/export/users.csv"
        
    def test_export_button_types(self):
        """다양한 내보내기 타입 테스트."""
        export_types = ["csv", "json", "xlsx", "pdf"]
        
        for export_type in export_types:
            button = ExportButton(
                export_type=export_type,
                endpoint=f"/export/data.{export_type}",
                filename=f"data.{export_type}"
            )
            assert button is not None
            assert hasattr(button, 'attrs')
            
    def test_export_button_colors(self):
        """다양한 색상의 내보내기 버튼 테스트."""
        colors = ["blue", "green", "red", "gray", "yellow"]
        
        for color in colors:
            button = ExportButton(
                export_type="csv",
                endpoint="/export/data.csv",
                filename="data.csv",
                color=color
            )
            assert button is not None
            assert hasattr(button, 'attrs')
            
    def test_export_button_sizes(self):
        """다양한 크기의 내보내기 버튼 테스트."""
        sizes = ["sm", "md", "lg", "xl"]
        
        for size in sizes:
            button = ExportButton(
                export_type="json",
                endpoint="/export/data.json",
                filename="data.json",
                size=size
            )
            assert button is not None
            assert hasattr(button, 'attrs')
            
    def test_export_button_disabled(self):
        """비활성화된 내보내기 버튼 테스트."""
        button = ExportButton(
            export_type="csv",
            endpoint="/export/data.csv",
            filename="data.csv",
            disabled=True
        )
        
        assert button is not None
        assert hasattr(button, 'attrs')
        
    def test_export_button_with_icon(self):
        """아이콘이 있는 내보내기 버튼 테스트."""
        button = ExportButton(
            export_type="pdf",
            endpoint="/export/report.pdf",
            filename="report.pdf",
            icon="📊"
        )
        
        assert button is not None
        assert hasattr(button, 'attrs')


class TestMetricsTable:
    """MetricsTable 컴포넌트 테스트."""
    
    def test_metrics_table_basic(self):
        """기본 메트릭 테이블 테스트."""
        metrics_data = [
            {
                "tool_name": "search_web",
                "usage_count": 150,
                "avg_response_time": "250ms",
                "error_rate": "2%"
            },
            {
                "tool_name": "search_vectors",
                "usage_count": 89,
                "avg_response_time": "180ms",
                "error_rate": "1%"
            }
        ]
        
        table = MetricsTable(
            metrics_data=metrics_data,
            metric_type="tools"
        )
        
        assert table is not None
        assert hasattr(table, 'attrs')
        
    def test_metrics_table_with_trends(self):
        """트렌드가 있는 메트릭 테이블 테스트."""
        metrics_data = [
            {
                "tool_name": "search_web",
                "usage_count": 150,
                "trend": "+15%"
            }
        ]
        
        table = MetricsTable(
            metrics_data=metrics_data,
            metric_type="tools",
            show_trends=True
        )
        
        assert table is not None
        assert hasattr(table, 'attrs')
        
    def test_metrics_table_sortable(self):
        """정렬 가능한 메트릭 테이블 테스트."""
        metrics_data = [
            {"tool_name": "tool1", "usage_count": 100},
            {"tool_name": "tool2", "usage_count": 200}
        ]
        
        table = MetricsTable(
            metrics_data=metrics_data,
            metric_type="tools",
            sortable=True
        )
        
        assert table is not None
        assert hasattr(table, 'attrs')
        
    def test_metrics_table_user_type(self):
        """사용자 메트릭 테이블 테스트."""
        metrics_data = [
            {
                "user_id": "user1",
                "request_count": 50,
                "last_active": "2023-01-01"
            }
        ]
        
        table = MetricsTable(
            metrics_data=metrics_data,
            metric_type="users"
        )
        
        assert table is not None
        assert hasattr(table, 'attrs')
        
    def test_metrics_table_with_custom_id(self):
        """커스텀 ID가 있는 메트릭 테이블 테스트."""
        metrics_data = [{"tool_name": "test", "usage_count": 1}]
        table_id = "custom-metrics-table"
        
        table = MetricsTable(
            metrics_data=metrics_data,
            metric_type="tools",
            table_id=table_id
        )
        
        assert table.attrs.get("id") == table_id


class TestNotificationBanner:
    """NotificationBanner 컴포넌트 테스트."""
    
    def test_notification_banner_basic(self):
        """기본 알림 배너 테스트."""
        banner = NotificationBanner(
            message="작업이 완료되었습니다.",
            type="success"
        )
        
        assert banner is not None
        assert hasattr(banner, 'attrs')
        
    def test_notification_banner_types(self):
        """다양한 알림 타입 테스트."""
        notification_types = ["info", "success", "warning", "error"]
        
        for noti_type in notification_types:
            banner = NotificationBanner(
                message=f"{noti_type} 메시지",
                type=noti_type
            )
            assert banner is not None
            assert hasattr(banner, 'attrs')
            
    def test_notification_banner_dismissible(self):
        """닫기 가능한 알림 배너 테스트."""
        banner = NotificationBanner(
            message="닫을 수 있는 알림",
            type="info",
            dismissible=True
        )
        
        assert banner is not None
        assert hasattr(banner, 'attrs')
        
    def test_notification_banner_with_icon(self):
        """아이콘이 있는 알림 배너 테스트."""
        banner = NotificationBanner(
            message="아이콘 알림",
            type="success",
            icon="✅"
        )
        
        assert banner is not None
        assert hasattr(banner, 'attrs')
        
    def test_notification_banner_with_action(self):
        """액션 버튼이 있는 알림 배너 테스트."""
        banner = NotificationBanner(
            message="액션이 있는 알림",
            type="info",
            action_text="자세히 보기",
            action_url="/details"
        )
        
        assert banner is not None
        assert hasattr(banner, 'attrs')
        
    def test_notification_banner_not_dismissible(self):
        """닫기 불가능한 알림 배너 테스트."""
        banner = NotificationBanner(
            message="중요한 알림",
            type="error",
            dismissible=False
        )
        
        assert banner is not None
        assert hasattr(banner, 'attrs')
        
    def test_notification_banner_with_custom_id(self):
        """커스텀 ID가 있는 알림 배너 테스트."""
        banner_id = "custom-notification"
        
        banner = NotificationBanner(
            message="커스텀 ID 알림",
            type="info",
            banner_id=banner_id
        )
        
        assert banner.attrs.get("id") == banner_id


class TestLanguageSelector:
    """LanguageSelector 컴포넌트 테스트."""
    
    def test_language_selector_basic(self):
        """기본 언어 선택기 테스트."""
        selector = LanguageSelector(
            current_language="ko",
            endpoint="/admin/change-language"
        )
        
        assert selector is not None
        assert hasattr(selector, 'attrs')
        
    def test_language_selector_english_default(self):
        """영어 기본값 언어 선택기 테스트."""
        selector = LanguageSelector(
            current_language="en",
            endpoint="/change-lang"
        )
        
        assert selector is not None
        assert hasattr(selector, 'attrs')
        
    def test_language_selector_sizes(self):
        """다양한 크기의 언어 선택기 테스트."""
        sizes = ["sm", "md", "lg"]
        
        for size in sizes:
            selector = LanguageSelector(
                current_language="ko",
                endpoint="/change-language",
                size=size
            )
            assert selector is not None
            assert hasattr(selector, 'attrs')
            
    def test_language_selector_with_flag(self):
        """국기 표시가 있는 언어 선택기 테스트."""
        selector = LanguageSelector(
            current_language="ko",
            endpoint="/change-language",
            show_flag=True
        )
        
        assert selector is not None
        assert hasattr(selector, 'attrs')
        
    def test_language_selector_without_flag(self):
        """국기 표시가 없는 언어 선택기 테스트."""
        selector = LanguageSelector(
            current_language="en",
            endpoint="/change-language",
            show_flag=False
        )
        
        assert selector is not None
        assert hasattr(selector, 'attrs')
        
    def test_language_selector_custom_target(self):
        """커스텀 타겟이 있는 언어 선택기 테스트."""
        selector = LanguageSelector(
            current_language="ko",
            endpoint="/change-language",
            target="#content-area"
        )
        
        assert selector is not None
        assert hasattr(selector, 'attrs')
        
    def test_language_selector_with_custom_id(self):
        """커스텀 ID가 있는 언어 선택기 테스트."""
        selector_id = "custom-language-selector"
        
        selector = LanguageSelector(
            current_language="ko",
            endpoint="/change-language",
            selector_id=selector_id
        )
        
        assert selector.attrs.get("id") == selector_id


class TestNewComponentIntegration:
    """새로운 컴포넌트 통합 테스트."""
    
    def test_analytics_chart_in_admin_card(self):
        """AdminCard 안의 AnalyticsChart 테스트."""
        chart_data = {
            "labels": ["1월", "2월"],
            "datasets": [{"data": [10, 20]}]
        }
        
        chart = AnalyticsChart(
            chart_type="line",
            data=chart_data,
            canvas_id="card-chart"
        )
        
        card = AdminCard(
            title="분석 차트",
            content=chart
        )
        
        assert card is not None
        assert hasattr(card, 'attrs')
        
    def test_export_button_in_filter_bar(self):
        """FilterBar와 ExportButton 조합 테스트."""
        filters = []
        
        filter_bar = FilterBar(
            filters=filters,
            htmx_endpoint="/filter"
        )
        
        export_button = ExportButton(
            export_type="csv",
            endpoint="/export/data.csv",
            filename="data.csv"
        )
        
        # 두 컴포넌트가 독립적으로 작동하는지 확인
        assert filter_bar is not None
        assert export_button is not None
        assert hasattr(filter_bar, 'attrs')
        assert hasattr(export_button, 'attrs')
        
    def test_notification_banner_with_language_selector(self):
        """알림 배너와 언어 선택기 조합 테스트."""
        banner = NotificationBanner(
            message="언어가 변경되었습니다.",
            type="success"
        )
        
        selector = LanguageSelector(
            current_language="ko",
            endpoint="/change-language"
        )
        
        assert banner is not None
        assert selector is not None
        assert hasattr(banner, 'attrs')
        assert hasattr(selector, 'attrs')
        
    def test_metrics_table_with_export_button(self):
        """메트릭 테이블과 내보내기 버튼 조합 테스트."""
        metrics_data = [
            {"tool_name": "test_tool", "usage_count": 100}
        ]
        
        table = MetricsTable(
            metrics_data=metrics_data,
            metric_type="tools"
        )
        
        export_button = ExportButton(
            export_type="json",
            endpoint="/export/metrics.json",
            filename="metrics.json"
        )
        
        assert table is not None
        assert export_button is not None
        assert hasattr(table, 'attrs')
        assert hasattr(export_button, 'attrs')


class TestNewComponentHTML:
    """새로운 컴포넌트 HTML 출력 테스트."""
    
    def test_analytics_chart_html_output(self):
        """AnalyticsChart HTML 출력 테스트."""
        chart_data = {"labels": ["A"], "datasets": [{"data": [1]}]}
        
        chart = AnalyticsChart(
            chart_type="bar",
            data=chart_data,
            canvas_id="test-chart",
            title="테스트 차트"
        )
        html_output = to_xml(chart)
        
        assert 'id="test-chart"' in html_output
        assert "canvas" in html_output.lower()
        assert "테스트 차트" in html_output
        
    def test_export_button_html_output(self):
        """ExportButton HTML 출력 테스트."""
        button = ExportButton(
            export_type="csv",
            endpoint="/export/users.csv",
            filename="users.csv",
            icon="📊"
        )
        html_output = to_xml(button)
        
        assert 'href="/export/users.csv"' in html_output
        assert "📊" in html_output
        assert "csv" in html_output.lower()
        
    def test_metrics_table_html_output(self):
        """MetricsTable HTML 출력 테스트."""
        metrics_data = [
            {
                "tool_name": "search_web",
                "usage_count": 150
            }
        ]
        
        table = MetricsTable(
            metrics_data=metrics_data,
            metric_type="tools",
            table_id="metrics-table"
        )
        html_output = to_xml(table)
        
        assert 'id="metrics-table"' in html_output
        assert "search_web" in html_output
        assert "150" in html_output
        
    def test_notification_banner_html_output(self):
        """NotificationBanner HTML 출력 테스트."""
        banner = NotificationBanner(
            message="테스트 알림 메시지",
            type="success",
            icon="✅",
            banner_id="test-banner"
        )
        html_output = to_xml(banner)
        
        assert 'id="test-banner"' in html_output
        assert "테스트 알림 메시지" in html_output
        assert "✅" in html_output
        
    def test_language_selector_html_output(self):
        """LanguageSelector HTML 출력 테스트."""
        selector = LanguageSelector(
            current_language="ko",
            endpoint="/change-language",
            selector_id="lang-selector"
        )
        html_output = to_xml(selector)
        
        assert 'id="lang-selector"' in html_output
        assert "한국어" in html_output
        assert "English" in html_output
        assert "/change-language" in html_output


class TestNewComponentCSS:
    """새로운 컴포넌트 CSS 클래스 테스트."""
    
    def test_new_components_have_proper_css_classes(self):
        """새로운 컴포넌트들이 적절한 CSS 클래스를 가지는지 테스트."""
        # ExportButton CSS 클래스 확인
        button = ExportButton(
            export_type="csv",
            endpoint="/export/data.csv",
            filename="data.csv"
        )
        button_classes = button.attrs.get("class", "")
        assert "inline-flex" in button_classes
        assert "items-center" in button_classes
        
        # NotificationBanner CSS 클래스 확인
        banner = NotificationBanner(
            message="테스트",
            type="info"
        )
        banner_classes = banner.attrs.get("class", "")
        assert "p-4" in banner_classes
        assert "rounded-md" in banner_classes
        
        # LanguageSelector CSS 클래스 확인
        selector = LanguageSelector(
            current_language="ko",
            endpoint="/change-language"
        )
        selector_classes = selector.attrs.get("class", "")
        assert "flex" in selector_classes
        assert "items-center" in selector_classes