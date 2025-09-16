/**
 * 认证管理器 - 统一处理页面认证
 */

class AuthManager {
    constructor() {
        this.apiBaseUrl = '/api';
        this.redirectTimeout = 2000;
    }

    /**
     * 初始化页面认证 - 检查管理员登录状态
     * @returns {Promise<boolean>} - 是否认证成功
     */
    async initPageAuth() {
        try {
            return await this.checkAdminAuth();
        } catch (error) {
            console.error('认证检查失败:', error);
            return false;
        }
    }

    /**
     * 检查管理员认证
     */
    async checkAdminAuth() {
        try {
            const token = this.getAuthToken();
            if (!token) {
                this.redirectToLogin();
                return false;
            }

            const response = await axios.get(`${this.apiBaseUrl}/admin/auth/check-auth`, {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });

            if (response.data && response.data.authenticated) {
                return true;
            } else {
                this.clearAuthToken();
                this.redirectToLogin();
                return false;
            }
        } catch (error) {
            console.error('管理员认证检查失败:', error);
            this.clearAuthToken();
            this.redirectToLogin();
            return false;
        }
    }


    /**
     * 获取认证Token
     */
    getAuthToken() {
        return localStorage.getItem('admin_token') || sessionStorage.getItem('admin_token');
    }

    /**
     * 清除认证Token
     */
    clearAuthToken() {
        localStorage.removeItem('admin_token');
        sessionStorage.removeItem('admin_token');
    }

    /**
     * 跳转到登录页面
     */
    redirectToLogin() {
        if (window.SimpleUI) {
            window.SimpleUI.showMessage('请先登录管理员账户', 'warning');
        }
        setTimeout(() => {
            window.location.href = '/static/login.html';
        }, this.redirectTimeout);
    }

    /**
     * 设置认证Token
     */
    setAuthToken(token, remember = false) {
        if (remember) {
            localStorage.setItem('admin_token', token);
        } else {
            sessionStorage.setItem('admin_token', token);
        }
    }

    /**
     * 获取当前用户信息
     */
    async getCurrentUser() {
        try {
            const token = this.getAuthToken();
            if (!token) return null;

            const response = await axios.get(`${this.apiBaseUrl}/admin/auth/me`, {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });

            return response.data.success ? response.data.data : null;
        } catch (error) {
            console.error('获取用户信息失败:', error);
            return null;
        }
    }

    /**
     * 登出
     */
    async logout() {
        try {
            const token = this.getAuthToken();
            if (token) {
                await axios.post(`${this.apiBaseUrl}/admin/auth/logout`, {}, {
                    headers: {
                        'Authorization': `Bearer ${token}`
                    }
                });
            }
        } catch (error) {
            console.error('登出请求失败:', error);
        } finally {
            this.clearAuthToken();
            window.location.href = '/static/login.html';
        }
    }
}

// 全局实例
window.authManager = new AuthManager();