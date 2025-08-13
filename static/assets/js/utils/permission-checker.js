/**
 * 权限检查工具类
 * 用于前端权限控制
 */
class PermissionChecker {
    constructor() {
        this.permissions = new Set();
        this.isSuperAdmin = false;
        this.isInitialized = false;
    }
    
    /**
     * 初始化权限信息
     * @param {Object} adminInfo - 管理员信息对象
     */
    async initialize(adminInfo) {
        if (!adminInfo) {
            // 尝试从API获取当前用户信息
            try {
                const response = await axios.get('/api/admin/auth/current');
                adminInfo = response.data;
            } catch (error) {
                // 获取用户权限信息失败
                this.permissions.clear();
                this.isSuperAdmin = false;
                this.isInitialized = false;
                return false;
            }
        }
        
        // 设置权限信息
        this.permissions = new Set(adminInfo.permissions || []);
        this.isSuperAdmin = adminInfo.is_super_admin || false;
        this.isInitialized = true;
        
        // 权限初始化完成
        
        return true;
    }
    
    /**
     * 检查是否有指定权限
     * @param {string} permission - 权限名称
     * @returns {boolean}
     */
    hasPermission(permission) {
        // 超级管理员拥有所有权限
        if (this.isSuperAdmin) {
            return true;
        }
        
        // 检查具体权限
        return this.permissions.has(permission);
    }
    
    /**
     * 检查是否有多个权限中的任意一个
     * @param {Array<string>} permissions - 权限列表
     * @returns {boolean}
     */
    hasAnyPermission(permissions) {
        if (this.isSuperAdmin) {
            return true;
        }
        
        return permissions.some(perm => this.permissions.has(perm));
    }
    
    /**
     * 检查是否有所有指定权限
     * @param {Array<string>} permissions - 权限列表
     * @returns {boolean}
     */
    hasAllPermissions(permissions) {
        if (this.isSuperAdmin) {
            return true;
        }
        
        return permissions.every(perm => this.permissions.has(perm));
    }
    
    // ========== 具体功能权限检查方法 ==========
    
    /**
     * 是否可以查看消息
     */
    canViewMessages() {
        return this.hasPermission('messages.view');
    }
    
    /**
     * 是否可以编辑消息
     */
    canEditMessage() {
        return this.hasPermission('messages.edit');
    }
    
    /**
     * 是否可以批准消息
     */
    canApproveMessage() {
        return this.hasPermission('messages.approve');
    }
    
    /**
     * 是否可以拒绝消息
     */
    canRejectMessage() {
        return this.hasPermission('messages.reject');
    }
    
    /**
     * 是否可以删除消息
     */
    canDeleteMessage() {
        return this.hasPermission('messages.delete');
    }
    
    /**
     * 是否可以标记为广告
     */
    canMarkAsAd() {
        return this.hasPermission('training.mark_ad') || 
               this.hasPermission('training.submit'); // 兼容旧权限
    }
    
    /**
     * 是否可以标记尾部内容
     */
    canMarkAsTail() {
        return this.hasPermission('training.mark_tail') || 
               this.hasPermission('training.submit'); // 兼容旧权限
    }
    
    /**
     * 是否可以执行过滤操作
     */
    canExecuteFilter() {
        return this.hasPermission('filter.execute');
    }
    
    /**
     * 是否可以添加过滤关键词
     */
    canAddFilterKeyword() {
        return this.hasPermission('filter.add_keyword') || 
               this.hasPermission('config.edit'); // 兼容旧权限
    }
    
    /**
     * 是否可以补抓媒体
     */
    canRefetchMedia() {
        return this.hasPermission('channels.refetch') || 
               this.hasPermission('channels.edit'); // 兼容旧权限
    }
    
    /**
     * 是否可以管理频道
     */
    canManageChannels() {
        return this.hasAnyPermission([
            'channels.add',
            'channels.edit',
            'channels.delete'
        ]);
    }
    
    /**
     * 是否可以查看配置
     */
    canViewConfig() {
        return this.hasPermission('config.view');
    }
    
    /**
     * 是否可以修改配置
     */
    canEditConfig() {
        return this.hasPermission('config.edit');
    }
    
    /**
     * 是否可以查看系统状态
     */
    canViewSystemStatus() {
        return this.hasPermission('system.view_status');
    }
    
    /**
     * 是否可以重启系统
     */
    canRestartSystem() {
        return this.hasPermission('system.restart');
    }
    
    /**
     * 是否可以管理用户
     */
    canManageUsers() {
        return this.hasPermission('admin.manage_users');
    }
    
    /**
     * 获取当前用户的权限列表
     */
    getPermissions() {
        return Array.from(this.permissions);
    }
    
    /**
     * 获取按钮显示配置
     * @returns {Object} 按钮显示状态
     */
    getButtonVisibility() {
        return {
            edit: this.canEditMessage(),
            approve: this.canApproveMessage(),
            reject: this.canRejectMessage(),
            markAsAd: this.canMarkAsAd(),
            markAsTail: this.canMarkAsTail(),
            executeFilter: this.canExecuteFilter(),
            refetchMedia: this.canRefetchMedia(),
            delete: this.canDeleteMessage()
        };
    }
    
    /**
     * 根据权限过滤操作按钮
     * @param {Array} buttons - 按钮配置数组
     * @returns {Array} 过滤后的按钮数组
     */
    filterButtons(buttons) {
        const visibility = this.getButtonVisibility();
        return buttons.filter(button => {
            // 根据按钮类型检查权限
            switch(button.action) {
                case 'edit':
                    return visibility.edit;
                case 'approve':
                    return visibility.approve;
                case 'reject':
                    return visibility.reject;
                case 'markAsAd':
                    return visibility.markAsAd;
                case 'markAsTail':
                    return visibility.markAsTail;
                case 'filter':
                case 'executeFilter':
                    return visibility.executeFilter;
                case 'refetch':
                case 'refetchMedia':
                    return visibility.refetchMedia;
                case 'delete':
                    return visibility.delete;
                default:
                    return true; // 默认显示
            }
        });
    }
}

// 创建全局权限检查器实例
window.permissionChecker = new PermissionChecker();

// 导出类供其他模块使用
if (typeof module !== 'undefined' && module.exports) {
    module.exports = PermissionChecker;
}