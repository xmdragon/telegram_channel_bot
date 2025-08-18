/**
 * 登录页面JavaScript逻辑
 * 从login.html分离的独立脚本文件
 */

// 确保API配置可用
const API = window.API;

const { createApp } = Vue;
const { ElMessage } = ElementPlus;
const { User, Lock } = ElementPlusIconsVue;

const LoginApp = {
    data() {
        return {
            loginData: {
                username: '',
                password: ''
            },
            rules: {
                username: [
                    { required: true, message: '请输入用户名', trigger: 'blur' },
                    { min: 2, max: 20, message: '用户名长度在 2 到 20 个字符', trigger: 'blur' }
                ],
                password: [
                    { required: true, message: '请输入密码', trigger: 'blur' },
                    { min: 6, message: '密码长度至少 6 个字符', trigger: 'blur' }
                ]
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
        
        async handleLogin() {
            this.$refs.loginForm.validate(async (valid) => {
                if (!valid) return;
                
                this.loading = true;
                this.errorMessage = '';
                
                try {
                    const response = await axios.post(API.adminAuth.login, this.loginData);
                    
                    if (response.data.success) {
                        // 保存token和用户信息
                        localStorage.setItem('admin_token', response.data.token);
                        localStorage.setItem('admin_info', JSON.stringify(response.data.admin));
                        
                        ElMessage({
                            message: '登录成功',
                            type: 'success',
                            duration: 1500
                        });
                        
                        // 跳转到首页
                        setTimeout(() => {
                            this.redirectToHome();
                        }, 500);
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
            });
        },
        
        redirectToHome() {
            // 检查是否有返回URL
            const urlParams = new URLSearchParams(window.location.search);
            const returnUrl = urlParams.get('return') || './index.html';
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
document.addEventListener('DOMContentLoaded', function() {
    const app = createApp(LoginApp);
    app.use(ElementPlus);
    
    // 注册图标
    for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
        app.component(key, component);
    }
    
    app.mount('#app');
});