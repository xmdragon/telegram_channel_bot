"""
API路由配置
统一管理所有API端点路径，禁止硬编码路由
"""

class ROUTES:
    """API路由统一配置类"""
    
    class system:
        """系统模块路由"""
        # 健康检查
        status = "/system/status"
        status_detailed = "/system/status/detailed"
        health = "/system/health"
        
        # 服务管理
        service_start = "/system/services/{service_name}/start"
        service_stop = "/system/services/{service_name}/stop"
        service_restart = "/system/services/{service_name}/restart"
        service_status = "/system/services/{service_name}/status"
        services = "/system/services"
        
        # 监控相关
        logs_realtime = "/system/logs/realtime"
        
        # 维护操作
        restart = "/system/restart"
        reset = "/system/reset"
        
        # 日志管理
        logs = "/system/logs"
    
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
        login = "/admin/auth/login"
        logout = "/admin/auth/logout"
        current = "/admin/auth/current"
        change_password = "/admin/auth/change-password"
        check_auth = "/admin/auth/check-auth"
        admins = "/admin/auth/admins"
        admin_by_id = "/admin/auth/admins/{admin_id}"
        permissions = "/admin/auth/permissions"
        sessions = "/admin/auth/sessions"
        session_by_token = "/admin/auth/sessions/{token}"
        me = "/admin/auth/me"
        permissions_me = "/admin/auth/permissions/me"
        
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