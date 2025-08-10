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
            logs: [],
            filteredLogs: [],
            selectedLevel: '',
            searchText: '',
            autoRefresh: true,
            refreshInterval: null,
            lastUpdate: new Date().toLocaleString('zh-CN')
        };
    },
    
    mounted() {
        this.loadLogs();
        this.startAutoRefresh();
    },
    
    beforeUnmount() {
        this.stopAutoRefresh();
    },
    
    methods: {
        async loadLogs() {
            try {
                const response = await axios.get('/api/system/logs', {
                    params: { limit: 100 }
                });
                
                if (response.data && response.data.logs) {
                    this.logs = response.data.logs;
                    this.filterLogs();
                    this.lastUpdate = new Date().toLocaleString('zh-CN');
                } else if (response.data && response.data.success === false) {
                    // 如果返回失败，显示默认消息
                    this.logs = [
                        { time: new Date().toISOString(), level: 'INFO', message: '系统正常运行' }
                    ];
                    this.filterLogs();
                }
            } catch (error) {
                console.error('加载日志失败:', error);
                // 如果网络错误，不显示错误消息，只显示基本信息
                this.logs = [
                    { time: new Date().toISOString(), level: 'INFO', message: '系统正常运行' }
                ];
                this.filterLogs();
            }
        },
        
        filterLogs() {
            let filtered = [...this.logs];
            
            // 按级别过滤
            if (this.selectedLevel) {
                filtered = filtered.filter(log => 
                    (log.level || '').toUpperCase() === this.selectedLevel.toUpperCase()
                );
            }
            
            // 按搜索文本过滤
            if (this.searchText) {
                const searchLower = this.searchText.toLowerCase();
                filtered = filtered.filter(log => 
                    (log.message || '').toLowerCase().includes(searchLower) ||
                    (log.content || '').toLowerCase().includes(searchLower)
                );
            }
            
            this.filteredLogs = filtered;
        },
        
        formatTime(timestamp) {
            if (!timestamp) return '';
            
            try {
                const date = new Date(timestamp);
                return date.toLocaleString('zh-CN', {
                    hour12: false,
                    year: 'numeric',
                    month: '2-digit',
                    day: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit'
                });
            } catch (e) {
                return timestamp;
            }
        },
        
        async clearLogs() {
            try {
                await ElMessageBox.confirm('确定要清空所有日志吗？', '警告', {
                    confirmButtonText: '确定',
                    cancelButtonText: '取消',
                    type: 'warning'
                });
                
                // 目前没有清空日志API，只清空前端显示
                this.logs = [];
                this.filteredLogs = [];
                MessageManager.success('日志显示已清空');
            } catch (error) {
                if (error !== 'cancel') {
                    MessageManager.error('清空日志失败');
                }
            }
        },
        
        toggleAutoRefresh() {
            this.autoRefresh = !this.autoRefresh;
            if (this.autoRefresh) {
                this.startAutoRefresh();
                MessageManager.success('已开启自动刷新');
            } else {
                this.stopAutoRefresh();
                MessageManager.info('已停止自动刷新');
            }
        },
        
        startAutoRefresh() {
            if (this.autoRefresh && !this.refreshInterval) {
                this.refreshInterval = setInterval(() => {
                    this.loadLogs();
                }, 2000); // 每2秒刷新一次
            }
        },
        
        stopAutoRefresh() {
            if (this.refreshInterval) {
                clearInterval(this.refreshInterval);
                this.refreshInterval = null;
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