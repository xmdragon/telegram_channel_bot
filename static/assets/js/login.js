/**
 * 登录页面JavaScript逻辑
 * 从login.html分离的独立脚本文件
 */

// 确保API配置可用
const API = window.API;

const { createApp } = Vue;

const LoginApp = {
    data() {
        return {
            loginData: {
                username: '',
                password: ''
            },
            loading: false,
            errorMessage: ''
        };
    },
    
    mounted() {
        // 检查是否已登录
        this.checkAuth();
    },
    
    methods: {
        async checkAuth() {
            const token = localStorage.getItem('admin_token');
            if (token) {
                try {
                    const response = await axios.get(API.adminAuth.checkAuth, {
                        headers: {
                            'Authorization': `Bearer ${token}`
                        }
                    });
                    
                    if (response.data.authenticated) {
                        // 已登录，跳转到首页
                        this.redirectToHome();
                    }
                } catch (error) {
                    // Token无效，清除
                    localStorage.removeItem('admin_token');
                }
            }
        },
        
        validateForm() {
            if (!this.loginData.username.trim()) {
                this.errorMessage = '请输入用户名';
                return false;
            }
            if (this.loginData.username.length < 2 || this.loginData.username.length > 20) {
                this.errorMessage = '用户名长度在 2 到 20 个字符';
                return false;
            }
            if (!this.loginData.password.trim()) {
                this.errorMessage = '请输入密码';
                return false;
            }
            if (this.loginData.password.length < 6) {
                this.errorMessage = '密码长度至少 6 个字符';
                return false;
            }
            return true;
        },
        
        async handleLogin() {
            if (!this.validateForm()) return;
            
            this.loading = true;
            this.errorMessage = '';
            
            try {
                const response = await axios.post(API.adminAuth.login, this.loginData);
                if (response.data && response.data.success) {
                    // 保存token和用户信息
                    localStorage.setItem('admin_token', response.data.token);
                    localStorage.setItem('admin_info', JSON.stringify(response.data.admin));
                    
                    // 🚀 缓存权限信息和时间戳 - 避免每个页面重复验证权限
                    if (response.data.admin.permissions) {
                        localStorage.setItem('admin_permissions', JSON.stringify(response.data.admin.permissions));
                    }
                    localStorage.setItem('auth_timestamp', Date.now().toString());
                    
                    // 使用SimpleUI显示成功消息
                    if (window.SimpleMessage) {
                        window.SimpleMessage.success('登录成功');
                    }
                    
                    // 立即跳转，不用setTimeout
                    this.redirectToHome();
                } else {
                    console.error('登录响应异常:', response.data);
                    this.errorMessage = '登录响应异常';
                }
            } catch (error) {
                if (error.response && error.response.status === 401) {
                    this.errorMessage = '用户名或密码错误';
                } else {
                    this.errorMessage = error.response?.data?.detail || '登录失败，请稍后重试';
                }
                
                // 清空密码
                this.loginData.password = '';
            } finally {
                this.loading = false;
            }
        },
        
        redirectToHome() {
            // 检查是否有返回URL
            const urlParams = new URLSearchParams(window.location.search);
            const returnUrl = urlParams.get('return') || '/static/index.html';
            
            
            // 使用绝对路径跳转
            window.location.href = returnUrl;
        },
        
        handleKeyPress(event) {
            if (event.key === 'Enter') {
                this.handleLogin();
            }
        }
    }
};

// 页面加载完成后初始化Vue应用
window.addEventListener('load', function() {
    const app = createApp(LoginApp);
    app.mount('#app');
});