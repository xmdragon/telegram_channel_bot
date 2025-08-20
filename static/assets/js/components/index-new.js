// 主页面 JavaScript 组件 - 重构后的精简版本

// 确保API配置可用，延迟解析避免加载时错误
let createApp, ElMessage;

// 延迟初始化函数
function initializeGlobals() {
    if (!createApp && window.Vue) createApp = window.Vue.createApp;
    if (!ElMessage && window.ElementPlus) ElMessage = window.ElementPlus.ElMessage;
}

// 主应用组件
const MainApp = {
    data() {
        return {
            // 基础状态
            loading: false,
            loadingMessage: '',
            statusMessage: '',
            statusType: 'success',
            systemStatus: '在线',
            
            // 消息数据
            messages: [],
            selectedMessages: [],
            searchKeyword: '',
            channelInfo: {},
            
            // 虚拟列表配置
            useVirtualScroll: true,
            virtualScrollThreshold: 100,
            messageItemHeight: 200,
            virtualListHeight: 600,
            
            // UI状态
            mediaPreview: {
                show: false,
                url: null
            },
            editDialog: {
                visible: false,
                messageId: null,
                filteredContent: '',
                originalMessage: null
            },
            
            // 统计数据
            stats: {
                total: { value: 0, label: '总消息' },
                pending: { value: 0, label: '待审核' },
                approved: { value: 0, label: '已发布' },
                rejected: { value: 0, label: '已拒绝' },
                ads: { value: 0, label: '广告消息' },
                duplicates: { value: 0, label: '重复消息' },
                chats: { value: 0, label: '聊天消息' }
            },
            
            // 过滤器
            filters: {
                status: 'pending',
                is_ad: null,
                source_channel: '',
                filter_reason: null,
                _show_duplicates: false
            },
            
            // 分页
            currentPage: 1,
            pageSize: 20,
            hasMore: true,
            isLoadingMore: false,
            
            // 权限控制
            buttonVisibility: {
                edit: true,
                approve: true,
                reject: true,
                markAsAd: true,
                markAsTail: true,
                executeFilter: true,
                refetchMedia: true
            }
        }
    },
    
    computed: {
        // 去重的频道列表
        uniqueChannels() {
            if (!this.channelInfo) return {};
            
            const uniqueChannels = {};
            const seenChannels = new Set();
            
            for (const [key, channelData] of Object.entries(this.channelInfo)) {
                if (channelData.type !== 'source') continue;
                
                const channelId = channelData.id;
                if (seenChannels.has(channelId)) continue;
                
                seenChannels.add(channelId);
                uniqueChannels[channelId] = channelData;
            }
            
            return uniqueChannels;
        },
        
        // 过滤后的消息列表
        filteredMessages() {
            if (!this.messages || !Array.isArray(this.messages)) {
                return [];
            }
            
            // 重复消息模式
            if (this.filters._show_duplicates) {
                return this.messages.filter(msg => {
                    const hasDuplicateId = !!(msg.duplicate_original_id);
                    const hasDuplicateInfo = !!(msg.duplicate_info);
                    const hasFilterReason = !!(msg.filter_reason && msg.filter_reason.toLowerCase().includes('duplicate'));
                    const hasRejectReason = !!(msg.reject_reason && (
                        msg.reject_reason.includes('重复') || 
                        msg.reject_reason.toLowerCase().includes('duplicate')
                    ));
                    
                    return hasDuplicateId || hasDuplicateInfo || hasFilterReason || hasRejectReason;
                });
            }
            
            return [...this.messages];
        },
        
        // 是否全选
        allSelected() {
            if (!this.filteredMessages || this.filteredMessages.length === 0) {
                return false;
            }
            const selectableMessages = this.filteredMessages.filter(msg => msg.status === 'pending');
            return selectableMessages.length > 0 && 
                   selectableMessages.every(msg => this.selectedMessages.includes(msg.id));
        }
    },
    
    watch: {
        'filters.status': function(newVal) {
            if (newVal === null) {
                this.filters.status = 'pending';
            }
        },
        'filters.source_channel': function() {
            this.loadMessages();
        }
    },
    
    async mounted() {
        try {
            // 权限检查
            const isAuthorized = await authManager.initPageAuth('messages.view');
            if (!isAuthorized) return;
            
            await this.initializePermissions();
            
            // 初始化WebSocket
            if (window.WebSocketManager) {
                window.WebSocketManager.init({
                    onMessage: this.handleWebSocketMessage,
                    onStatusChange: this.handleWebSocketStatus,
                    onError: this.handleWebSocketError
                });
            }
            
            // 检查刷新参数
            const urlParams = new URLSearchParams(window.location.search);
            if (urlParams.get('refresh') === 'true') {
                window.history.replaceState({}, document.title, window.location.pathname);
                this.messages = [];
            }
            
            // 加载初始数据
            await Promise.all([
                this.loadMessages(),
                this.loadChannelInfo(),
                this.loadStats()
            ]);
            
        } catch (error) {
            console.error('页面初始化失败:', error);
            if (window.UIHandlers) {
                window.UIHandlers.showError('页面初始化失败: ' + error.message);
            }
        }
    },
    
    beforeUnmount() {
        // 清理WebSocket连接
        if (window.WebSocketManager) {
            window.WebSocketManager.close();
        }
    },
    
    methods: {
        // 权限初始化
        async initializePermissions() {
            try {
                // 使用authManager的权限检查方法
                this.buttonVisibility = {
                    edit: authManager.hasPermission('messages.edit'),
                    approve: authManager.hasPermission('messages.approve'),
                    reject: authManager.hasPermission('messages.reject'),
                    markAsAd: authManager.hasPermission('messages.mark_as_ad'),
                    markAsTail: authManager.hasPermission('messages.mark_as_tail'),
                    executeFilter: authManager.hasPermission('messages.filter'),
                    refetchMedia: authManager.hasPermission('messages.refetch_media')
                };
            } catch (error) {
                console.error('权限初始化失败:', error);
                // 默认权限（如果权限检查失败）
                this.buttonVisibility = {
                    edit: true,
                    approve: true,
                    reject: true,
                    markAsAd: true,
                    markAsTail: true,
                    executeFilter: true,
                    refetchMedia: true
                };
            }
        },
        
        // 加载消息
        async loadMessages(append = false) {
            if (this.loading && !append) return;
            
            try {
                this.loading = !append;
                this.loadingMessage = append ? '加载更多...' : '加载消息中...';
                
                const result = await window.MessageManager.loadMessages(
                    this.filters, 
                    append ? this.currentPage + 1 : 1, 
                    this.pageSize
                );
                
                if (result.success) {
                    if (append) {
                        this.messages.push(...result.data);
                        this.currentPage++;
                    } else {
                        this.messages = result.data;
                        this.currentPage = 1;
                    }
                    
                    this.hasMore = result.has_more;
                } else {
                    throw new Error(result.error);
                }
                
            } catch (error) {
                console.error('加载消息失败:', error);
                if (window.UIHandlers) {
                    window.UIHandlers.showError('加载消息失败: ' + error.message);
                }
            } finally {
                this.loading = false;
                this.isLoadingMore = false;
            }
        },
        
        // 加载频道信息
        async loadChannelInfo() {
            try {
                const response = await axios.get('/api/messages/channel-info');
                if (response.data.success) {
                    this.channelInfo = response.data.data;
                }
            } catch (error) {
                console.error('加载频道信息失败:', error);
            }
        },
        
        // 加载统计数据
        async loadStats() {
            try {
                const response = await axios.get('/api/messages/stats/overview');
                if (response.data.success) {
                    const stats = response.data.data;
                    this.stats.total.value = stats.total || 0;
                    this.stats.pending.value = stats.pending || 0;
                    this.stats.approved.value = stats.approved || 0;
                    this.stats.rejected.value = stats.rejected || 0;
                    this.stats.ads.value = stats.ads || 0;
                    this.stats.duplicates.value = stats.duplicates || 0;
                    this.stats.chats.value = stats.chats || 0;
                }
            } catch (error) {
                console.error('加载统计数据失败:', error);
            }
        },
        
        // WebSocket消息处理
        handleWebSocketMessage(data) {
            switch (data.type) {
                case 'message_update':
                    this.handleMessageUpdate(data.data);
                    break;
                case 'stats_update':
                    this.handleStatsUpdate(data.data);
                    break;
                case 'system_status':
                    this.systemStatus = data.status;
                    break;
            }
        },
        
        // WebSocket状态处理
        handleWebSocketStatus(connected) {
            this.websocketConnected = connected;
        },
        
        // WebSocket错误处理
        handleWebSocketError(error) {
            console.error('WebSocket错误:', error);
        },
        
        // 消息更新处理
        handleMessageUpdate(updatedMessage) {
            const index = this.messages.findIndex(msg => msg.id === updatedMessage.id);
            if (index !== -1) {
                this.messages.splice(index, 1, updatedMessage);
            }
        },
        
        // 统计更新处理
        handleStatsUpdate(newStats) {
            Object.assign(this.stats, newStats);
        },
        
        // 工具方法 - 使用外部模块
        formatTime: window.DataUtils?.formatTime || (time => time),
        getStatusTag: window.DataUtils?.getStatusTag || (status => ({ text: status, type: 'default' })),
        getChannelDisplayName: window.DataUtils?.getChannelDisplayName || (channel => '未知频道'),
        getMediaTypeIcon: window.DataUtils?.getMediaTypeIcon || (type => '📎'),
        handleImageError: window.DataUtils?.handleImageError || (() => {}),
        
        // UI交互方法
        openMediaPreview(url) {
            if (window.UIHandlers) {
                window.UIHandlers.openMediaPreview(url);
            }
        },
        
        showSuccess(message) {
            if (window.UIHandlers) {
                window.UIHandlers.showSuccess(message);
            }
        },
        
        showError(message) {
            if (window.UIHandlers) {
                window.UIHandlers.showError(message);
            }
        }
    }
};

// 页面加载完成后初始化应用
document.addEventListener('DOMContentLoaded', function() {
    // 确保所有依赖已加载
    if (typeof Vue !== 'undefined' && typeof ElementPlus !== 'undefined') {
        initializeGlobals();
        
        const app = createApp(MainApp);
        app.use(ElementPlus);
        app.mount('#app');
    } else {
        console.error('Vue或ElementPlus未加载');
    }
});

// 导出模块
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { MainApp, initializeGlobals };
} else {
    window.MainApp = MainApp;
    window.initializeGlobals = initializeGlobals;
}