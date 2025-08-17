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
        list = "/"
        channel_info = "/channel-info"
        detail = "/detail/{message_id}"
        approve = "/detail/{message_id}/approve"
        reject = "/detail/{message_id}/reject"
        delete = "/detail/{message_id}"
        
        # 批量操作
        batch_approve = "/batch/approve"
        batch_reject = "/batch/reject"
        batch_delete = "/batch/delete"
        batch_refetch_media = "/batch/refetch-media"
        
        # 过滤器操作
        filter_tail = "/{message_id}/filter-tail"
        refilter = "/{message_id}/refilter"
        train_tail = "/{message_id}/train-tail"
        not_ad = "/{message_id}/not-ad"
        feedback = "/{message_id}/feedback"
        
        # 阈值管理
        thresholds_stats = "/thresholds/stats"
        thresholds_optimize = "/thresholds/optimize"
        thresholds_reset = "/thresholds/{filter_name}/{metric_name}/reset"
        
        # 统计相关
        stats_overview = "/stats/overview"
        stats_channel = "/stats/channel/{channel_id}"
        stats_performance = "/stats/performance"
        stats_filters = "/stats/filters"
        stats_trending = "/stats/trending"
        health_check = "/health-check"
        metrics = "/metrics"
        reports_generate = "/reports/generate"
    
    class Admin:
        """管理员相关路由"""
        channels = "/channels"
        channels_by_name = "/channels/{channel_name}"
        channels_refresh_titles = "/channels/refresh-titles"
        search_channels = "/search-channels"
        collect_history = "/collect-history/{channel_id}"
        collect_history_progress = "/collect-history/progress"
        collect_history_stop = "/collect-history/{channel_id}/stop"
        config = "/config"
        config_batch = "/config/batch"
        config_forwarding = "/config/forwarding"
        restart = "/restart"
        backup = "/backup"
        clear_cache = "/clear-cache"
        export_logs = "/export-logs"
        health = "/health"
        resolve_review_group = "/resolve-review-group"
        review_group_status = "/review-group-status"
        resolve_channel_ids = "/resolve-channel-ids"
        resolve_channel_id = "/resolve-channel-id"
    
    class AdminAuth:
        """管理员认证路由"""
        login = "/login"
        logout = "/logout"
        current = "/current"
        change_password = "/change-password"
        check_auth = "/check-auth"
        admins = "/admins"
        admin_by_id = "/admins/{admin_id}"
        permissions = "/permissions"
        sessions = "/sessions"
        session_by_token = "/sessions/{token}"
        me = "/me"
        permissions_me = "/permissions/me"
    
    class Auth:
        """Telegram认证路由"""
        init = "/init"
        send_code = "/send-code"
        verify_code = "/verify-code"
        verify_password = "/verify-password"
        resend_code = "/resend-code"
        status = "/status"
        disconnect = "/disconnect"
        clear = "/clear"
        info = "/info"
    
    class Config:
        """配置管理路由"""
        base = "/"
        by_key = "/{config_key}"
        reload = "/reload"
        resolve_group_id = "/resolve-group-id"
        resolve_target_channel = "/resolve-target-channel"
        categories_telegram = "/categories/telegram"
        categories_channels = "/categories/channels"
        categories_filter = "/categories/filter"
        categories_review = "/categories/review"
        batch = "/batch"
        batch_update = "/batch-update"
        reset_defaults = "/reset-defaults"
        channels_add = "/channels/add"
        channels_by_id = "/channels/{channel_id}"
        channels_status = "/channels/{channel_id}/status"
        channels_list = "/channels/"
        channels_batch_add = "/channels/batch-add"
    
    class System:
        """系统相关路由"""
        # 健康检查
        status = "/status"
        status_detailed = "/status/detailed"
        health = "/health"
        
        # 日志管理
        logs = "/logs"
        logs_realtime = "/logs/realtime"
        
        # 服务管理
        services = "/services"
        service_status = "/services/{service_name}/status"
        service_start = "/services/{service_name}/start"
        service_stop = "/services/{service_name}/stop"
        service_restart = "/services/{service_name}/restart"
        
        # 维护操作
        restart = "/restart"
        reset = "/reset"
        
        # 历史消息采集
        history_progress = "/history-collection/progress"
        history_start = "/history-collection/start/{channel_id}"
        history_stop = "/history-collection/stop/{channel_id}"
    
    class ChannelResolver:
        """频道解析路由"""
        resolve = "/resolve"
        resolve_all = "/resolve-all"
        resolve_target = "/resolve-target"
        resolve_review = "/resolve-review"
    
    class Lock:
        """锁管理路由"""
        status = "/lock/status"
        force_release = "/lock/force-release"
    
    def __init__(self):
        self.messages = self.Messages()
        self.admin = self.Admin()
        self.admin_auth = self.AdminAuth()
        self.auth = self.Auth()
        self.config = self.Config()
        self.system = self.System()
        self.channel_resolver = self.ChannelResolver()
        self.lock = self.Lock()

# 全局路由配置实例
ROUTES = RouteConfig()