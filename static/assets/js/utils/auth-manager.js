/**
 * 认证管理器 - 统一处理页面认证
 */

class AuthManager {
    constructor() {
        this.apiBaseUrl = '/api';
        this.redirectTimeout = 2000;
    }

    /**
     * 初始化页面认证
     * @param {string} authType - 认证类型 ('admin' | 'telegram.sender.auth' | 'telegram.listener.auth' | 'telegram.dual.auth')
     * @returns {Promise<boolean>} - 是否认证成功
     */
    async initPageAuth(authType = 'admin') {
        try {
            switch (authType) {
                case 'admin':
                    return await this.checkAdminAuth();
                case 'telegram.sender.auth':
                case 'telegram.listener.auth':
                case 'telegram.dual.auth':
                    return await this.checkTelegramAuth(authType);
                default:
                    console.warn('未知的认证类型:', authType);
                    return true;
            }
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
     * 检查Telegram认证状态
     * @param {string} authType 
     */
    async checkTelegramAuth(authType) {
        try {
            // 首先检查管理员认证
            const adminAuthed = await this.checkAdminAuth();
            if (!adminAuthed) {
                return false;
            }

            // 然后检查Telegram认证状态
            const sessionType = this.getSessionTypeFromAuthType(authType);
            const response = await axios.get(`${this.apiBaseUrl}/dual-auth/session-status/${sessionType}`, {
                headers: {
                    'Authorization': `Bearer ${this.getAuthToken()}`
                }
            });

            if (response.data && response.data.success && response.data.status.state === 'authorized') {
                return true;
            } else {
                // Telegram未认证，跳转到认证页面
                this.redirectToTelegramAuth(authType);
                return false;
            }
        } catch (error) {
            console.error('Telegram认证检查失败:', error);
            this.redirectToTelegramAuth(authType);
            return false;
        }
    }

    /**
     * 从认证类型获取Session类型
     */
    getSessionTypeFromAuthType(authType) {
        if (authType.includes('sender')) return 'sender';
        if (authType.includes('listener')) return 'listener';
        return 'sender'; // 默认
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
     * 跳转到Telegram认证页面
     */
    redirectToTelegramAuth(authType) {
        if (window.SimpleUI) {
            window.SimpleUI.showMessage('请先完成Telegram认证', 'warning');
        }
        
        let hash = '';
        if (authType === 'telegram.sender.auth') hash = '#sender';
        else if (authType === 'telegram.listener.auth') hash = '#listener';
        
        setTimeout(() => {
            window.location.href = `/static/telegram-auth.html${hash}`;
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