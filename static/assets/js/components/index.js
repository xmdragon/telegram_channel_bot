// 主页面 JavaScript 组件

const { createApp } = Vue;
const { ElMessage } = ElementPlus;

// 主应用组件
const MainApp = {
    data() {
        return {
            loading: false,
            loadingMessage: '',
            statusMessage: '',
            statusType: 'success',
            systemStatus: '在线',
            messages: [],
            selectedMessages: [],
            stats: {
                total: { value: 0, label: '总消息' },
                pending: { value: 0, label: '待审核' },
                approved: { value: 0, label: '已批准' },
                rejected: { value: 0, label: '已拒绝' },
                ads: { value: 0, label: '广告消息' },
                channels: { value: 0, label: '监听频道' }
            },
            filters: {
                status: '',
                is_ad: null
            }
        }
    },
    
    mounted() {
        this.loadMessages();
        this.loadStats();
        // 定期刷新数据
        setInterval(() => {
            this.loadMessages();
            this.loadStats();
        }, 30000);
    },
    
    methods: {
        async loadMessages() {
            this.loading = true;
            this.loadingMessage = '正在加载消息数据...';
            
            try {
                const response = await axios.get('/api/messages/', {
                    params: this.filters
                });
                
                if (response.data.success) {
                    this.messages = response.data.messages;
                } else {
                    this.showError('加载消息失败');
                }
            } catch (error) {
                this.showError('加载消息失败: ' + (error.response?.data?.detail || error.message));
            } finally {
                this.loading = false;
            }
        },
        
        async loadStats() {
            try {
                const response = await axios.get('/api/stats/');
                if (response.data.success) {
                    const stats = response.data.stats;
                    this.stats.total.value = stats.total_messages || 0;
                    this.stats.pending.value = stats.pending_messages || 0;
                    this.stats.approved.value = stats.approved_messages || 0;
                    this.stats.rejected.value = stats.rejected_messages || 0;
                    this.stats.ads.value = stats.ad_messages || 0;
                    this.stats.channels.value = stats.active_channels || 0;
                }
            } catch (error) {
                console.error('加载统计信息失败:', error);
            }
        },
        
        async approveMessage(messageId) {
            try {
                const response = await axios.post(`/api/messages/${messageId}/approve`);
                if (response.data.success) {
                    this.showSuccess('消息批准成功');
                    this.loadMessages();
                } else {
                    this.showError('消息批准失败');
                }
            } catch (error) {
                this.showError('消息批准失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async rejectMessage(messageId) {
            try {
                const response = await axios.post(`/api/messages/${messageId}/reject`);
                if (response.data.success) {
                    this.showSuccess('消息拒绝成功');
                    this.loadMessages();
                } else {
                    this.showError('消息拒绝失败');
                }
            } catch (error) {
                this.showError('消息拒绝失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        async batchApprove() {
            if (this.selectedMessages.length === 0) {
                this.showError('请选择要批准的消息');
                return;
            }
            
            try {
                const response = await axios.post('/api/messages/batch-approve', {
                    message_ids: this.selectedMessages
                });
                
                if (response.data.success) {
                    this.showSuccess(`批量批准成功，共 ${this.selectedMessages.length} 条消息`);
                    this.selectedMessages = [];
                    this.loadMessages();
                } else {
                    this.showError('批量批准失败');
                }
            } catch (error) {
                this.showError('批量批准失败: ' + (error.response?.data?.detail || error.message));
            }
        },
        
        getStatusType(status) {
            const types = {
                'pending': 'warning',
                'approved': 'success',
                'rejected': 'danger',
                'auto_forwarded': 'info'
            };
            return types[status] || 'info';
        },
        
        getStatusText(status) {
            const texts = {
                'pending': '待审核',
                'approved': '已批准',
                'rejected': '已拒绝',
                'auto_forwarded': '自动转发'
            };
            return texts[status] || status;
        },
        
        formatTime(timeStr) {
            if (!timeStr) return '';
            const date = new Date(timeStr);
            return date.toLocaleString('zh-CN');
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
};

// 导出组件
window.MainApp = MainApp; 