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
        list = "/messages/"
        channel_info = "/messages/channel-info"
        detail = "/messages/detail/{message_id}"
        approve = "/messages/detail/{message_id}/approve"
        reject = "/messages/detail/{message_id}/reject"
        delete = "/messages/detail/{message_id}"
        
        # 批量操作
        batch_approve = "/messages/batch/approve"
        batch_reject = "/messages/batch/reject"
        batch_delete = "/messages/batch/delete"
        batch_refetch_media = "/messages/batch/refetch-media"
        
        # 过滤器操作
        filter_tail = "/messages/{message_id}/filter-tail"
        refilter = "/messages/{message_id}/refilter"
        train_tail = "/messages/{message_id}/train-tail"
        not_ad = "/messages/{message_id}/not-ad"
        feedback = "/messages/{message_id}/feedback"
        
        
        # 统计相关
        stats_overview = "/messages/stats/overview"
        stats_channel = "/messages/stats/channel/{channel_id}"
        stats_performance = "/messages/stats/performance"
        stats_filters = "/messages/stats/filters"
        stats_trending = "/messages/stats/trending"
        health_check = "/messages/health-check"
        metrics = "/messages/metrics"
        reports_generate = "/messages/reports/generate"
    
    class Admin:
        """管理员相关路由"""
        channels = "/admin/channels"
        channels_by_name = "/admin/channels/{channel_name}"
        channels_refresh_titles = "/admin/channels/refresh-titles"
        search_channels = "/admin/search-channels"
        collect_history = "/admin/collect-history/{channel_id}"
        collect_history_progress = "/admin/collect-history/progress"
        collect_history_stop = "/admin/collect-history/{channel_id}/stop"
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
        channels_add = "/config/channels/add"
        channels_by_id = "/config/channels/{channel_id}"
        channels_status = "/config/channels/{channel_id}/status"
        channels_list = "/config/channels/"
        channels_batch_add = "/config/channels/batch-add"
    
    class System:
        """系统相关路由"""
        # 健康检查
        status = "/system/status"
        status_detailed = "/system/status/detailed"
        health = "/system/health"
        
        # 日志管理
        logs = "/system/logs"
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
        
        # 历史消息采集
        history_progress = "/system/history-collection/progress"
        history_start = "/system/history-collection/start/{channel_id}"
        history_stop = "/system/history-collection/stop/{channel_id}"
    
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