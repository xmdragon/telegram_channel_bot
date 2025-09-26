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
            hasValidApi: false,
            savingApi: false,
            apiConfig: {
                api_id: '',
                api_hash: ''
            },

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
        // 启动时加载配置
        await this.loadApiConfig();
        await this.checkDualSessionStatus();
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
        
        async checkDualSessionStatus(config = null) {
            try {
                // 如果没有传入配置，才去获取
                if (!config) {
                    const response = await axios.get(API.telegramConfig.get);
                    config = response.data.config;
                }

                if (config) {

                    // 检查SESSION配置是否存在（非空）
                    const listenerSession = config.listener_session;
                    const senderSession = config.sender_session;

                    // 根据SESSION配置的存在性来设置状态
                    if (listenerSession && listenerSession.trim() !== '') {
                        this.listenerSession.completed = true;
                        this.listenerSession.currentStep = 3;
                    } else {
                        this.listenerSession.completed = false;
                        this.listenerSession.currentStep = 1;
                    }

                    if (senderSession && senderSession.trim() !== '') {
                        this.senderSession.completed = true;
                        this.senderSession.currentStep = 3;
                    } else {
                        this.senderSession.completed = false;
                        this.senderSession.currentStep = 1;
                    }
                }
            } catch (error) {
                console.error('检查Session配置失败:', error);
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


        async loadApiConfig() {
            try {
                // 从新的telegram-config端点获取配置
                const response = await axios.get(API.telegramConfig.get);
                if (response.data && response.data.config) {
                    const config = response.data.config;

                    // 加载现有配置到表单
                    this.apiConfig.api_id = config.api_id || '';
                    this.apiConfig.api_hash = config.api_hash || '';

                    // 检查配置是否有效
                    this.hasValidApi = !!(config.api_id && config.api_hash);

                    return config;
                }
            } catch (error) {
                console.error('加载API配置失败:', error);
                this.hasValidApi = false;
                return null;
            }
        },

        async saveApiConfig() {
            try {
                this.savingApi = true;

                const response = await axios.post(API.telegramConfig.update, {
                    api_id: this.apiConfig.api_id.trim(),
                    api_hash: this.apiConfig.api_hash.trim()
                });

                if (response.data.success) {
                    this.hasValidApi = true;
                    window.SimpleUI.showMessage('API配置已保存成功', 'success');

                    // 重新加载配置以确保同步
                    await this.loadApiConfig();
                }
            } catch (error) {
                console.error('保存API配置失败:', error);
                window.SimpleUI.showMessage('保存API配置失败: ' + (error.response?.data?.detail || error.message), 'error');
            } finally {
                this.savingApi = false;
            }
        },

        goToConfig() {
            // 跳转到系统配置页面的系统设置标签
            window.location.href = API.pages.config + '#system';
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
                `确定要重新开始${sessionType === 'listener' ? '采集' : '发布'}Session认证吗？`,
                '确认重新认证'
            );

            if (!confirmed) return;

            // 由于SESSION配置通过系统配置页面管理，这里只重置前端状态
            session.currentStep = 1;
            session.phone = '';
            session.verificationCode = '';
            session.password = '';
            session.loading = false;
            session.completed = false;
            session.needsPassword = false;
            session.errorMessage = '';

            window.SimpleUI.showMessage(`${sessionType}认证状态已重置，请重新开始认证流程`, 'info');
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
            window.location.href = API.pages.index;
        }
    }
};

// 创建Vue应用实例
const app = createApp(DualAuthApp);

// 注册全局组件
app.component('nav-bar', NavBar);

// 挂载应用
app.mount('#app');