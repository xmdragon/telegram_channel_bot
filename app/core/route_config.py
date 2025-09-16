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
        """消息相关路由 - 统一action-first设计"""
        # 基础查询
        list = "/messages/"
        channel_info = "/messages/channel-info"
        detail = "/messages/detail/{message_id}"
        
        # 核心操作 - action-first模式
        approve = "/messages/approve/{message_id}"
        reject = "/messages/reject/{message_id}"
        restore = "/messages/restore/{message_id}"
        delete = "/messages/delete/{message_id}"
        update = "/messages/update/{message_id}"
        
        # 高级操作
        edit_publish = "/messages/edit-publish/{message_id}"
        publish = "/messages/publish/{message_id}"
        publish_direct = "/messages/publish-direct/{message_id}"
        resend = "/messages/resend/{message_id}"
        
        # 过滤器操作
        filter_content = "/messages/filter-content/{message_id}"
        train_tail = "/messages/train-tail/{message_id}"
        not_ad = "/messages/not-ad/{message_id}"
        refilter = "/messages/refilter/{message_id}"
        feedback = "/messages/feedback/{message_id}"
        delete_review = "/messages/delete-review/{message_id}"
        extract_ad_keywords = "/messages/extract-ad-keywords/{id}"
        mark_as_ad = "/messages/mark-as-ad/{id}"
        
        # 批量操作
        batch_approve = "/messages/batch/approve"
        batch_reject = "/messages/batch/reject"
        batch_delete = "/messages/batch/delete"
        
        
        # 统计相关
        stats_overview = "/messages/stats/overview"
    
    class Admin:
        """管理员相关路由"""
        config = "/admin/config"
        config_batch = "/admin/config/batch"
        config_forwarding = "/admin/config/forwarding"
        restart = "/admin/restart"
        backup = "/admin/backup"
        clear_cache = "/admin/clear-cache"
        export_logs = "/admin/export-logs"
        health = "/admin/health"
        resolve_review_group = "/admin/resolve-review-group"
        review_group_status = "/admin/review-group-status"
        resolve_channel_ids = "/admin/resolve-channel-ids"
        resolve_channel_id = "/admin/resolve-channel-id"
    
    class AdminAuth:
        """管理员认证路由"""
        # 保持与routes.py的兼容性，同时提供简化路径
        login = "/admin/auth/login"  # 完整路径
        logout = "/admin/auth/logout"
        current = "/admin/auth/current"
        change_password = "/admin/auth/change-password"
        check_auth = "/admin/auth/check-auth"
        admins = "/admin/auth/admins"
        admin_by_id = "/admin/auth/admins/{admin_id}"
        sessions = "/admin/auth/sessions"
        session_by_token = "/admin/auth/sessions/{token}"
        me = "/admin/auth/me"
    
    class Auth:
        """Telegram认证路由"""
        init = "/telegram-auth/init"
        send_code = "/telegram-auth/send-code"
        verify_code = "/telegram-auth/verify-code"
        verify_password = "/telegram-auth/verify-password"
        resend_code = "/telegram-auth/resend-code"
        status = "/telegram-auth/status"
        disconnect = "/telegram-auth/disconnect"
        clear = "/telegram-auth/clear"
        info = "/telegram-auth/info"
        websocket = "/telegram-auth/ws/auth"  # WebSocket认证连接
    
    class Config:
        """配置管理路由"""
        base = "/config/"
        by_key = "/config/{config_key}"
        reload = "/config/reload"
        resolve_group_id = "/config/resolve-group-id"
        resolve_target_channel = "/config/resolve-target-channel"
        categories_telegram = "/config/categories/telegram"
        categories_channels = "/config/categories/channels"
        categories_filter = "/config/categories/filter"
        categories_review = "/config/categories/review"
        batch = "/config/batch"
        batch_update = "/config/batch-update"
        reset_defaults = "/config/reset-defaults"
    
    class System:
        """系统相关路由"""
        # 健康检查（保留实际使用的端点）
        status = "/system/status"
        status_detailed = "/system/status-detailed"
        health = "/system/health"
        lock_status = "/system/lock-status"
        clear_lock = "/system/clear-lock"
        auto_clear_lock = "/system/auto-clear-lock"
        logs_realtime = "/system/logs/realtime"
        
        
        # 服务管理
        services = "/system/services"
        service_status = "/system/services/{service_name}/status"
        service_start = "/system/services/{service_name}/start"
        service_stop = "/system/services/{service_name}/stop"
        service_restart = "/system/services/{service_name}/restart"
        
        # 维护操作
        restart = "/system/restart"
        reset = "/system/reset"
    
    
    
    class Channels:
        """统一的频道管理路由"""
        # 基础管理
        list = "/"
        add = "/"
        delete = "/{channel_id}"
        get = "/{channel_id}"

        # 批量操作
        batch_add = "/batch-add"
        search = "/search"

        # 解析功能（仅源频道）
        resolve = "/resolve"
        resolve_all = "/resolve-all"
    
    class Training:
        """训练数据管理路由"""
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
        
        # 基础训练（保留实际使用的端点）
        mark_ad_message = "/training/mark-ad-message"
        separator_patterns = "/training/separator-patterns"
        test_separator = "/training/test-separator"
        
        
        
        # 尾部过滤器
        tail_filter_statistics = "/training/tail-filter-statistics"
        tail_filter_history = "/training/tail-filter-history"
        tail_filter_samples = "/training/tail-filter-samples"
        tail_filter_samples_by_id = "/training/tail-filter-samples/{sample_id}"
        tail_filter_detect_duplicates = "/training/tail-filter-samples/detect-duplicates"
        tail_filter_deduplicate = "/training/tail-filter-samples/deduplicate"
        
        
        # 媒体文件（保留实际使用的端点）
        media_files = "/training/media-files"
        media_files_by_hash = "/training/media-files/{file_hash}"
        media_files_clean_orphaned = "/training/media-files/clean-orphaned"
        media_files_rebuild_visual_hashes = "/training/media-files/rebuild-visual-hashes"
        media_files_export = "/training/media-files/export"
        
        
        # 关键词管理
        ad_keywords = "/training/ad-keywords"
        ad_keywords_by_keyword = "/training/ad-keywords/{keyword}"
        ad_keywords_threshold = "/training/ad-keywords/threshold"
        ad_keywords_stats = "/training/ad-keywords/stats"
    
    def __init__(self):
        self.messages = self.Messages()
        self.admin = self.Admin()
        self.admin_auth = self.AdminAuth()
        self.auth = self.Auth()
        self.config = self.Config()
        self.system = self.System()
        self.channels = self.Channels()
        self.training = self.Training()

# 全局路由配置实例
ROUTES = RouteConfig()