// Telegram 双Session认证页面 JavaScript

// 确保API配置可用
const API = window.API;

const { createApp } = Vue;

// 双Session认证应用组件
const DualAuthApp = {
    data() {
        return {
            loading: false,
            loadingMessage: '',
            statusMessage: '',
            statusType: 'success',
            
            // API配置状态
            hasSharedApi: false,
            
            // 采集Session状态
            listenerSession: {
                currentStep: 1,
                phone: '',
                verificationCode: '',
                password: '',
                loading: false,
                completed: false,
                needsPassword: false,
                errorMessage: ''
            },
            
            // 发送Session状态
            senderSession: {
                currentStep: 1,
                phone: '',
                verificationCode: '',
                password: '',
                loading: false,
                completed: false,
                needsPassword: false,
                errorMessage: ''
            },
            
            // WebSocket连接
            websocket: null,
            connected: false
        }
    },
    
    computed: {
        bothSessionsCompleted() {
            return this.listenerSession.completed && this.senderSession.completed;
        }
    },
    
    async mounted() {
        // 初始化管理员认证检查
        try {
            const isAuthorized = await authManager.initPageAuth('telegram.dual.auth');
            if (!isAuthorized) {
                return; // 认证失败，页面已跳转
            }
        } catch (error) {
            console.error('管理员认证失败:', error);
            window.SimpleUI.showMessage('请先登录管理员账户');
            return;
        }
        
        this.connectWebSocket();
        await this.checkApiConfiguration();
        await this.checkDualSessionStatus();
        await this.migrateConfigIfNeeded();
    },
    
    beforeUnmount() {
        this.disconnectWebSocket();
    },
    
    methods: {
        connectWebSocket() {
            try {
                if (!window.WebSocket) {
                    this.connected = false;
                    return;
                }
                
                this.websocket = WebSocketFactory.create('main');
                
                this.websocket.onopen = () => {
                    this.connected = true;
                };
                
                this.websocket.onmessage = (event) => {
                    try {
                        const data = JSON.parse(event.data);
                        this.handleWebSocketMessage(data);
                    } catch (error) {
                        // 忽略解析错误
                    }
                };
                
                this.websocket.onclose = () => {
                    this.connected = false;
                };
                
                this.websocket.onerror = () => {
                    this.connected = false;
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
        
        handleWebSocketMessage(data) {
            // 处理WebSocket消息（如果需要实时状态更新）
            if (data.type === 'session_status_update') {
                this.updateSessionStatus(data.session_type, data.status);
            }
        },
        
        async checkDualSessionStatus() {
            try {
                const response = await axios.get(API.dualAuth.dualSessionStatus);
                
                if (response.data.success) {
                    const { listener, sender, config } = response.data;
                    
                    // 更新Session状态
                    this.updateSessionFromStatus('listener', listener);
                    this.updateSessionFromStatus('sender', sender);
                    
                    // 检查是否有配置
                    if (config.listener_configured || config.sender_configured) {
                        // 假设API已配置
                        this.hasSharedApi = true;
                    }
                }
            } catch (error) {
                console.error('检查双Session状态失败:', error);
            }
        },
        
        updateSessionFromStatus(sessionType, status) {
            const session = sessionType === 'listener' ? this.listenerSession : this.senderSession;
            
            if (status.state === 'authorized') {
                session.completed = true;
                session.currentStep = 3;
            } else if (status.state === 'password_needed') {
                session.needsPassword = true;
                session.currentStep = 3;
            } else if (status.state === 'code_sent') {
                session.currentStep = 2;
            }
            
            if (status.error_message) {
                session.errorMessage = status.error_message;
            }
        },
        
        async migrateConfigIfNeeded() {
            try {
                const response = await axios.post(API.dualAuth.migrateConfig);
                if (response.data.success && response.data.details && response.data.details.migrated) {
                    window.SimpleUI.showMessage('配置已迁移到双Session结构', 'success');
                    await this.checkDualSessionStatus();
                }
            } catch (error) {
                console.error('配置迁移失败:', error);
            }
        },
        
        async checkApiConfiguration() {
            try {
                // 从系统配置检查API是否已配置  
                const response = await axios.get(API.admin.config);
                if (response.data) {
                    const configs = response.data;
                    const hasApiId = configs['telegram.api_id'];
                    const hasApiHash = configs['telegram.api_hash'];
                    
                    this.hasSharedApi = !!(hasApiId && hasApiHash);
                    
                    if (this.hasSharedApi) {
                        // 初始化双Session
                        await this.initSession('listener');
                        await this.initSession('sender');
                    }
                }
            } catch (error) {
                console.error('检查API配置失败:', error);
                this.hasSharedApi = false;
            }
        },
        
        goToConfig() {
            // 跳转到系统配置页面的系统设置标签
            window.location.href = '/static/config.html#system';
        },
        
        async checkApiConfig() {
            await this.checkApiConfiguration();
            if (this.hasSharedApi) {
                window.SimpleUI.showMessage('API配置检查完成', 'success');
            } else {
                window.SimpleUI.showMessage('未检测到API配置，请先配置', 'warning');
            }
        },
        
        async initSession(sessionType) {
            try {
                const response = await axios.post(API.dualAuth.initSession, {
                    session_type: sessionType
                });
                
                if (response.data.success) {
                    const session = sessionType === 'listener' ? this.listenerSession : this.senderSession;
                    
                    if (response.data.status.state === 'authorized') {
                        session.completed = true;
                        session.currentStep = 3;
                    }
                }
            } catch (error) {
                console.error(`初始化${sessionType}Session失败:`, error);
            }
        },
        
        async sendCode(sessionType) {
            const session = sessionType === 'listener' ? this.listenerSession : this.senderSession;
            
            if (!session.phone) {
                session.errorMessage = '请输入手机号码';
                return;
            }
            
            session.loading = true;
            session.errorMessage = '';
            
            try {
                const response = await axios.post(API.dualAuth.sendCode, {
                    session_type: sessionType,
                    phone: session.phone
                });
                
                if (response.data.success) {
                    session.currentStep = 2;
                    window.SimpleUI.showMessage(`${sessionType}验证码已发送`, 'success');
                } else {
                    session.errorMessage = response.data.error;
                }
            } catch (error) {
                console.error(`发送${sessionType}验证码失败:`, error);
                session.errorMessage = '发送验证码失败';
            } finally {
                session.loading = false;
            }
        },
        
        async verifyCode(sessionType) {
            const session = sessionType === 'listener' ? this.listenerSession : this.senderSession;
            
            if (!session.verificationCode) {
                session.errorMessage = '请输入验证码';
                return;
            }
            
            session.loading = true;
            session.errorMessage = '';
            
            try {
                const response = await axios.post(API.dualAuth.verifyCode, {
                    session_type: sessionType,
                    code: session.verificationCode
                });
                
                if (response.data.success) {
                    if (response.data.next_step === 'password') {
                        session.needsPassword = true;
                        session.currentStep = 3;
                        window.SimpleUI.showMessage('请输入两步验证密码', 'info');
                    } else {
                        // 认证完成
                        session.completed = true;
                        session.currentStep = 3;
                        window.SimpleUI.showMessage(`${sessionType}认证成功！`, 'success');
                    }
                } else {
                    session.errorMessage = response.data.error;
                }
            } catch (error) {
                console.error(`验证${sessionType}验证码失败:`, error);
                session.errorMessage = '验证码验证失败';
            } finally {
                session.loading = false;
            }
        },
        
        async verifyPassword(sessionType) {
            const session = sessionType === 'listener' ? this.listenerSession : this.senderSession;
            
            if (!session.password) {
                session.errorMessage = '请输入两步验证密码';
                return;
            }
            
            session.loading = true;
            session.errorMessage = '';
            
            try {
                const response = await axios.post(API.dualAuth.verifyPassword, {
                    session_type: sessionType,
                    password: session.password
                });
                
                if (response.data.success) {
                    session.completed = true;
                    session.currentStep = 3;
                    window.SimpleUI.showMessage(`${sessionType}认证成功！`, 'success');
                } else {
                    session.errorMessage = response.data.error;
                }
            } catch (error) {
                console.error(`验证${sessionType}密码失败:`, error);
                session.errorMessage = '密码验证失败';
            } finally {
                session.loading = false;
            }
        },
        
        async clearSession(sessionType) {
            const session = sessionType === 'listener' ? this.listenerSession : this.senderSession;
            
            const confirmed = await window.SimpleUI.confirm(
                `确定要清除${sessionType === 'listener' ? '采集' : '发布'}Session认证吗？`,
                '确认清除'
            );
            
            if (!confirmed) return;
            
            try {
                const response = await axios.post(API.dualAuth.clearSession, {
                    session_type: sessionType
                });
                
                if (response.data.success) {
                    // 重置Session状态
                    session.currentStep = 1;
                    session.phone = '';
                    session.verificationCode = '';
                    session.password = '';
                    session.loading = false;
                    session.completed = false;
                    session.needsPassword = false;
                    session.errorMessage = '';
                    
                    window.SimpleUI.showMessage(`${sessionType}Session已清除`, 'success');
                } else {
                    window.SimpleUI.showMessage('清除失败', 'error');
                }
            } catch (error) {
                console.error(`清除${sessionType}Session失败:`, error);
                window.SimpleUI.showMessage('清除失败', 'error');
            }
        },
        
        async resetAllSessions() {
            const confirmed = await window.SimpleUI.confirm(
                '确定要重新配置所有Session吗？这将清除所有认证信息。',
                '确认重置'
            );
            
            if (!confirmed) return;
            
            try {
                // 清除双Session
                await axios.post(API.dualAuth.clearSession, { session_type: 'listener' });
                await axios.post(API.dualAuth.clearSession, { session_type: 'sender' });
                
                // 重置界面状态
                this.hasSharedApi = false;
                
                // 重置Session状态
                this.resetSessionState(this.listenerSession);
                this.resetSessionState(this.senderSession);
                
                window.SimpleUI.showMessage('所有Session已重置', 'success');
            } catch (error) {
                console.error('重置Session失败:', error);
                window.SimpleUI.showMessage('重置失败', 'error');
            }
        },
        
        resetSessionState(session) {
            session.currentStep = 1;
            session.phone = '';
            session.verificationCode = '';
            session.password = '';
            session.loading = false;
            session.completed = false;
            session.needsPassword = false;
            session.errorMessage = '';
        },
        
        goToMain() {
            window.location.href = '/static/index.html';
        }
    }
};

// 创建Vue应用实例
const app = createApp(DualAuthApp);

// 注册全局组件
app.component('nav-bar', NavBar);

// 挂载应用
app.mount('#app');