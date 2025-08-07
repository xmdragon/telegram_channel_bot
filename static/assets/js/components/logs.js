// 系统日志页面 JavaScript 组件

const { createApp } = Vue;
const { ElMessage, ElMessageBox } = ElementPlus;

// 日志应用组件
const LogsApp = {
    setup() {
        // 响应式数据
        const logs = Vue.ref([]);
        const filteredLogs = Vue.ref([]);
        const loading = Vue.ref(false);
        const autoRefresh = Vue.ref(true);
        const isConnected = Vue.ref(true);
        const lastUpdate = Vue.ref('');
        const refreshInterval = Vue.ref(3000); // 3秒刷新间隔
        
        // 过滤器状态
        const selectedLevel = Vue.ref('');
        const searchText = Vue.ref('');
        
        // 定时器和WebSocket
        let refreshTimer = null;
        let lastTimestamp = null;
        let websocket = null;
        
        // 格式化时间显示，只显示时分秒
        const formatTime = (timestamp) => {
            try {
                // 如果timestamp已经是时间格式，直接返回前8位
                if (typeof timestamp === 'string' && timestamp.includes(':')) {
                    // 处理 "2025-08-07 15:59:45" 格式
                    if (timestamp.length >= 19) {
                        return timestamp.substring(11, 19);
                    }
                    // 处理已经是时间格式的情况
                    return timestamp.substring(0, 8);
                }
                
                const date = new Date(timestamp);
                if (isNaN(date.getTime())) {
                    return timestamp.substring(11, 19) || timestamp.substring(0, 8) || timestamp;
                }
                return date.toTimeString().substring(0, 8); // HH:MM:SS
            } catch (error) {
                console.warn('Time format error:', error, timestamp);
                return timestamp.toString().substring(0, 8) || '00:00:00';
            }
        };
        
        // 获取系统日志
        const fetchLogs = async (isRealtime = false) => {
            try {
                loading.value = !isRealtime;
                
                let url = '/api/system/logs?lines=200';
                if (isRealtime && lastTimestamp) {
                    url = `/api/system/logs/realtime?since=${lastTimestamp}`;
                }
                
                const response = await fetch(url);
                const result = await response.json();
                
                if (result.success) {
                    if (isRealtime && result.data.logs && result.data.logs.length > 0) {
                        // 实时更新：将新日志添加到前面，同时过滤掉心跳检测
                        const newLogs = result.data.logs
                            .filter(newLog => 
                                !newLog.message.includes('系统心跳检测') && 
                                newLog.source !== 'heartbeat'
                            )
                            .filter(newLog => 
                                !logs.value.some(existingLog => 
                                    existingLog.timestamp === newLog.timestamp && 
                                    existingLog.message === newLog.message
                                )
                            );
                        if (newLogs.length > 0) {
                            logs.value = [...newLogs, ...logs.value].slice(0, 500); // 限制最大500条
                            filterLogs();
                        }
                    } else {
                        // 完整更新，过滤掉心跳检测日志
                        const allLogs = result.data.logs || [];
                        logs.value = allLogs.filter(log => 
                            !log.message.includes('系统心跳检测') && 
                            log.source !== 'heartbeat'
                        );
                        
                        filterLogs();
                    }
                    
                    lastUpdate.value = new Date().toLocaleString();
                    lastTimestamp = result.data.timestamp;
                    isConnected.value = true;
                } else {
                    console.error('获取日志失败:', result.message);
                    isConnected.value = false;
                }
            } catch (error) {
                console.error('获取日志错误:', error);
                isConnected.value = false;
                ElMessage.error('获取日志失败: ' + error.message);
            } finally {
                loading.value = false;
            }
        };
        
        // 过滤日志
        const filterLogs = () => {
            let filtered = [...logs.value];
            
            // 按级别过滤
            if (selectedLevel.value) {
                filtered = filtered.filter(log => log.level === selectedLevel.value);
            }
            
            // 按内容搜索
            if (searchText.value) {
                const searchLower = searchText.value.toLowerCase();
                filtered = filtered.filter(log => 
                    log.message.toLowerCase().includes(searchLower)
                );
            }
            
            filteredLogs.value = filtered;
            
            // 滚动到顶部显示最新日志
            Vue.nextTick(() => {
                const container = document.querySelector('.logs-content');
                if (container) {
                    container.scrollTop = 0;
                }
            });
        };
        
        // 切换自动刷新
        const toggleAutoRefresh = () => {
            autoRefresh.value = !autoRefresh.value;
            
            if (autoRefresh.value) {
                startAutoRefresh();
                ElMessage.success('已开启自动刷新');
            } else {
                stopAutoRefresh();
                ElMessage.info('已停止自动刷新');
            }
        };
        
        // 开始自动刷新
        const startAutoRefresh = () => {
            stopAutoRefresh(); // 先停止现有的定时器
            refreshTimer = setInterval(() => {
                fetchLogs(false); // 改为完整获取，确保能看到新日志
            }, refreshInterval.value);
        };
        
        // 停止自动刷新
        const stopAutoRefresh = () => {
            if (refreshTimer) {
                clearInterval(refreshTimer);
                refreshTimer = null;
            }
        };
        
        
        // 清空日志
        const clearLogs = () => {
            ElMessageBox.confirm('确定要清空显示的日志吗？', '确认清空', {
                confirmButtonText: '确定',
                cancelButtonText: '取消',
                type: 'warning',
            }).then(() => {
                logs.value = [];
                filteredLogs.value = [];
                ElMessage.success('已清空日志显示');
            }).catch(() => {
                // 用户取消
            });
        };
        
        // 组件挂载时
        Vue.onMounted(() => {
            fetchLogs(false); // 首次加载完整日志
            
            if (autoRefresh.value) {
                startAutoRefresh();
            }
        });
        
        // 组件卸载时清理资源
        Vue.onUnmounted(() => {
            stopAutoRefresh();
        });
        
        return {
            // 数据
            logs,
            filteredLogs,
            loading,
            autoRefresh,
            isConnected,
            lastUpdate,
            refreshInterval,
            selectedLevel,
            searchText,
            
            // 方法
            formatTime,
            filterLogs,
            toggleAutoRefresh,
            clearLogs
        };
    }
};

// 等待DOM加载完成
document.addEventListener('DOMContentLoaded', function() {
    try {
        const app = createApp(LogsApp);
        app.use(ElementPlus);
        
        // 注册导航栏组件
        if (window.NavBar) {
            app.component('nav-bar', window.NavBar);
        }
        
        // ElementPlus 图标自动注册
        
        // 添加错误处理
        app.config.errorHandler = (err, vm, info) => {
            console.error('Vue Error:', err);
            console.error('Error Info:', info);
        };
        
        // 检查目标元素是否存在
        const targetElement = document.getElementById('app');
        if (!targetElement) {
            console.error('Target element #app not found!');
            return;
        }
        
        // 挂载应用
        app.mount('#app');
        console.log('日志页面 Vue 应用挂载成功');
    } catch (error) {
        console.error('Failed to mount logs Vue app:', error);
    }
});