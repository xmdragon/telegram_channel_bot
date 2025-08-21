// 确保API配置可用
const API = window.API;

const { createApp } = Vue;
const { ElMessage, ElMessageBox } = ElementPlus;

// 消息管理器 - 右下角显示
const MessageManager = {
    success(message) {
        ElMessage({
            message: message,
            type: 'success',
            offset: 20,
            customClass: 'bottom-right-message'
        });
    },
    error(message) {
        ElMessage({
            message: message,
            type: 'error',
            offset: 20,
            customClass: 'bottom-right-message'
        });
    },
    warning(message) {
        ElMessage({
            message: message,
            type: 'warning',
            offset: 20,
            customClass: 'bottom-right-message'
        });
    },
    info(message) {
        ElMessage({
            message: message,
            type: 'info',
            offset: 20,
            customClass: 'bottom-right-message'
        });
    }
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
            
            // 系统统计 - 与主控制台保持一致
            systemStats: {
                total: { label: '总消息', value: 0 },
                pending: { label: '待审核', value: 0 },
                approved: { label: '已发布', value: 0 },
                rejected: { label: '已拒绝', value: 0 },
                ads: { label: '广告消息', value: 0 },
                duplicates: { label: '重复消息', value: 0 },
                chats: { label: '聊天消息', value: 0 }
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
            
            // 进度条颜色配置
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
            const iconMap = {
                'Telegram客户端': 'el-icon-message',
                '消息处理器': 'el-icon-cpu',
                '调度器': 'el-icon-timer',
                'Redis存储': 'el-icon-coin'
            };
            return iconMap[serviceName] || 'el-icon-service';
        },
        
        async loadSystemStatus() {
            try {
                // 加载系统状态（包含消息统计数据）
                const statusResponse = await axios.get(API.system.systemStatus);
                
                if (statusResponse.data) {
                    this.updateSystemStatus(statusResponse.data);
                    
                    // 从系统状态中提取消息统计
                    if (statusResponse.data.stats) {
                        this.updateMessageStatsFromSystemStatus(statusResponse.data.stats);
                    }
                }
            } catch (error) {
                MessageManager.error('加载系统状态失败');
            }
        },
        
        updateSystemStatus(data) {
            // 只更新服务状态和系统信息，统计数据由updateMessageStats处理
            
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
        
        updateMessageStats(stats) {
            // 更新消息统计数据 - 用于主控制台API数据格式
            this.systemStats.total.value = stats.total || 0;
            this.systemStats.pending.value = stats.pending || 0;
            this.systemStats.approved.value = stats.approved || 0;
            this.systemStats.rejected.value = stats.rejected || 0;
            this.systemStats.ads.value = stats.ads || 0;
            this.systemStats.duplicates.value = stats.duplicates || 0;
            this.systemStats.chats.value = stats.chats || 0;
        },
        
        updateMessageStatsFromSystemStatus(stats) {
            // 更新消息统计数据 - 用于系统状态API数据格式
            this.systemStats.total.value = stats.total_messages || 0;
            this.systemStats.pending.value = stats.pending_messages || 0;
            this.systemStats.approved.value = stats.forwarded_messages || 0;
            this.systemStats.rejected.value = 0; // 系统状态API暂不包含拒绝数
            this.systemStats.ads.value = 0;      // 系统状态API暂不包含广告数
            this.systemStats.duplicates.value = 0; // 系统状态API暂不包含重复数
            this.systemStats.chats.value = stats.source_channels || 0; // 用频道数作为聊天数
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
        
        async restartServices() {
            try {
                await ElMessageBox.confirm(
                    '确定要重启所有服务吗？这可能会暂时中断消息处理。',
                    '重启确认',
                    {
                        confirmButtonText: '确定',
                        cancelButtonText: '取消',
                        type: 'warning'
                    }
                );
                
                this.loading = true;
                this.loadingMessage = '正在重启服务...';
                
                const response = await axios.post(API.system.restart);
                if (response.data.success) {
                    MessageManager.success('服务重启成功');
                    // 等待几秒后刷新状态
                    setTimeout(() => {
                        this.loadSystemStatus();
                    }, 3000);
                } else {
                    MessageManager.error(response.data.message || '重启失败');
                }
            } catch (error) {
                if (error !== 'cancel') {
                    MessageManager.error('重启服务失败');
                }
            } finally {
                this.loading = false;
            }
        },
        
        async resetMessages() {
            try {
                await ElMessageBox.confirm(
                    '⚠️ 警告：此操作将执行以下危险操作：\n\n' +
                    '• 停止Telegram消息采集器\n' +
                    '• 清空所有消息数据\n' +
                    '• 清空临时媒体文件\n' +
                    '• 重置所有频道采集点为0\n\n' +
                    '此操作不可逆转！确定要继续吗？',
                    '🚨 消息重置确认',
                    {
                        confirmButtonText: '确定重置',
                        cancelButtonText: '取消',
                        type: 'error',
                        dangerouslyUseHTMLString: true
                    }
                );
                
                this.loading = true;
                this.loadingMessage = '正在重置系统...';
                
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
                if (error !== 'cancel') {
                    MessageManager.error('重置系统失败');
                }
            } finally {
                this.loading = false;
            }
        },
        
        // WebSocket相关方法
        connectWebSocket() {
            try {
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = `${protocol}//${window.location.host}/ws`;
                
                this.ws = new WebSocket(wsUrl);
                
                this.ws.onopen = () => {
                    console.log('WebSocket 连接已建立');
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
                    console.log('WebSocket 连接已关闭，尝试重连...');
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
            if (data.type === 'operation_progress') {
                this.updateProgress(data.data);
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
            return titleMap[this.operationProgress.type] || '操作进行中';
        }
    }
});

app.use(ElementPlus);
// 注册导航栏组件
if (window.NavBar) {
    app.component('nav-bar', window.NavBar);
}
app.mount('#app');