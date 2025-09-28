"""
API路由路径配置
集中管理所有API路由路径，禁止在其他文件中硬编码路由路径

使用方法：
from app.core.route_config import ROUTES
@router.get(ROUTES.messages.list)
"""

class RouteConfig:
    """路由配置类"""

    class Messages:
        """消息相关路由"""
        # 基础查询
        list = "/messages/"
        channel_info = "/messages/channel-info"
        detail = "/messages/detail/{message_id}"

        # 核心操作
        approve = "/messages/approve/{message_id}"
        reject = "/messages/reject/{message_id}"
        restore = "/messages/restore/{message_id}"
        delete = "/messages/delete/{message_id}"
        update = "/messages/update/{message_id}"

        # 过滤器操作
        filter_content = "/messages/filter-content/{message_id}"
        mark_as_ad = "/messages/mark-as-ad/{id}"
        not_ad = "/messages/not-ad/{message_id}"
        delete_review = "/messages/delete-review/{message_id}"
        train_tail = "/messages/train-tail/{message_id}"
        feedback = "/messages/feedback/{message_id}"
        refilter = "/messages/refilter/{message_id}"

        # 批量操作
        batch_approve = "/messages/batch/approve"
        batch_reject = "/messages/batch/reject"
        batch_delete = "/messages/batch/delete"

        # 重置操作
        reset_failed = "/messages/reset-failed"

        # 统计相关
        stats_overview = "/messages/stats/overview"

    class Channels:
        """频道管理路由"""
        # 基础管理
        list = "/"
        add = "/"
        get = "/{channel_id}"
        delete = "/{channel_id}"

        # 批量操作
        batch_add = "/batch-add"

        # 搜索功能
        search = "/search"

        # 解析功能
        resolve = "/resolve"

    class Training:
        """训练数据管理路由"""
        # 分隔符模式
        separator_patterns = "/training/separator-patterns"
        test_separator = "/training/test-separator"

        # 文本过滤
        text_filters = "/training/text-filters"
        text_filters_by_keyword = "/training/text-filters/{keyword}"
        text_filters_clear = "/training/text-filters/clear"
        test_text_filter = "/training/test-text-filter"

        # 关键词管理
        ad_keywords = "/training/ad-keywords"
        ad_keywords_by_keyword = "/training/ad-keywords/{keyword}"
        ad_keywords_threshold = "/training/ad-keywords/threshold"
        ad_keywords_stats = "/training/ad-keywords/stats"

        # 广告向量
        ad_vectors = "/training/ad-vectors"
        ad_vector_statistics = "/training/ad-vector-statistics"
        ad_vector_by_id = "/training/ad-vectors/{vector_id}"
        ad_vectors_batch = "/training/ad-vectors/batch"
        ad_vectors_detect_duplicates = "/training/ad-vectors/detect-duplicates"
        ad_vectors_deduplicate = "/training/ad-vectors/deduplicate"
        ad_vector_test_detection = "/training/ad-vectors/test-detection"
        ad_vector_add_from_text = "/training/ad-vectors/add-from-text"
        ad_vector_stats = "/training/ad-vector-stats"

        # 尾部过滤器
        tail_filter_samples = "/training/tail-filter-samples"
        tail_filter_samples_by_id = "/training/tail-filter-samples/{sample_id}"
        tail_filter_statistics = "/training/tail-filter-statistics"
        tail_filter_history = "/training/tail-filter-history"
        tail_filter_detect_duplicates = "/training/tail-filter-samples/detect-duplicates"
        tail_filter_deduplicate = "/training/tail-filter-samples/deduplicate"

        # 媒体文件
        media_files = "/training/media-files"
        media_files_by_hash = "/training/media-files/{file_hash}"
        media_files_clean_orphaned = "/training/media-files/clean-orphaned"
        media_files_export = "/training/media-files/export"

    class AdminAuth:
        """管理员认证路由"""
        login = "/admin/auth/login"
        logout = "/admin/auth/logout"
        check_auth = "/admin/auth/check-auth"
        current = "/admin/auth/current"
        change_password = "/admin/auth/change-password"
        admins = "/admin/auth/admins"
        admin_by_id = "/admin/auth/admins/{admin_id}"
        sessions = "/admin/auth/sessions"
        session_by_token = "/admin/auth/sessions/{token}"
        me = "/admin/auth/me"

    class Admin:
        """管理功能路由"""
        config = "/admin/config"
        config_batch = "/admin/config/batch"
        config_forwarding = "/admin/config/forwarding"

    class DualAuth:
        """双Session认证路由"""
        init_session = "/init-session"
        send_code = "/send-code"
        verify_code = "/verify-code"
        verify_password = "/verify-password"
        session_status = "/session-status/{session_type}"

    class TelegramTools:
        """Telegram工具路由"""
        message_structure = "/message-structure"

    class Services:
        """服务管理路由"""
        status = "/status"
        status_by_service = "/status/{service_name}"
        start = "/start/{service_name}"
        stop = "/stop/{service_name}"
        restart = "/restart/{service_name}"
        logs = "/logs/{service_name}"
        reload_config = "/reload-config"
        info = "/info"

    class System:
        """系统相关路由"""
        health = "/health"
        health_service = "/health/{service_name}"
        status_detailed = "/system/status-detailed"
        reset = "/system/reset"

    class Config:
        """配置管理路由"""
        get = "/config"
        update = "/config"

    class TelegramConfig:
        """Telegram配置管理路由"""
        get = "/telegram-config"
        update = "/telegram-config"

    class Stats:
        """统计路由"""
        get = "/stats"

    class WebRoutes:
        """Web页面重定向路由"""
        root = "/"
        admin = "/admin"
        config = "/config"
        auth = "/auth"
        status = "/status"
        train = "/train"

    class WebServer:
        """Web服务器路径配置"""
        api_prefix = "/api"
        static_mount = "/static"
        temp_media_mount = "/temp_media"

    class WebSocketRoutes:
        """WebSocket路径配置"""
        main = "/ws"
        api_messages = "/api/ws/messages"
        api_websocket = "/api/websocket"

    def __init__(self):
        # 按照统一顺序初始化
        self.messages = self.Messages()
        self.channels = self.Channels()
        self.training = self.Training()
        self.admin_auth = self.AdminAuth()
        self.admin = self.Admin()
        self.dual_auth = self.DualAuth()
        self.telegram_tools = self.TelegramTools()
        self.services = self.Services()
        self.system = self.System()
        self.config = self.Config()
        self.telegram_config = self.TelegramConfig()
        self.stats = self.Stats()
        self.web = self.WebRoutes()
        self.web_server = self.WebServer()
        self.websocket_routes = self.WebSocketRoutes()

# 全局路由配置实例
ROUTES = RouteConfig()