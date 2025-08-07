const { createApp } = Vue;
const { ElMessage } = ElementPlus;

const app = createApp({
    data() {
        return {
            loading: false,
            loadingMessage: '',
            statusMessage: '',
            statusType: 'success',
            adminStatus: '在线',
            health: {
                status: 'healthy',
                database: 'connected',
                version: 'v1.0.0',
                timestamp: new Date().toLocaleString()
            },
            channels: [],
            filterRules: [],
            showAddChannelDialog: false,
            showAddRuleDialog: false,
            channelSearchKeyword: ''
        }
    },
    
    mounted() {
        this.loadAdminData();
    },
    
    methods: {
        async loadAdminData() {
            this.loading = true;
            this.loadingMessage = '正在加载管理数据...';
            
            try {
                // 加载健康状态
                await this.checkHealth();
                
                // 加载频道列表
                await this.loadChannels();
                
                // 加载过滤规则
                const rulesResponse = await axios.get('/api/admin/filter-rules');
                if (rulesResponse.data.success) {
                    this.filterRules = rulesResponse.data.rules;
                }
                
            } catch (error) {
                console.error('加载管理数据失败:', error);
                this.loadMockData();
            } finally {
                this.loading = false;
            }
        },
        
        loadMockData() {
            // 模拟数据
            this.channels = [
                { id: 1, channel_name: '测试频道1', channel_id: '@test1', channel_type: 'source', is_active: true },
                { id: 2, channel_name: '测试频道2', channel_id: '@test2', channel_type: 'source', is_active: false }
            ];
            
            this.filterRules = [
                { id: 1, pattern: '广告', rule_type: 'keyword', is_active: true, description: '过滤广告内容' },
                { id: 2, pattern: '推广', rule_type: 'keyword', is_active: true, description: '过滤推广内容' }
            ];
        },
        
        async checkHealth() {
            try {
                const response = await axios.get('/api/admin/health');
                if (response.data.success) {
                    this.health = response.data.health;
                }
            } catch (error) {
                console.error('检查健康状态失败:', error);
            }
        },
        
        getChannelTypeColor(type) {
            const colors = {
                'source': 'primary',
                'target': 'success',
                'review': 'warning'
            };
            return colors[type] || 'info';
        },
        
        getChannelTypeText(type) {
            const texts = {
                'source': '源频道',
                'target': '目标频道',
                'review': '审核频道'
            };
            return texts[type] || type;
        },
        
        async editChannel(channel) {
            try {
                // 这里可以实现编辑频道的弹窗或跳转到编辑页面
                // 暂时显示频道信息
                this.showSuccess(`编辑频道: ${channel.channel_name} (${channel.channel_id})`);
                
                // 可以添加编辑逻辑，比如打开编辑弹窗
                // this.editDialogVisible = true;
                // this.editingChannel = channel;
            } catch (error) {
                this.showError('编辑频道失败: ' + error.message);
            }
        },
        
        async deleteChannel(channelId) {
            try {
                if (confirm('确定要删除这个频道吗？')) {
                    const response = await axios.delete(`/api/admin/channels/${channelId}`);
                    if (response.data.message) {
                        this.showSuccess(response.data.message);
                        // 重新加载频道列表
                        await this.loadChannels();
                    }
                }
            } catch (error) {
                this.showError('删除频道失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async loadChannels() {
            try {
                const params = {};
                if (this.channelSearchKeyword) {
                    params.search = this.channelSearchKeyword;
                }
                const response = await axios.get('/api/admin/channels', { params });
                if (response.data.success) {
                    this.channels = response.data.channels;
                }
            } catch (error) {
                this.showError('加载频道失败: ' + error.message);
            }
        },
        
        async searchChannels() {
            await this.loadChannels();
        },
        
        async editRule(rule) {
            try {
                // 这里可以实现编辑规则的弹窗或跳转到编辑页面
                this.showSuccess(`编辑规则: ${rule.pattern} (${rule.rule_type})`);
                
                // 可以添加编辑逻辑，比如打开编辑弹窗
                // this.editRuleDialogVisible = true;
                // this.editingRule = rule;
            } catch (error) {
                this.showError('编辑规则失败: ' + error.message);
            }
        },
        
        async deleteRule(ruleId) {
            try {
                if (confirm('确定要删除这个过滤规则吗？')) {
                    const response = await axios.delete(`/api/admin/filter-rules/${ruleId}`);
                    if (response.data.message) {
                        this.showSuccess(response.data.message);
                        // 重新加载规则列表
                        await this.loadFilterRules();
                    }
                }
            } catch (error) {
                this.showError('删除规则失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async restartSystem() {
            try {
                const response = await axios.post('/api/admin/restart');
                if (response.data.success) {
                    this.showSuccess('系统重启成功');
                } else {
                    this.showError('系统重启失败');
                }
            } catch (error) {
                this.showError('系统重启失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async backupData() {
            try {
                const response = await axios.post('/api/admin/backup');
                if (response.data.success) {
                    this.showSuccess('数据备份成功');
                } else {
                    this.showError('数据备份失败');
                }
            } catch (error) {
                this.showError('数据备份失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async clearCache() {
            try {
                const response = await axios.post('/api/admin/clear-cache');
                if (response.data.success) {
                    this.showSuccess('缓存清理成功');
                } else {
                    this.showError('缓存清理失败');
                }
            } catch (error) {
                this.showError('缓存清理失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async exportLogs() {
            try {
                const response = await axios.post('/api/admin/export-logs');
                if (response.data.success) {
                    this.showSuccess('日志导出成功');
                } else {
                    this.showError('日志导出失败');
                }
            } catch (error) {
                this.showError('日志导出失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        showSuccess(message) {
            this.statusMessage = message;
            this.statusType = 'success';
            setTimeout(() => {
                this.statusMessage = '';
            }, 3000);
        },
        
        showError(message) {
            this.statusMessage = message;
            this.statusType = 'error';
            setTimeout(() => {
                this.statusMessage = '';
            }, 5000);
        }
    }
});

app.use(ElementPlus);
// 注册导航栏组件
if (window.NavBar) {
    app.component('nav-bar', window.NavBar);
}
app.mount('#app');