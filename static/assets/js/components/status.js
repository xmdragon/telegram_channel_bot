// 确保API配置可用
const API = window.API;

const { createApp } = Vue;

// SimpleUI消息管理器
const MessageManager = window.SimpleUI ? window.SimpleUI.Message : {
    success: (message) => console.log('SUCCESS:', message),
    error: (message) => console.error('ERROR:', message),
    warning: (message) => console.warn('WARNING:', message),
    info: (message) => console.info('INFO:', message)
};

const app = createApp({
    data() {
        return {
            loading: false,
            loadingMessage: '加载系统状态...',
            autoRefresh: true,
            refreshInterval: null,
            supervisorConnected: false,

            // WebSocket相关
            ws: null,

            // 服务状态
            services: [],

            // 日志弹窗
            logModal: {
                visible: false,
                serviceId: '',
                serviceName: '',
                logType: 'stdout',
                logs: ''
            },
            
            // 系统信息
            systemInfo: {
                version: '1.0.0',
                uptime: '0小时',
                lastUpdate: new Date().toLocaleString('zh-CN')
            },
            
        };
    },
    
    mounted() {
        this.loadSystemStatus();
        this.startAutoRefresh();
        this.connectWebSocket();
    },
    
    beforeUnmount() {
        this.stopAutoRefresh();
        this.disconnectWebSocket();
    },
    
    methods: {
        getServiceIcon(serviceName) {
            // 返回CSS类名而不是emoji，以便在CSS中控制显示
            const iconMap = {
                'Telegram客户端': 'service-icon-telegram',
                'Telegram采集器': 'service-icon-telegram',
                '消息处理器': 'service-icon-processor',
                'Web服务': 'service-icon-web',
                '调度器': 'service-icon-scheduler',
                'Redis存储': 'service-icon-storage'
            };
            return iconMap[serviceName] || 'service-icon-default';
        },

        getStatusClass(status) {
            const statusMap = {
                'running': 'status-success',
                'stopped': 'status-danger',
                'starting': 'status-warning',
                'stopping': 'status-warning',
                'failed': 'status-danger',
                'restarting': 'status-warning',
                'unknown': 'status-secondary'
            };
            return statusMap[status] || 'status-secondary';
        },

        getStatusIcon(status) {
            const iconMap = {
                'running': 'icon-check',
                'stopped': 'icon-close',
                'starting': 'icon-loading',
                'stopping': 'icon-loading',
                'failed': 'icon-error',
                'restarting': 'icon-loading',
                'unknown': 'icon-question'
            };
            return iconMap[status] || 'icon-question';
        },

        getStatusText(status) {
            const textMap = {
                'running': '运行中',
                'stopped': '已停止',
                'starting': '启动中',
                'stopping': '停止中',
                'failed': '失败',
                'restarting': '重启中',
                'unknown': '未知'
            };
            return textMap[status] || '未知';
        },
        
        async loadSystemStatus() {
            try {
                // 加载服务状态
                const response = await axios.get(API.services.status);

                if (response.data.success) {
                    this.services = response.data.services || [];
                    this.supervisorConnected = response.data.connected || false;

                    if (!this.supervisorConnected) {
                        console.warn('Supervisor未连接');
                    }
                }

                // 加载系统信息
                const systemResponse = await axios.get(API.system.systemStatus);
                if (systemResponse.data) {
                    this.updateSystemStatus(systemResponse.data);
                }
            } catch (error) {
                console.error('加载服务状态失败:', error);
                MessageManager.error('加载服务状态失败');
            }
        },
        
        updateSystemStatus(data) {
            // 更新系统信息
            if (data.system) {
                this.systemInfo.uptime = this.formatUptime(data.system.uptime || 0);
                this.systemInfo.lastUpdate = new Date().toLocaleString('zh-CN');
            }
        },
        
        formatUptime(seconds) {
            const hours = Math.floor(seconds / 3600);
            const minutes = Math.floor((seconds % 3600) / 60);
            
            if (hours > 24) {
                const days = Math.floor(hours / 24);
                return `${days}天${hours % 24}小时`;
            }
            return `${hours}小时${minutes}分钟`;
        },
        
        startAutoRefresh() {
            if (this.autoRefresh) {
                this.refreshInterval = setInterval(() => {
                    this.loadSystemStatus();
                }, 5000); // 每5秒刷新一次
            }
        },
        
        stopAutoRefresh() {
            if (this.refreshInterval) {
                clearInterval(this.refreshInterval);
                this.refreshInterval = null;
            }
        },
        
        async refreshStatus() {
            this.loading = true;
            this.loadingMessage = '正在刷新状态...';
            try {
                await this.loadSystemStatus();
                MessageManager.success('状态已刷新');
            } catch (error) {
                MessageManager.error('刷新失败');
            } finally {
                this.loading = false;
            }
        },
        
        async restartService(serviceId) {
            if (!confirm(`确定要重启${serviceId}服务吗？`)) return;

            this.loading = true;
            this.loadingMessage = `正在重启服务...`;

            try {
                const response = await axios.post(API.services.restart(serviceId));
                if (response.data.success) {
                    MessageManager.success(`服务${serviceId}正在重启`);
                    setTimeout(() => this.loadSystemStatus(), 2000);
                } else {
                    MessageManager.error(response.data.message || '重启失败');
                }
            } catch (error) {
                MessageManager.error(`重启失败: ${error.message}`);
            } finally {
                this.loading = false;
            }
        },

        async toggleService(service) {
            const action = service.status === 'running' ? 'stop' : 'start';
            const actionText = action === 'stop' ? '停止' : '启动';

            if (!confirm(`确定要${actionText}${service.display_name || service.name}服务吗？`)) return;

            this.loading = true;
            this.loadingMessage = `正在${actionText}服务...`;

            try {
                const endpoint = action === 'stop' ? API.services.stop(service.id) : API.services.start(service.id);
                const response = await axios.post(endpoint);

                if (response.data.success) {
                    MessageManager.success(`服务${service.display_name}正在${actionText}`);
                    setTimeout(() => this.loadSystemStatus(), 2000);
                } else {
                    MessageManager.error(response.data.message || `${actionText}失败`);
                }
            } catch (error) {
                MessageManager.error(`操作失败: ${error.message}`);
            } finally {
                this.loading = false;
            }
        },

        async viewLogs(serviceId) {
            const service = this.services.find(s => s.id === serviceId);
            if (!service) return;

            this.logModal.serviceId = serviceId;
            this.logModal.serviceName = service.display_name || service.name;
            this.logModal.visible = true;
            this.logModal.logs = '加载中...';

            await this.refreshLogs();
        },

        async refreshLogs() {
            try {
                const response = await axios.get(API.services.logs(this.logModal.serviceId), {
                    params: {
                        log_type: this.logModal.logType,
                        lines: 200
                    }
                });

                if (response.data.success) {
                    this.logModal.logs = response.data.logs || '暂无日志';
                } else {
                    this.logModal.logs = '获取日志失败';
                }
            } catch (error) {
                this.logModal.logs = `获取日志失败: ${error.message}`;
            }
        },

        closeLogModal() {
            this.logModal.visible = false;
            this.logModal.logs = '';
        },

        async resetMessages() {
            const confirmMessage = '⚠️ 警告：此操作将执行以下危险操作：\n\n' +
                '• 停止Telegram消息采集器\n' +
                '• 清空所有消息数据\n' +
                '• 清空临时媒体文件\n' +
                '• 重置所有频道采集点为0\n\n' +
                '此操作不可逆转！确定要继续吗？';

            if (!confirm(confirmMessage)) {
                return;
            }

            this.loading = true;
            this.loadingMessage = '正在重置系统...';

            try {
                const response = await axios.post(API.system.reset);
                if (response.data.success) {
                    MessageManager.success(
                        `重置完成：清空${response.data.details.cleared_messages}条消息，` +
                        `重置${response.data.details.reset_channels}个频道`
                    );
                    // 等待几秒后刷新状态
                    setTimeout(() => {
                        this.loadSystemStatus();
                    }, 2000);
                } else {
                    MessageManager.error(response.data.message || '重置失败');
                }
            } catch (error) {
                MessageManager.error('重置系统失败');
            } finally {
                this.loading = false;
            }
        },
        
        // WebSocket相关方法
        connectWebSocket() {
            try {
                // 使用统一的WebSocket工厂，消除重复代码
                this.ws = WebSocketFactory.create('main');

                this.ws.onopen = () => {
                    // WebSocket连接已建立
                };

                this.ws.onmessage = (event) => {
                    try {
                        const data = JSON.parse(event.data);
                        this.handleWebSocketMessage(data);
                    } catch (error) {
                        console.error('解析WebSocket消息失败:', error);
                    }
                };

                this.ws.onclose = () => {
                    // WebSocket连接已关闭，准备重连
                    // 5秒后重连
                    setTimeout(() => {
                        if (!this.ws || this.ws.readyState === WebSocket.CLOSED) {
                            this.connectWebSocket();
                        }
                    }, 5000);
                };

                this.ws.onerror = (error) => {
                    console.error('WebSocket 错误:', error);
                };

            } catch (error) {
                console.error('WebSocket 连接失败:', error);
            }
        },

        disconnectWebSocket() {
            if (this.ws) {
                this.ws.close();
                this.ws = null;
            }
        },

        handleWebSocketMessage(data) {
            // 处理WebSocket消息
            // 目前主要用于实时更新服务状态
        },
        
    }
});

// 注册导航栏组件
if (window.NavBar) {
    app.component('nav-bar', window.NavBar);
}
app.mount('#app');