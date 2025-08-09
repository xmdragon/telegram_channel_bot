// 主页面 Vue 应用 - Modern UI版本
const { createApp } = Vue;
const { ElMessage } = ElementPlus;

// 创建消息工具
const ModernUI = {
    Message: {
        success: (msg) => ElMessage.success(msg),
        error: (msg) => ElMessage.error(msg),
        warning: (msg) => ElMessage.warning(msg),
        info: (msg) => ElMessage.info(msg)
    }
};

const MainApp = {
    data() {
        return {
            loading: false,
            messages: [],
            selectedMessages: [],
            searchKeyword: '',
            stats: {
                total: { value: 0, label: '总消息' },
                pending: { value: 0, label: '待审核' },
                approved: { value: 0, label: '已批准' },
                rejected: { value: 0, label: '已拒绝' },
                ads: { value: 0, label: '广告消息' },
                channels: { value: 0, label: '监听频道' }
            },
            filters: {
                status: 'pending',
                is_ad: null
            },
            editDialog: {
                visible: false,
                messageId: null,
                content: '',
                originalMessage: null
            },
            mediaPreview: {
                show: false,
                url: null
            }
        }
    },
    
    computed: {
        filteredMessages() {
            let filtered = this.messages;
            
            // 按状态筛选
            if (this.filters.status) {
                filtered = filtered.filter(m => m.status === this.filters.status);
            }
            
            // 按广告状态筛选
            if (this.filters.is_ad !== null) {
                filtered = filtered.filter(m => m.is_ad === this.filters.is_ad);
            }
            
            // 按搜索关键词筛选
            if (this.searchKeyword) {
                const keyword = this.searchKeyword.toLowerCase();
                filtered = filtered.filter(m => 
                    m.content && m.content.toLowerCase().includes(keyword)
                );
            }
            
            return filtered;
        },
        
        allSelected() {
            return this.filteredMessages.length > 0 && 
                   this.selectedMessages.length === this.filteredMessages.length;
        }
    },
    
    mounted() {
        this.loadMessages();
        this.loadStats();
        
        // 定期刷新
        setInterval(() => {
            this.loadMessages();
            this.loadStats();
        }, 30000);
    },
    
    methods: {
        async loadMessages() {
            try {
                const response = await axios.get('/api/messages/', {
                    params: {
                        status: this.filters.status || 'pending',
                        limit: 100
                    }
                });
                
                if (response.data && response.data.messages) {
                    this.messages = response.data.messages;
                }
            } catch (error) {
                console.error('加载消息失败:', error);
                ModernUI.Message.error('加载消息失败');
            }
        },
        
        async loadStats() {
            try {
                const response = await axios.get('/api/messages/stats/overview');
                if (response.data) {
                    const data = response.data;
                    this.stats.total.value = data.total || 0;
                    this.stats.pending.value = data.pending || 0;
                    this.stats.approved.value = data.approved || 0;
                    this.stats.rejected.value = data.rejected || 0;
                    this.stats.ads.value = data.ads || 0;
                    this.stats.channels.value = data.channels || 0;
                }
            } catch (error) {
                console.error('加载统计失败:', error);
            }
        },
        
        toggleSelectAll() {
            if (this.allSelected) {
                this.selectedMessages = [];
            } else {
                this.selectedMessages = this.filteredMessages.map(m => m.id);
            }
        },
        
        toggleMessage(messageId) {
            const index = this.selectedMessages.indexOf(messageId);
            if (index > -1) {
                this.selectedMessages.splice(index, 1);
            } else {
                this.selectedMessages.push(messageId);
            }
        },
        
        isSelected(messageId) {
            return this.selectedMessages.includes(messageId);
        },
        
        async approveMessages() {
            if (this.selectedMessages.length === 0) {
                ModernUI.Message.warning('请先选择要批准的消息');
                return;
            }
            
            try {
                this.loading = true;
                const response = await axios.post('/api/messages/batch/approve', {
                    message_ids: this.selectedMessages
                });
                
                if (response.data.success) {
                    ModernUI.Message.success(`成功批准 ${this.selectedMessages.length} 条消息`);
                    this.selectedMessages = [];
                    await this.loadMessages();
                    await this.loadStats();
                }
            } catch (error) {
                console.error('批准失败:', error);
                ModernUI.Message.error('批准失败');
            } finally {
                this.loading = false;
            }
        },
        
        async rejectMessages() {
            if (this.selectedMessages.length === 0) {
                ModernUI.Message.warning('请先选择要拒绝的消息');
                return;
            }
            
            if (!confirm(`确定要拒绝这 ${this.selectedMessages.length} 条消息吗？`)) {
                return;
            }
            
            try {
                this.loading = true;
                const response = await axios.post('/api/messages/batch/reject', {
                    message_ids: this.selectedMessages
                });
                
                if (response.data.success) {
                    ModernUI.Message.success(`成功拒绝 ${this.selectedMessages.length} 条消息`);
                    this.selectedMessages = [];
                    await this.loadMessages();
                    await this.loadStats();
                }
            } catch (error) {
                console.error('拒绝失败:', error);
                ModernUI.Message.error('拒绝失败');
            } finally {
                this.loading = false;
            }
        },
        
        async deleteMessages() {
            if (this.selectedMessages.length === 0) {
                ModernUI.Message.warning('请先选择要删除的消息');
                return;
            }
            
            if (!confirm(`确定要永久删除这 ${this.selectedMessages.length} 条消息吗？此操作不可恢复！`)) {
                return;
            }
            
            try {
                this.loading = true;
                const response = await axios.post('/api/messages/batch/delete', {
                    message_ids: this.selectedMessages
                });
                
                if (response.data.success) {
                    ModernUI.Message.success(`成功删除 ${this.selectedMessages.length} 条消息`);
                    this.selectedMessages = [];
                    await this.loadMessages();
                    await this.loadStats();
                }
            } catch (error) {
                console.error('删除失败:', error);
                ModernUI.Message.error('删除失败');
            } finally {
                this.loading = false;
            }
        },
        
        handleStatClick(key) {
            // 根据点击的统计卡片设置过滤器
            switch(key) {
                case 'pending':
                    this.filters.status = 'pending';
                    this.filters.is_ad = null;
                    break;
                case 'approved':
                    this.filters.status = 'approved';
                    this.filters.is_ad = null;
                    break;
                case 'rejected':
                    this.filters.status = 'rejected';
                    this.filters.is_ad = null;
                    break;
                case 'ads':
                    this.filters.status = null;
                    this.filters.is_ad = true;
                    break;
                default:
                    this.filters.status = null;
                    this.filters.is_ad = null;
            }
            this.loadMessages();
        },
        
        openEditDialog(message) {
            this.editDialog.messageId = message.id;
            this.editDialog.content = message.content;
            this.editDialog.originalMessage = message;
            this.editDialog.visible = true;
        },
        
        async saveEdit() {
            try {
                const response = await axios.post('/api/messages/edit', {
                    message_id: this.editDialog.messageId,
                    content: this.editDialog.content
                });
                
                if (response.data.success) {
                    ModernUI.Message.success('消息已更新');
                    this.editDialog.visible = false;
                    await this.loadMessages();
                }
            } catch (error) {
                console.error('编辑失败:', error);
                ModernUI.Message.error('编辑失败');
            }
        },
        
        formatTime(timestamp) {
            if (!timestamp) return '';
            const date = new Date(timestamp);
            const now = new Date();
            const diff = (now - date) / 1000;
            
            if (diff < 60) return '刚刚';
            if (diff < 3600) return Math.floor(diff / 60) + ' 分钟前';
            if (diff < 86400) return Math.floor(diff / 3600) + ' 小时前';
            if (diff < 2592000) return Math.floor(diff / 86400) + ' 天前';
            
            return date.toLocaleDateString('zh-CN');
        },
        
        getStatusTag(status) {
            const statusMap = {
                'pending': { text: '待审核', type: 'warning' },
                'approved': { text: '已批准', type: 'success' },
                'rejected': { text: '已拒绝', type: 'danger' },
                'sent': { text: '已发送', type: 'info' }
            };
            return statusMap[status] || { text: status, type: 'info' };
        },
        
        openMediaPreview(url) {
            this.mediaPreview.show = true;
            this.mediaPreview.url = url;
        }
    }
};

// 导出组件供HTML使用
window.MainApp = MainApp;

// 等待DOM加载完成后挂载应用
document.addEventListener('DOMContentLoaded', function() {
    try {
        const app = createApp(MainApp);
        app.use(ElementPlus);
        
        // 注册导航栏组件（如果存在）
        if (window.NavBar) {
            app.component('nav-bar', window.NavBar);
        }
        
        app.mount('#app');
        console.log('Vue app mounted successfully');
    } catch (error) {
        console.error('Failed to mount Vue app:', error);
    }
});