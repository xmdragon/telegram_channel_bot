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
        resend = "/messages/resend/{message_id}"
        
        # 过滤器操作
        filter_content = "/messages/filter-content/{message_id}"
        train_tail = "/messages/train-tail/{message_id}"
        not_ad = "/messages/not-ad/{message_id}"
        refetch_media = "/messages/refetch-media/{message_id}"
        refilter = "/messages/refilter/{message_id}"
        feedback = "/messages/feedback/{message_id}"
        delete_review = "/messages/delete-review/{message_id}"
        
        # 批量操作
        batch_approve = "/messages/batch/approve"
        batch_reject = "/messages/batch/reject"
        batch_delete = "/messages/batch/delete"
        batch_refetch_media = "/messages/batch/refetch-media"
        
        
        # 统计相关
        stats_overview = "/messages/stats/overview"
    
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
        lock_status = "/system/lock-status"
        clear_lock = "/system/clear-lock"
        auto_clear_lock = "/system/auto-clear-lock"
        # 其他系统路由
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
    
    class AI:
        """AI功能控制路由"""
        status = "/ai/status"
        enable = "/ai/enable"
        disable = "/ai/disable"
        config = "/ai/config"
        module_config = "/ai/module-config"
        cache_info = "/ai/cache/info"
        cache_preload = "/ai/cache/preload"
        cache_clear = "/ai/cache/clear"
        lightweight_train = "/ai/lightweight-train"
        recommendations = "/ai/recommendations"
    
    class Training:
        """训练数据管理路由"""
        # 广告样本
        ad_samples = "/training/ad-samples"
        ad_statistics = "/training/ad-statistics"
        ad_samples_by_id = "/training/ad-samples/{sample_id}"
        ad_samples_batch = "/training/ad-samples/batch"
        ad_samples_detect_duplicates = "/training/ad-samples/detect-duplicates"
        ad_samples_deduplicate = "/training/ad-samples/deduplicate"
        mark_ad_test = "/training/mark-ad-test"
        mark_ad_message = "/training/mark-ad-message"
        add_ad_sample = "/training/add-ad-sample"
        ad_stats = "/training/ad-stats"
        ad_samples_reload = "/training/ad-samples/reload"
        
        # 基础训练
        channels = "/training/channels"
        stats = "/training/stats"
        history = "/training/history"
        submit = "/training/submit"
        sample_by_id = "/training/{sample_id}"
        apply = "/training/apply"
        clear_by_channel = "/training/clear/{channel_id}"
        export = "/training/export"
        auto_learn = "/training/auto-learn/{channel_id}"
        sample_detail = "/training/sample/{sample_id}"
        separator_patterns = "/training/separator-patterns"
        reload_model = "/training/reload-model"
        
        # OCR样本
        ocr_samples = "/training/ocr-samples"
        ocr_statistics = "/training/ocr-samples/statistics"
        ocr_learn = "/training/ocr-samples/learn"
        ocr_samples_by_id = "/training/ocr-samples/{sample_id}"
        ocr_export = "/training/ocr-samples/export"
        ocr_add = "/training/ocr-samples/add"
        ocr_batch_process = "/training/ocr-samples/batch-process"
        ocr_confidence_distribution = "/training/ocr-samples/confidence-distribution"
        
        # 管理功能
        optimize_storage = "/training/optimize-storage"
        optimize_storage_sse = "/training/optimize-storage-sse"
        learning_stats = "/training/learning-stats"
        emergency_backup = "/training/emergency-backup"
        integrity_report = "/training/integrity-report"
        verify_integrity = "/training/verify-integrity"
        cleanup_backups = "/training/cleanup-backups"
        backups = "/training/backups"
        restore = "/training/restore/{backup_filename}"
        feedback = "/training/feedback"
        statistics = "/training/statistics"
        clear = "/training/clear"
        
        # 尾部过滤器
        tail_filter_statistics = "/training/tail-filter-statistics"
        tail_filter_history = "/training/tail-filter-history"
        tail_filter_samples = "/training/tail-filter-samples"
        tail_filter_samples_by_id = "/training/tail-filter-samples/{sample_id}"
        tail_filter_detect_duplicates = "/training/tail-filter-samples/detect-duplicates"
        tail_filter_deduplicate = "/training/tail-filter-samples/deduplicate"
        tail_filter_rebuild_vectors = "/training/tail-filter-rebuild-vectors"
        
        # 阈值管理
        thresholds_stats = "/training/thresholds/stats"
        thresholds_optimize = "/training/thresholds/optimize"
        thresholds_reset = "/training/thresholds/{filter_name}/{metric_name}/reset"
        
        # 媒体文件
        media_files = "/training/media-files"
        media_files_clean_orphaned = "/training/media-files/clean-orphaned"
        media_files_duplicates = "/training/media-files/duplicates"
        media_files_export = "/training/media-files/export"
        media_files_deduplicate = "/training/media-files/deduplicate"
        media_files_rebuild_visual_hashes = "/training/media-files/rebuild-visual-hashes"
        media_files_ocr = "/training/media-files/ocr/{file_hash}"
        media_files_by_hash = "/training/media-files/{file_hash}"
        
        # 推广链接训练
        promo_samples = "/training/promo-samples"
        promo_samples_by_id = "/training/promo-samples/{sample_id}"
        preview_promo_filter = "/training/preview-promo-filter"
    
    def __init__(self):
        self.messages = self.Messages()
        self.admin = self.Admin()
        self.admin_auth = self.AdminAuth()
        self.auth = self.Auth()
        self.config = self.Config()
        self.system = self.System()
        self.channel_resolver = self.ChannelResolver()
        self.lock = self.Lock()
        self.ai = self.AI()
        self.training = self.Training()

# 全局路由配置实例
ROUTES = RouteConfig()