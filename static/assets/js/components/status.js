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
            
            // WebSocket相关
            ws: null,
            operationProgress: {
                active: false,
                operation: '',
                progress: 0,
                message: '',
                type: ''  // 'system_status' 或 'system_reset'
            },
            
            
            // 服务状态
            services: [
                { name: 'Telegram客户端', description: '消息采集服务', status: 'stopped' },
                { name: '消息处理器', description: '内容过滤与处理', status: 'stopped' },
                { name: '调度器', description: '自动转发调度', status: 'stopped' },
                { name: 'Redis存储', description: 'Redis数据存储服务', status: 'stopped' }
            ],
            
            // 系统信息
            systemInfo: {
                version: '1.0.0',
                uptime: '0小时',
                lastUpdate: new Date().toLocaleString('zh-CN')
            },
            
            // 进度条颜色配置（保留数据结构用于可能的扩展）
            progressColors: [
                { color: '#f56565', percentage: 20 },
                { color: '#ed8936', percentage: 40 },
                { color: '#ecc94b', percentage: 60 },
                { color: '#48bb78', percentage: 80 },
                { color: '#38b2ac', percentage: 100 }
            ]
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
                '消息处理器': 'service-icon-processor', 
                '调度器': 'service-icon-scheduler',
                'Redis存储': 'service-icon-storage'
            };
            return iconMap[serviceName] || 'service-icon-default';
        },
        
        async loadSystemStatus() {
            try {
                // 加载系统状态（不包含消息统计）
                const statusResponse = await axios.get(API.system.systemStatus);
                
                if (statusResponse.data) {
                    this.updateSystemStatus(statusResponse.data);
                }
                
                // 系统状态页面不需要消息统计数据
            } catch (error) {
                MessageManager.error('加载系统状态失败');
            }
        },
        
        updateSystemStatus(data) {
            // 更新服务状态和系统信息
            
            // 更新服务状态
            if (data.services) {
                this.services[0].status = data.services.telegram_client ? 'running' : 'stopped';
                this.services[1].status = data.services.message_processor ? 'running' : 'stopped';
                this.services[2].status = data.services.scheduler ? 'running' : 'stopped';
                this.services[3].status = data.services.redis ? 'running' : 'stopped';
            }
            
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
                // Linus风格：使用统一的WebSocket工厂，消除重复代码
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
            // 处理WebSocket消息（生产环境已移除调试日志）
            if (data.type === 'operation_progress') {
                // 处理进度消息
                // 只为消息重置操作显示弹窗，忽略系统状态检查
                if (data.data.operation === 'system_reset') {
                    this.updateProgress(data.data);
                }
                // system_status 操作静默执行，不显示弹窗
            }
            // 可以添加其他类型的WebSocket消息处理
        },
        
        updateProgress(progressData) {
            this.operationProgress = {
                active: true,
                operation: progressData.operation,
                progress: progressData.progress,
                message: progressData.message,
                type: progressData.operation
            };
            
            // 如果进度完成，延迟隐藏
            if (progressData.progress >= 100) {
                setTimeout(() => {
                    this.operationProgress.active = false;
                    // 刷新状态（如果是系统状态检查完成）
                    if (progressData.operation === 'system_status') {
                        // 系统状态已经通过API获取，无需额外刷新
                    } else if (progressData.operation === 'system_reset') {
                        // 重置完成后刷新状态
                        setTimeout(() => {
                            this.loadSystemStatus();
                        }, 1000);
                    }
                }, 2000);
            }
        },
        
        getProgressTitle() {
            const titleMap = {
                'system_status': '系统状态检查',
                'system_reset': '系统重置进行中'
            };
            return titleMap[this.operationProgress.operation] || '操作进行中';
        },
        
    }
});

// 注册导航栏组件
if (window.NavBar) {
    app.component('nav-bar', window.NavBar);
}
app.mount('#app');