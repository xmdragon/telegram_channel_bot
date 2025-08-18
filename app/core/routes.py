"""
API路由配置
统一管理所有API端点路径，禁止硬编码路由
"""

class ROUTES:
    """API路由统一配置类"""
    
    class system:
        """系统模块路由"""
        # 健康检查
        status = "/status"
        status_detailed = "/status/detailed"
        health = "/health"
        
        # 服务管理
        service_start = "/services/{service_name}/start"
        service_stop = "/services/{service_name}/stop"
        service_restart = "/services/{service_name}/restart"
        service_status = "/services/{service_name}/status"
        services = "/services"
        
        # 监控相关
        history_progress = "/history-collection/progress"
        history_start = "/history-collection/start/{channel_id}"
        history_stop = "/history-collection/stop/{channel_id}"
        logs_realtime = "/logs/realtime"
        
        # 维护操作
        restart = "/restart"
        reset = "/reset"
        
        # 日志管理
        logs = "/logs"
    
    class messages:
        """消息模块路由（示例，根据需要扩展）"""
        list = "/messages/"
        detail = "/messages/{message_id}"
        batch_approve = "/messages/batch-approve"
        batch_reject = "/messages/batch-reject"
        
    class admin:
        """管理员模块路由"""
        login = "/admin/login"
        logout = "/admin/logout"
        profile = "/admin/profile"
        restart = "/admin/restart"
        backup = "/admin/backup"
        clear_cache = "/admin/clear-cache"
        export_logs = "/admin/export-logs"
        health = "/admin/health"
    
    class admin_auth:
        """管理员认证模块路由"""
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
        
    class config:
        """配置模块路由（示例，根据需要扩展）"""
        get = "/config"
        update = "/config"
        
    class training:
        """训练数据模块路由（示例，根据需要扩展）"""
        ad_samples = "/training-db/ad-samples"
        normal_samples = "/training-db/normal-samples"
        
    class channel_resolver:
        """频道解析模块路由"""
        resolve = "/resolve"
        resolve_all = "/resolve-all"
        resolve_target = "/resolve-target"
        resolve_review = "/resolve-review"
        
    class lock:
        """进程锁模块路由"""
        status = "/lock/status"
        force_release = "/lock/force-release"
    
    class ai:
        """AI配置模块路由"""
        status = "/ai-config/status"
        config = "/ai-config/global-config"
        module_config = "/ai-config/module-config"
        cache_clear = "/ai-config/cache/clear"
        lightweight_train = "/ai-config/lightweight/train"
        recommendations = "/ai-config/recommendations"