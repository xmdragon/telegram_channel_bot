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
            logs: [],
            filteredLogs: [],
            selectedLevel: '',
            selectedLogType: 'collector', // 默认选择Telegram采集日志
            searchText: '',
            autoRefresh: true,
            websocket: null,
            isWebSocketConnected: false,
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
                // 统一使用主日志API，每次都重新加载以确保日志类型正确
                const response = await axios.get(API.system.logs, {
                    params: { 
                        limit: 100,
                        log_type: this.selectedLogType 
                    }
                });
                
                if (response.data && response.data.logs) {
                    this.logs = response.data.logs;
                }
                
                this.filterLogs();
                this.lastUpdate = new Date().toLocaleString('zh-CN');
            } catch (error) {
                console.error('加载日志失败:', error);
                // 如果网络错误，显示基本信息
                if (this.logs.length === 0) {
                    this.logs = [
                        { timestamp: new Date().toISOString(), level: 'ERROR', message: `日志加载失败: ${error.message}` },
                        { timestamp: new Date().toISOString(), level: 'INFO', message: '系统正常运行' }
                    ];
                    this.filterLogs();
                }
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
            if (this.autoRefresh && !this.isWebSocketConnected) {
                this.connectWebSocket();
            }
        },
        
        stopAutoRefresh() {
            this.disconnectWebSocket();
        },
        
        async changeLogType() {
            // 切换日志类型时重新加载日志
            this.logs = [];
            this.filteredLogs = [];
            await this.loadLogs();
            MessageManager.success(`已切换到${this.getLogTypeLabel()}日志`);
        },
        
        getLogTypeLabel() {
            const labels = {
                'collector': 'Telegram采集',
                'web': 'Web服务',
                'scheduler': '调度服务',
                'error': '错误日志',
                'all': '全部日志'
            };
            return labels[this.selectedLogType] || 'Telegram采集';
        },

        // WebSocket连接管理 - Linus式推送替代轮询
        connectWebSocket() {
            if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
                return; // 已连接，无需重复连接
            }

            try {
                // 使用API配置中的WebSocket URL
                const wsUrl = window.API ? window.API.websocket.main : 'ws://localhost:8000/ws';
                this.websocket = new WebSocket(wsUrl);

                this.websocket.onopen = () => {
                    this.isWebSocketConnected = true;
                    MessageManager.success('实时日志推送已启用');
                    
                    // 订阅日志更新
                    this.websocket.send(JSON.stringify({
                        type: 'subscribe',
                        channel: 'logs',
                        log_type: this.selectedLogType
                    }));
                };

                this.websocket.onmessage = (event) => {
                    try {
                        const data = JSON.parse(event.data);
                        this.handleWebSocketMessage(data);
                    } catch (error) {
                        console.warn('WebSocket消息解析失败:', error);
                    }
                };

                this.websocket.onclose = () => {
                    this.isWebSocketConnected = false;
                    this.websocket = null;
                    
                    // 如果是自动刷新模式且页面还在，尝试重连
                    if (this.autoRefresh) {
                        setTimeout(() => this.connectWebSocket(), 3000);
                    }
                };

                this.websocket.onerror = (error) => {
                    console.error('WebSocket错误:', error);
                    MessageManager.error('实时日志连接失败，已回退到手动刷新');
                };

            } catch (error) {
                console.error('WebSocket连接失败:', error);
                MessageManager.error('无法建立实时连接');
            }
        },

        disconnectWebSocket() {
            if (this.websocket) {
                this.websocket.close();
                this.websocket = null;
                this.isWebSocketConnected = false;
            }
        },

        handleWebSocketMessage(data) {
            if (data.type === 'log_update' && data.data && data.data.logs) {
                // 服务器推送的日志更新
                if (data.data.log_type === this.selectedLogType) {
                    // 添加新日志到列表顶部
                    this.logs = [...data.data.logs, ...this.logs].slice(0, 100); // 保持100条限制
                    this.filterLogs();
                    this.lastUpdate = new Date().toLocaleString('zh-CN');
                }
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