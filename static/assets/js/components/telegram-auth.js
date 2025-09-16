// Telegram 认证页面 JavaScript

// 确保API配置可用
const API = window.API;

// 检查依赖是否加载

const { createApp } = Vue;

// 认证应用组件
const AuthApp = {
        data() {
            return {
                loading: false,
                loadingMessage: '',
                statusMessage: '',
                statusType: 'success',
                authStatus: '未认证',
                currentStep: 1,
                verifying: false,
                errorMessage: '',
                config: {
                    api_id: '',
                    api_hash: '',
                    phone: ''
                },
                verificationCode: '',
                password: '',
                websocket: null,
                connected: false,
                savedAuthInfo: null,
                showSavedInfo: false,
                hasSavedSession: false
            }
        },
        
        computed: {
            canProceed() {
                return this.config.api_id && this.config.api_hash;
            }
        },
        
        async mounted() {
            // 初始化管理员认证检查
            try {
                const isAuthorized = await authManager.initPageAuth();
                if (!isAuthorized) {
                    return; // 认证失败，页面已跳转
                }
            } catch (error) {
                console.error('管理员认证失败:', error);
                window.SimpleUI.showMessage('请先登录管理员账户');
                return;
            }
            
            this.connectWebSocket();
            this.checkAuthStatus();
            this.loadSavedAuthInfo();
        },
        
        beforeUnmount() {
            this.disconnectWebSocket();
        },
        
        methods: {
            connectWebSocket() {
                try {
                    // 检查是否支持 WebSocket
                    if (!window.WebSocket) {
                        this.connected = false;
                        return;
                    }
                    
                    // Linus风格：使用统一的WebSocket工厂，消除重复代码
                    this.websocket = WebSocketFactory.create('main');
                    
                    this.websocket.onopen = () => {
                        this.connected = true;
                    };
                    
                    this.websocket.onmessage = (event) => {
                        try {
                            const data = JSON.parse(event.data);
                            this.handleWebSocketMessage(data);
                        } catch (error) {
                        }
                    };
                    
                    this.websocket.onclose = () => {
                        this.connected = false;
                    };
                    
                    this.websocket.onerror = (error) => {
                        this.connected = false;
                        // 不显示错误，静默降级到 REST API
                        // 立即尝试使用 REST API 检查状态
                        this.checkAuthStatus();
                    };
                } catch (error) {
                    this.connected = false;
                }
            },
            
            disconnectWebSocket() {
                if (this.websocket) {
                    this.websocket.close();
                    this.websocket = null;
                }
            },
            
            sendWebSocketMessage(action, data = {}) {
                if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
                    const message = {
                        action: action,
                        ...data
                    };
                    this.websocket.send(JSON.stringify(message));
                } else {
                    this.sendRestApiRequest(action, data);
                }
            },
            
            async sendRestApiRequest(action, data = {}) {
                try {
                    let url = '';
                    let method = 'POST';
                    let payload = {};
                    
                    switch (action) {
                        case 'init_auth':
                            url = API.telegramAuth.init;
                            payload = {
                                api_id: parseInt(data.api_id),
                                api_hash: data.api_hash
                            };
                            break;
                        case 'send_phone':
                            url = API.telegramAuth.sendCode;
                            payload = { phone: data.phone };
                            break;
                        case 'verify_code':
                            url = API.telegramAuth.verifyCode;
                            payload = { code: data.code };
                            break;
                        case 'verify_password':
                            url = API.telegramAuth.verifyPassword;
                            payload = { password: data.password };
                            break;
                        case 'disconnect':
                            url = API.telegramAuth.disconnect;
                            method = 'POST';
                            break;
                        default:
                            return;
                    }
                    
                    const response = await fetch(url, {
                        method: method,
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify(payload)
                    });
                    
                    const result = await response.json();
                    
                    if (response.ok) {
                        this.handleAuthStatus(result.state || 'success', result.message || '操作成功');
                        // 对于send_code成功后，清除loading状态
                        if (action === 'send_phone' && result.state === 'code_sent') {
                            this.loading = false;
                        }
                    } else {
                        this.handleError(result.detail || '操作失败');
                    }
                } catch (error) {
                    this.handleError('网络请求失败');
                }
            },
            
            handleWebSocketMessage(data) {
                
                const type = data.type;
                const state = data.state;
                const message = data.message;
                
                if (type === 'auth_status') {
                    this.handleAuthStatus(state, message);
                } else if (type === 'error') {
                    this.handleError(message);
                } else if (type === 'auth_info') {
                    this.handleAuthInfo(data.data);
                } else if (type === 'auth_cleared') {
                    this.handleAuthCleared(message);
                }
            },
            
            handleAuthStatus(state, message) {
                this.showSuccess(message);
                
                switch (state) {
                    case 'authorized':
                        this.authStatus = '已认证';
                        this.currentStep = 5;
                        break;
                    case 'idle':
                        // 初始化成功，需要输入手机号
                        this.currentStep = 2;
                        this.authStatus = '需要输入手机号';
                        break;
                    case 'phone_needed':
                        this.currentStep = 2;
                        break;
                    case 'code_sent':
                        this.currentStep = 3;
                        break;
                    case 'password_needed':
                        this.currentStep = 4;
                        break;
                    case 'disconnected':
                        this.authStatus = '未认证';
                        this.currentStep = 1;
                        this.resetForm();
                        break;
                }
            },
            
            handleError(message) {
                this.errorMessage = message;
                this.showError(message);
            },
            
            async checkAuthStatus() {
                try {
                    const response = await axios.get(API.telegramAuth.status);
                    if (response.data.authorized) {
                        this.authStatus = '已认证';
                        this.currentStep = 5;
                    } else {
                        this.authStatus = '未认证';
                    }
                } catch (error) {
                    this.authStatus = '未认证';
                }
            },
            
            async submitConfig() {
                if (this.canProceed) {
                    this.loading = true;
                    this.loadingMessage = '正在初始化认证...';
                    this.errorMessage = '';
                    
                    this.sendWebSocketMessage('init_auth', {
                        api_id: parseInt(this.config.api_id),
                        api_hash: this.config.api_hash
                    });
                    
                    // 等待一小段时间让WebSocket消息处理
                    setTimeout(() => {
                        this.loading = false;
                    }, 1000);
                }
            },
            
            nextStep() {
                if (this.canProceed) {
                    this.currentStep = 2;
                    this.sendCode();
                }
            },
            
            prevStep() {
                if (this.currentStep > 1) {
                    this.currentStep--;
                }
            },
            
            async sendCode() {
                if (!this.config.phone) {
                    this.errorMessage = '请输入手机号码';
                    return;
                }
                
                this.loading = true;
                this.loadingMessage = '正在发送验证码...';
                this.errorMessage = '';
                
                this.sendWebSocketMessage('send_phone', {
                    phone: this.config.phone
                });
            },
            
            async verifyCode() {
                if (!this.verificationCode) {
                    this.errorMessage = '请输入验证码';
                    return;
                }
                
                this.verifying = true;
                this.errorMessage = '';
                
                this.sendWebSocketMessage('verify_code', {
                    code: this.verificationCode
                });
            },
            
            async verifyPassword() {
                if (!this.password) {
                    this.errorMessage = '请输入两步验证密码';
                    return;
                }
                
                this.verifying = true;
                this.errorMessage = '';
                
                this.sendWebSocketMessage('verify_password', {
                    password: this.password
                });
            },
            
            goToMain() {
                window.location.href = '/';
            },
            
            async loadSavedAuthInfo() {
                try {
                    const response = await axios.get(API.telegramAuth.info);
                    this.handleAuthInfo(response.data);
                } catch (error) {
                }
            },
            
            handleAuthInfo(data) {
                // 创建响应式数据对象
                this.savedAuthInfo = {
                    api_id: data.api_id || '',
                    api_hash: data.api_hash || '',
                    has_saved_auth: data.has_saved_auth,
                    has_session: data.has_session
                };
                
                this.hasSavedSession = data.has_session || false;
                
                // 判断显示状态：
                // 1. 如果有session且有效 -> 显示已保存的认证信息页
                // 2. 如果session为空或无效 -> 显示步骤1（API配置页）
                if (data.has_saved_auth && data.has_session) {
                    this.authStatus = '已认证';
                    this.showSavedInfo = true;
                    this.currentStep = 5; // 设置为完成状态，但通过showSavedInfo控制显示
                } else {
                    // session为空或无效，显示步骤1
                    this.authStatus = '未认证';
                    this.showSavedInfo = false;
                    this.currentStep = 1; // 默认显示第一阶段页面（API配置）
                    
                    // 如果有保存的API凭据，自动填充到表单
                    if (data.api_id && data.api_hash) {
                        this.config.api_id = data.api_id;
                        this.config.api_hash = data.api_hash;
                    }
                }
            },
            
            handleAuthCleared(message) {
                this.showSuccess(message);
                this.savedAuthInfo = null;
                this.showSavedInfo = false;
                this.authStatus = '未认证';
                this.currentStep = 1;
                this.resetForm();
            },
            
            async clearAuthData() {
                // 二次确认
                const confirmed = await this.$confirm(
                    '此操作将永久删除所有认证数据和Session文件，是否继续？',
                    '确认清除',
                    {
                        confirmButtonText: '确定',
                        cancelButtonText: '取消',
                        type: 'warning',
                        customClass: 'starcraft-confirm'
                    }
                ).catch(() => false);
                
                if (!confirmed) {
                    return;
                }
                
                try {
                    this.loading = true;
                    this.loadingMessage = '正在清除认证数据...';
                    
                    const response = await axios.post(API.telegramAuth.clear);
                    if (response.data.success) {
                        this.handleAuthCleared(response.data.message);
                    } else {
                        this.handleError(response.data.error);
                    }
                } catch (error) {
                    this.handleError('清除认证数据失败');
                } finally {
                    this.loading = false;
                }
            },
            
            async startReAuth() {
                // 使用输入框中的新值进行认证
                if (this.savedAuthInfo && this.savedAuthInfo.api_id && this.savedAuthInfo.api_hash) {
                    this.config.api_id = this.savedAuthInfo.api_id;
                    this.config.api_hash = this.savedAuthInfo.api_hash;
                    
                    // 直接开始新的认证流程
                    this.showSavedInfo = false;
                    this.currentStep = 1;
                    this.authStatus = '重新认证';
                    this.errorMessage = '';
                    
                    window.SimpleUI.showMessage('开始重新认证流程');
                } else {
                    window.SimpleUI.showMessage('请输入 API ID 和 API Hash');
                }
            },
            
            resetForm() {
                this.config = {
                    api_id: '',
                    api_hash: '',
                    phone: ''
                };
                this.verificationCode = '';
                this.password = '';
                this.errorMessage = '';
            },
            
            showSuccess(message) {
                this.statusMessage = message;
                this.statusType = 'success';
                this.loading = false;
                this.verifying = false;
                setTimeout(() => {
                    this.statusMessage = '';
                }, 3000);
            },
            
            showError(message) {
                // 显示错误消息
                this.errorMessage = message;
                this.loading = false;
                this.verifying = false;
                window.SimpleUI.showMessage(message);
            }
        }
};

// 创建并挂载应用
document.addEventListener('DOMContentLoaded', function() {
    const app = createApp(AuthApp);
        // 注册导航栏组件
    if (window.NavBar) {
        app.component('nav-bar', window.NavBar);
    }
    app.mount('#app');
}); 