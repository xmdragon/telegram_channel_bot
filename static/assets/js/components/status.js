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
            
            // 系统统计
            systemStats: {
                channels: { label: '监听频道', value: 0 },
                messages: { label: '处理消息', value: 0 },
                pending: { label: '待审核', value: 0 },
                forwarded: { label: '已转发', value: 0 }
            },
            
            // 服务状态
            services: [
                { name: 'Telegram客户端', description: '消息采集服务', status: 'stopped' },
                { name: '消息处理器', description: '内容过滤与处理', status: 'stopped' },
                { name: '调度器', description: '自动转发调度', status: 'stopped' },
                { name: '数据库', description: 'PostgreSQL数据库', status: 'stopped' }
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
        async loadSystemStatus() {
            try {
                const response = await axios.get('/api/system/status');
                if (response.data) {
                    this.updateSystemStatus(response.data);
                }
            } catch (error) {
                // console.error('加载系统状态失败:', error);
                MessageManager.error('加载系统状态失败');
            }
        },
        
        updateSystemStatus(data) {
            // 更新统计数据
            if (data.stats) {
                this.systemStats.channels.value = data.stats.source_channels || 0;
                this.systemStats.messages.value = data.stats.total_messages || 0;
                this.systemStats.pending.value = data.stats.pending_messages || 0;
                this.systemStats.forwarded.value = data.stats.forwarded_messages || 0;
            }
            
            // 更新服务状态
            if (data.services) {
                this.services[0].status = data.services.telegram_client ? 'running' : 'stopped';
                this.services[1].status = data.services.message_processor ? 'running' : 'stopped';
                this.services[2].status = data.services.scheduler ? 'running' : 'stopped';
                this.services[3].status = data.services.database ? 'running' : 'stopped';
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
                
                const response = await axios.post('/api/system/restart');
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
        }
    }
});

app.use(ElementPlus);
// 注册导航栏组件
if (window.NavBar) {
    app.component('nav-bar', window.NavBar);
}
app.mount('#app');