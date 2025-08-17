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
            
            // 系统统计 - 与主控制台保持一致
            systemStats: {
                total: { label: '总消息', value: 0 },
                pending: { label: '待审核', value: 0 },
                approved: { label: '已批准', value: 0 },
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
            }
        };
    },
    
    mounted() {
        this.loadSystemStatus();
        this.startAutoRefresh();
    },
    
    beforeUnmount() {
        this.stopAutoRefresh();
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
                // 同时加载系统状态和消息统计
                const [statusResponse, statsResponse] = await Promise.all([
                    axios.get(API.system.systemStatus),
                    axios.get(API.messages.statsOverview)
                ]);
                
                if (statusResponse.data) {
                    this.updateSystemStatus(statusResponse.data);
                }
                
                if (statsResponse.data) {
                    this.updateMessageStats(statsResponse.data);
                }
            } catch (error) {
                // console.error('加载系统状态失败:', error);
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
            // 更新消息统计数据
            this.systemStats.total.value = stats.total || 0;
            this.systemStats.pending.value = stats.pending || 0;
            this.systemStats.approved.value = stats.approved || 0;
            this.systemStats.rejected.value = stats.rejected || 0;
            this.systemStats.ads.value = stats.ads || 0;
            this.systemStats.duplicates.value = stats.duplicates || 0;
            this.systemStats.chats.value = stats.chats || 0;
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
                    // console.error('重启服务失败:', error);
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
                    // console.error('重置系统失败:', error);
                    MessageManager.error('重置系统失败');
                }
            } finally {
                this.loading = false;
            }
        }
    }
});

app.use(ElementPlus);
// 注册导航栏组件
if (window.NavBar) {
    app.component('nav-bar', window.NavBar);
}
app.mount('#app');