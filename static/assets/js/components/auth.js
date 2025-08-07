// Telegram 认证页面 JavaScript

// 检查依赖是否加载
console.log('Vue loaded:', typeof Vue !== 'undefined');
console.log('ElementPlus loaded:', typeof ElementPlus !== 'undefined');
console.log('Axios loaded:', typeof axios !== 'undefined');

const { createApp } = Vue;
const { ElMessage } = ElementPlus;

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
                showSavedInfo: false
            }
        },
        
        computed: {
            canProceed() {
                return this.config.api_id && this.config.api_hash;
            }
        },
        
        mounted() {
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
                        console.warn('浏览器不支持 WebSocket，将使用 REST API');
                        this.connected = false;
                        return;
                    }
                    
                    // 根据当前协议选择WebSocket协议
                    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                    const wsUrl = `${protocol}//${window.location.host}/api/auth/ws/auth`;
                    console.log('尝试连接 WebSocket:', wsUrl);
                    
                    this.websocket = new WebSocket(wsUrl);
                    
                    this.websocket.onopen = () => {
                        console.log('WebSocket 连接已建立');
                        this.connected = true;
                    };
                    
                    this.websocket.onmessage = (event) => {
                        try {
                            const data = JSON.parse(event.data);
                            this.handleWebSocketMessage(data);
                        } catch (error) {
                            console.error('解析 WebSocket 消息失败:', error);
                        }
                    };
                    
                    this.websocket.onclose = () => {
                        console.log('WebSocket 连接已关闭');
                        this.connected = false;
                    };
                    
                    this.websocket.onerror = (error) => {
                        console.warn('WebSocket 连接失败，将使用 REST API 模式:', error);
                        this.connected = false;
                        // 不显示错误，静默降级到 REST API
                        // 立即尝试使用 REST API 检查状态
                        this.checkAuthStatus();
                    };
                } catch (error) {
                    console.warn('WebSocket 初始化失败，将使用 REST API 模式');
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
                    console.warn('WebSocket 未连接，使用 REST API');
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
                            url = '/api/auth/init';
                            payload = {
                                api_id: parseInt(data.api_id),
                                api_hash: data.api_hash
                            };
                            break;
                        case 'send_phone':
                            url = '/api/auth/send-code';
                            payload = { phone: data.phone };
                            break;
                        case 'verify_code':
                            url = '/api/auth/verify-code';
                            payload = { code: data.code };
                            break;
                        case 'verify_password':
                            url = '/api/auth/verify-password';
                            payload = { password: data.password };
                            break;
                        case 'disconnect':
                            url = '/api/auth/disconnect';
                            method = 'POST';
                            break;
                        default:
                            console.error('未知的 API 操作:', action);
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
                    } else {
                        this.handleError(result.detail || '操作失败');
                    }
                } catch (error) {
                    console.error('REST API 请求失败:', error);
                    this.handleError('网络请求失败');
                }
            },
            
            handleWebSocketMessage(data) {
                console.log('收到 WebSocket 消息:', data);
                
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
                    const response = await axios.get('/api/auth/status');
                    if (response.data.authorized) {
                        this.authStatus = '已认证';
                        this.currentStep = 5;
                    } else {
                        this.authStatus = '未认证';
                    }
                } catch (error) {
                    console.log('使用模拟认证状态');
                    this.authStatus = '未认证';
                }
            },
            
            submitConfig() {
                if (this.canProceed) {
                    this.loading = true;
                    this.loadingMessage = '正在初始化认证...';
                    this.errorMessage = '';
                    
                    this.sendWebSocketMessage('init_auth', {
                        api_id: parseInt(this.config.api_id),
                        api_hash: this.config.api_hash
                    });
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
                    const response = await axios.get('/api/auth/info');
                    this.handleAuthInfo(response.data);
                } catch (error) {
                    console.log('获取认证信息失败:', error);
                }
            },
            
            handleAuthInfo(data) {
                this.savedAuthInfo = data;
                if (data.has_saved_auth) {
                    this.showSavedInfo = true;
                    this.authStatus = '已保存认证信息';
                } else {
                    this.showSavedInfo = false;
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
                    
                    const response = await axios.post('/api/auth/clear');
                    if (response.data.success) {
                        this.handleAuthCleared(response.data.message);
                    } else {
                        this.handleError(response.data.error);
                    }
                } catch (error) {
                    console.error('清除认证数据失败:', error);
                    this.handleError('清除认证数据失败');
                } finally {
                    this.loading = false;
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
                // 避免显示错误，改为静默处理
                console.log('操作失败:', message);
                this.loading = false;
                this.verifying = false;
                // 不显示错误消息，避免用户看到错误按钮
            }
        }
};

// 创建并挂载应用
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM loaded, mounting Vue app...');
    const app = createApp(AuthApp);
    app.use(ElementPlus);
    app.mount('#app');
    console.log('Vue app mounted successfully');
}); 