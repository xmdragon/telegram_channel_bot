/**
 * 管理员认证工具
 */

class AuthManager {
    constructor() {
        this.token = localStorage.getItem('admin_token');
        this.adminInfo = this.getAdminInfo();
    }
    
    /**
     * 获取管理员信息
     */
    getAdminInfo() {
        const infoStr = localStorage.getItem('admin_info');
        if (infoStr) {
            try {
                return JSON.parse(infoStr);
            } catch (e) {
                return null;
            }
        }
        return null;
    }
    
    /**
     * 检查是否已登录
     */
    isAuthenticated() {
        return !!this.token && !!this.adminInfo;
    }
    
    /**
     * 检查是否有指定权限
     */
    hasPermission(permission) {
        if (!this.adminInfo) return false;
        if (this.adminInfo.is_super_admin) return true;
        return this.adminInfo.permissions && this.adminInfo.permissions.includes(permission);
    }
    
    /**
     * 检查多个权限（满足其一即可）
     */
    hasAnyPermission(permissions) {
        if (!Array.isArray(permissions)) {
            permissions = [permissions];
        }
        return permissions.some(p => this.hasPermission(p));
    }
    
    /**
     * 检查多个权限（必须全部满足）
     */
    hasAllPermissions(permissions) {
        if (!Array.isArray(permissions)) {
            permissions = [permissions];
        }
        return permissions.every(p => this.hasPermission(p));
    }
    
    /**
     * 获取带认证的请求头
     */
    getAuthHeaders() {
        if (this.token) {
            return {
                'Authorization': `Bearer ${this.token}`
            };
        }
        return {};
    }
    
    /**
     * 配置axios默认请求头
     */
    configureAxios() {
        if (typeof axios !== 'undefined' && this.token) {
            axios.defaults.headers.common['Authorization'] = `Bearer ${this.token}`;
        }
    }
    
    /**
     * 验证认证状态
     */
    async verifyAuth() {
        if (!this.token) {
            this.redirectToLogin();
            return false;
        }
        
        try {
            const response = await axios.get('/api/admin/auth/current');
            // 更新本地存储的管理员信息
            localStorage.setItem('admin_info', JSON.stringify(response.data));
            this.adminInfo = response.data;
            return true;
        } catch (error) {
            if (error.response && error.response.status === 401) {
                // Token无效
                this.logout();
                this.redirectToLogin();
                return false;
            }
            console.error('验证认证失败:', error);
            return false;
        }
    }
    
    /**
     * 登出
     */
    async logout() {
        if (this.token) {
            try {
                await axios.post('/api/admin/auth/logout');
            } catch (e) {
                // 忽略错误
            }
        }
        
        localStorage.removeItem('admin_token');
        localStorage.removeItem('admin_info');
        this.token = null;
        this.adminInfo = null;
        
        // 清除axios默认请求头
        if (typeof axios !== 'undefined') {
            delete axios.defaults.headers.common['Authorization'];
        }
    }
    
    /**
     * 重定向到登录页
     */
    redirectToLogin() {
        const currentUrl = window.location.pathname + window.location.search;
        window.location.href = `/static/login.html?return=${encodeURIComponent(currentUrl)}`;
    }
    
    /**
     * 处理API错误
     */
    handleApiError(error) {
        if (error.response && error.response.status === 401) {
            // 未认证
            this.logout();
            this.redirectToLogin();
            return true;
        } else if (error.response && error.response.status === 403) {
            // 无权限
            if (typeof ElementPlus !== 'undefined') {
                ElementPlus.ElMessage.error('您没有权限执行此操作');
            } else {
                alert('您没有权限执行此操作');
            }
            return true;
        }
        return false;
    }
    
    /**
     * 初始化页面权限检查
     */
    async initPageAuth(requiredPermission = null) {
        // 验证登录状态
        const isValid = await this.verifyAuth();
        if (!isValid) {
            return false;
        }
        
        // 检查特定权限
        if (requiredPermission && !this.hasPermission(requiredPermission)) {
            if (typeof ElementPlus !== 'undefined') {
                ElementPlus.ElMessage.error('您没有权限访问此页面');
            } else {
                alert('您没有权限访问此页面');
            }
            setTimeout(() => {
                window.location.href = '/';
            }, 1500);
            return false;
        }
        
        // 配置axios
        this.configureAxios();
        
        return true;
    }
}

// 创建全局实例
const authManager = new AuthManager();

// 配置axios拦截器
if (typeof axios !== 'undefined') {
    // 请求拦截器
    axios.interceptors.request.use(
        config => {
            // 添加认证头
            const headers = authManager.getAuthHeaders();
            Object.assign(config.headers, headers);
            return config;
        },
        error => {
            return Promise.reject(error);
        }
    );
    
    // 响应拦截器
    axios.interceptors.response.use(
        response => response,
        error => {
            // 处理认证错误
            if (authManager.handleApiError(error)) {
                return Promise.reject(error);
            }
            return Promise.reject(error);
        }
    );
}