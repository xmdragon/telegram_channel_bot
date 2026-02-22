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
     * 获取token
     */
    getToken() {
        return this.token;
    }
    
    /**
     * 检查是否已登录
     */
    isAuthenticated() {
        return !!this.token && !!this.adminInfo;
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
     * 验证认证状态 - 优化版本，优先使用本地缓存
     */
    async verifyAuth() {
        if (!this.token) {
            this.redirectToLogin();
            return false;
        }
        
        // 🚀 检查本地缓存的权限信息
        const cachedTimestamp = localStorage.getItem('auth_timestamp');
        const cacheAge = Date.now() - parseInt(cachedTimestamp || '0');
        
        // 缓存有效期5分钟（300,000毫秒）
        if (cacheAge < 5 * 60 * 1000 && this.adminInfo) {
            return true;  // 直接使用缓存，避免API请求
        }
        
        // 缓存过期或不存在，发送API请求
        try {
            const response = await axios.get(
                API.adminAuth.current,
                { headers: this.getAuthHeaders() }
            );
            
            // 更新本地存储的管理员信息和时间戳
            localStorage.setItem('admin_info', JSON.stringify(response.data));
            localStorage.setItem('auth_timestamp', Date.now().toString());
            
            // 如果响应包含权限信息，也缓存起来
            
            this.adminInfo = response.data;
            return true;
        } catch (error) {
            // 401是认证失败，404可能是服务未启动或路径错误
            if (error.response && (error.response.status === 401 || error.response.status === 404)) {
                // Token无效或API不可用
                this.logout();
                this.redirectToLogin();
                return false;
            }
            console.error('权限验证失败:', error);
            return false;
        }
    }
    
    /**
     * 登出
     */
    async logout() {
        if (this.token) {
            try {
                // 携带认证头发送登出请求
                await axios.post(API.adminAuth.logout, {}, {
                    headers: {
                        'Authorization': `Bearer ${this.token}`
                    }
                });
            } catch (e) {
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
            if (typeof window.SimpleUI !== 'undefined' && window.SimpleUI.showMessage) {
                window.SimpleUI.showMessage('您没有权限执行此操作', 'error');
            } else {
                alert('您没有权限执行此操作');
            }
            return true;
        }
        return false;
    }
    
    /**
     * 初始化页面认证检查 - 带超时处理
     */
    async initPageAuth() {
        try {
            // 开始页面加载超时检测
            if (typeof window.AxiosConfig !== 'undefined' && window.AxiosConfig.startPageLoadTimeout) {
                window.AxiosConfig.startPageLoadTimeout();
            }

            // 验证登录状态
            const isValid = await this.verifyAuth();
            if (!isValid) {
                return false;
            }

            // 配置axios
            this.configureAxios();

            // 清除页面加载超时检测
            if (typeof window.AxiosConfig !== 'undefined' && window.AxiosConfig.clearPageLoadTimeout) {
                window.AxiosConfig.clearPageLoadTimeout();
            }

            return true;
        } catch (error) {
            console.error('页面认证检查失败:', error);

            // 清除页面加载超时检测
            if (typeof window.AxiosConfig !== 'undefined' && window.AxiosConfig.clearPageLoadTimeout) {
                window.AxiosConfig.clearPageLoadTimeout();
            }

            // 如果是认证相关错误（401或404），直接跳转到登录页
            if (error.response && (error.response.status === 401 || error.response.status === 404)) {
                this.redirectToLogin();
                return false;
            }

            // 显示错误信息并提供重试
            if (typeof window.SimpleUI !== 'undefined' && window.SimpleUI.showMessage) {
                window.SimpleUI.showMessage('认证检查失败，请刷新页面重试', 'error', 8000);
            }

            // 3秒后提供刷新按钮
            setTimeout(() => {
                this.addRetryButton();
            }, 3000);

            return false;
        }
    }
    
    /**
     * 后台静默刷新认证
     */
    async refreshAuthSilently() {
        if (!this.token) return false;
        
        try {
            const response = await axios.get(
                API.adminAuth.current,
                { headers: this.getAuthHeaders() }
            );
            
            // 静默更新缓存
            localStorage.setItem('admin_info', JSON.stringify(response.data));
            localStorage.setItem('auth_timestamp', Date.now().toString());
            
            
            this.adminInfo = response.data;
            return true;
        } catch (error) {
            // 401是认证失败，404可能是服务未启动或API路径错误
            if (error.response?.status === 401 || error.response?.status === 404) {
                this.logout();
                return false;
            }
            console.error('后台刷新认证失败:', error);
            return false;
        }
    }

    /**
     * 添加重试按钮
     */
    addRetryButton() {
        const existingButton = document.getElementById('auth-retry-button');
        if (existingButton) return;
        
        const button = document.createElement('button');
        button.id = 'auth-retry-button';
        button.innerHTML = '🔄 重试认证';
        button.style.cssText = `
            position: fixed;
            top: 60px;
            right: 20px;
            z-index: 10001;
            padding: 8px 16px;
            background: #67c23a;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 13px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.2);
        `;
        
        button.addEventListener('click', async () => {
            button.textContent = '重试中...';
            button.disabled = true;
            
            try {
                const isValid = await this.initPageAuth();
                if (isValid) {
                    button.remove();
                    window.location.reload();
                }
            } catch (e) {
                button.textContent = '🔄 重试认证';
                button.disabled = false;
            }
        });
        
        document.body.appendChild(button);
    }
}

// 创建全局实例
const authManager = new AuthManager();

// 暴露到全局作用域
window.authManager = authManager;

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

/**
 * 获取认证Token的全局函数
 * 兼容不同的Token获取方式
 */
function getAuthToken() {
    // 优先使用admin_token
    let token = localStorage.getItem('admin_token');
    if (token) {
        return token;
    }
    
    // 降级使用auth_token
    token = localStorage.getItem('auth_token');
    if (token) {
        return token;
    }
    
    // 如果都没有，返回null
    return null;
}

// 导出为全局函数
window.getAuthToken = getAuthToken;

// ⚡ 启动后台认证刷新机制 - 每5分钟静默刷新一次
if (typeof window !== 'undefined') {
    // 避免重复启动定时器
    if (!window.authRefreshTimer) {
        window.authRefreshTimer = setInterval(() => {
            if (authManager.isAuthenticated()) {
                authManager.refreshAuthSilently();
            }
        }, 5 * 60 * 1000); // 5分钟 = 300,000毫秒
    }
}