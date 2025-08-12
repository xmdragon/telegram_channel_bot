// 管理页面JavaScript组件
const { createApp } = Vue;
const { ElMessage, ElMessageBox } = ElementPlus;

const AdminApp = {
    data() {
        return {
            loading: false,
            loadingMessage: '',
            statusMessage: '',
            statusType: 'success',
            
            // 系统健康状态
            health: {
                status: 'unknown',
                database: 'unknown',
                version: 'unknown'
            },
            
            // 频道列表
            channels: [],
            channelSearchKeyword: '',
            
            // 添加频道对话框
            showAddChannelDialog: false,
            
            // 训练数据统计
            trainingStats: {
                totalSamples: 0,
                storageSize: 0
            }
        };
    },
    
    async mounted() {
        // 初始化权限检查 - 需要系统管理权限
        const isAuthorized = await authManager.initPageAuth('system.view_status');
        if (!isAuthorized) {
            return;
        }
        
        this.checkHealth();
        this.loadChannels();
        this.loadTrainingStats();
    },
    
    methods: {
        // 检查系统健康状态
        async checkHealth() {
            try {
                const response = await axios.get('/api/system/health');
                this.health = response.data;
                this.showMessage('系统状态已更新', 'success');
            } catch (error) {
                this.showMessage('获取系统状态失败', 'error');
            }
        },
        
        // 加载频道列表
        async loadChannels() {
            try {
                const response = await axios.get('/api/channels');
                this.channels = response.data.channels || [];
            } catch (error) {
                this.showMessage('加载频道失败', 'error');
            }
        },
        
        // 加载训练数据统计
        async loadTrainingStats() {
            try {
                const response = await axios.get('/api/training/stats');
                if (response.data) {
                    this.trainingStats = response.data;
                }
            } catch (error) {
                console.error('加载训练数据统计失败:', error);
            }
        },
        
        // 删除频道
        async deleteChannel(channelId) {
            try {
                await ElMessageBox.confirm('确定要删除这个频道吗？', '确认删除', {
                    confirmButtonText: '确定',
                    cancelButtonText: '取消',
                    type: 'warning'
                });
                
                // 检查权限
                if (!authManager.hasPermission('channels.delete')) {
                    this.showMessage('您没有删除频道的权限', 'error');
                    return;
                }
                
                await axios.delete(`/api/channels/${channelId}`);
                this.showMessage('频道已删除', 'success');
                this.loadChannels();
            } catch (error) {
                if (error !== 'cancel') {
                    this.showMessage('删除频道失败', 'error');
                }
            }
        },
        
        // 重启系统
        async restartSystem() {
            try {
                await ElMessageBox.confirm('确定要重启系统吗？', '确认重启', {
                    confirmButtonText: '确定',
                    cancelButtonText: '取消',
                    type: 'warning'
                });
                
                // 检查权限
                if (!authManager.hasPermission('system.restart')) {
                    this.showMessage('您没有重启系统的权限', 'error');
                    return;
                }
                
                this.loading = true;
                this.loadingMessage = '正在重启系统...';
                
                await axios.post('/api/system/restart');
                this.showMessage('系统重启命令已发送', 'success');
            } catch (error) {
                if (error !== 'cancel') {
                    this.showMessage('重启系统失败', 'error');
                }
            } finally {
                this.loading = false;
            }
        },
        
        // 备份数据
        async backupData() {
            try {
                // 检查权限
                if (!authManager.hasPermission('system.view_status')) {
                    this.showMessage('您没有备份数据的权限', 'error');
                    return;
                }
                
                this.loading = true;
                this.loadingMessage = '正在备份数据...';
                
                const response = await axios.post('/api/system/backup');
                this.showMessage('数据备份成功', 'success');
            } catch (error) {
                this.showMessage('备份数据失败', 'error');
            } finally {
                this.loading = false;
            }
        },
        
        // 清理缓存
        async clearCache() {
            try {
                await ElMessageBox.confirm('确定要清理缓存吗？', '确认清理', {
                    confirmButtonText: '确定',
                    cancelButtonText: '取消',
                    type: 'warning'
                });
                
                // 检查权限
                if (!authManager.hasPermission('system.view_status')) {
                    this.showMessage('您没有清理缓存的权限', 'error');
                    return;
                }
                
                await axios.post('/api/system/clear_cache');
                this.showMessage('缓存已清理', 'success');
            } catch (error) {
                if (error !== 'cancel') {
                    this.showMessage('清理缓存失败', 'error');
                }
            }
        },
        
        // 导出日志
        async exportLogs() {
            try {
                // 检查权限
                if (!authManager.hasPermission('system.view_logs')) {
                    this.showMessage('您没有导出日志的权限', 'error');
                    return;
                }
                
                const response = await axios.get('/api/system/export_logs', {
                    responseType: 'blob'
                });
                
                // 创建下载链接
                const url = window.URL.createObjectURL(new Blob([response.data]));
                const link = document.createElement('a');
                link.href = url;
                link.setAttribute('download', `logs_${new Date().toISOString()}.zip`);
                document.body.appendChild(link);
                link.click();
                link.remove();
                
                this.showMessage('日志导出成功', 'success');
            } catch (error) {
                this.showMessage('导出日志失败', 'error');
            }
        },
        
        // 获取频道类型文本
        getChannelTypeText(type) {
            const typeMap = {
                'source': '源频道',
                'target': '目标频道',
                'review': '审核群'
            };
            return typeMap[type] || type;
        },
        
        // 获取频道类型颜色
        getChannelTypeColor(type) {
            const colorMap = {
                'source': 'primary',
                'target': 'success',
                'review': 'warning'
            };
            return colorMap[type] || 'info';
        },
        
        // 编辑频道
        editChannel(channel) {
            this.showMessage('编辑功能开发中', 'info');
        },
        
        // 搜索频道
        searchChannels() {
            // 实现频道搜索逻辑
            this.loadChannels();
        },
        
        // 打开训练数据管理界面
        openTrainingManager() {
            window.open('/static/training_manager.html', '_blank');
        },
        
        // 格式化文件大小
        formatSize(bytes) {
            if (bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        },

        // 显示消息
        showMessage(message, type = 'info') {
            this.statusMessage = message;
            this.statusType = type;
            
            ElMessage({
                message: message,
                type: type,
                offset: 20,
                customClass: 'bottom-right-message'
            });
            
            setTimeout(() => {
                this.statusMessage = '';
            }, 3000);
        }
    }
};

// 创建并挂载应用
const app = createApp(AdminApp);
app.use(ElementPlus);
if (window.NavBar) {
    app.component('nav-bar', window.NavBar);
}
app.mount('#app');