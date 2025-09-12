/**
 * 状态管理模块 - 集中管理应用状态
 * 遵循Linus"好品味"原则：数据结构驱动程序设计
 */

const StateManager = {
    // 创建初始状态
    createInitialState() {
        return {
            // 加载状态
            loading: false,
            loadingMessage: '',
            isLoadingMore: false,
            isClearing: false,
            
            // 系统状态
            statusMessage: '',
            statusType: 'success',
            systemStatus: '在线',
            
            // WebSocket状态
            websocket: null,
            websocketConnected: false,
            
            // 数据状态
            messages: [],
            selectedMessages: [],
            searchKeyword: '',
            channelInfo: {},
            previousMessageIds: new Set(),
            
            // 分页状态
            currentPage: 1,
            pageSize: 20,
            hasMore: true,
            
            // 筛选状态
            filters: {
                status: 'pending',
                is_ad: null,
                source_channel: '',
                filter_reason: null
            },
            
            // 统计状态
            stats: {
                pending: { value: 0, label: '待审核' },
                approved: { value: 0, label: '已发布' },
                rejected: { value: 0, label: '已拒绝' }
            },
            
            // 操作状态
            processingMessages: new Set(),
            _isProcessingAction: false,
            refetchingMedia: {},
            
            // 对话框状态
            mediaPreview: {
                show: false,
                url: null
            },
            fileDetailsDialog: {
                visible: false,
                details: null
            },
            editDialog: {
                visible: false,
                messageId: null,
                filteredContent: '',
                originalMessage: null
            },
            
            // 虚拟滚动配置
            useVirtualScroll: true,
            virtualScrollThreshold: 100,
            messageItemHeight: 200,
            virtualListHeight: 600,
            
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
        };
    },
    
    // 状态重置方法
    resetLoadingState(state) {
        state.loading = false;
        state.isLoadingMore = false;
        state.isClearing = false;
        state.loadingMessage = '';
    },
    
    resetPaginationState(state) {
        state.currentPage = 1;
        state.hasMore = true;
        state.previousMessageIds.clear();
    },
    
    resetMessagesState(state) {
        state.messages = [];
        state.selectedMessages = [];
        this.resetPaginationState(state);
    },
    
    resetFiltersState(state) {
        state.filters = {
            status: 'pending',
            is_ad: null,
            source_channel: '',
            filter_reason: null
        };
        state.searchKeyword = '';
    },
    
    // 状态验证
    validateState(state) {
        const requiredFields = [
            'loading', 'messages', 'currentPage', 'pageSize', 
            'filters', 'stats', 'selectedMessages'
        ];
        
        for (const field of requiredFields) {
            if (!(field in state)) {
                console.error(`状态字段缺失: ${field}`);
                return false;
            }
        }
        
        return true;
    },
    
    // 状态转换工具
    transitionToLoading(state, message = '正在加载...') {
        state.loading = true;
        state.loadingMessage = message;
        state.statusMessage = '';
    },
    
    transitionToLoadingMore(state) {
        state.isLoadingMore = true;
    },
    
    transitionToProcessing(state, messageId) {
        state._isProcessingAction = true;
        if (messageId) {
            state.processingMessages.add(messageId);
        }
        // 设置全局标志
        if (typeof window !== 'undefined') {
            window._globalProcessingAction = true;
        }
    },
    
    transitionToIdle(state, messageId) {
        state.loading = false;
        state.isLoadingMore = false;
        state._isProcessingAction = false;
        state.loadingMessage = '';
        
        if (messageId) {
            state.processingMessages.delete(messageId);
        }
        
        // 清除全局标志
        if (typeof window !== 'undefined') {
            window._globalProcessingAction = false;
        }
    },
    
    // 消息操作工具
    addMessages(state, messages, append = false) {
        if (!append) {
            state.messages = messages;
        } else {
            // 避免重复
            const existingIds = new Set(state.messages.map(m => m.message_id));
            const newMessages = messages.filter(msg => !existingIds.has(msg.message_id));
            state.messages = [...state.messages, ...newMessages];
        }
        
        // 更新消息ID集合
        state.previousMessageIds = new Set(state.messages.map(msg => msg.message_id));
    },
    
    updateMessageStatus(state, messageId, status) {
        const message = state.messages.find(msg => msg.id === messageId);
        if (message) {
            message.status = status;
        }
    },
    
    removeMessage(state, messageId) {
        state.messages = state.messages.filter(msg => msg.id !== messageId);
        state.selectedMessages = state.selectedMessages.filter(id => id !== messageId);
        state.previousMessageIds.delete(messageId);
    },
    
    // 选择操作工具
    toggleMessageSelection(state, messageId) {
        const index = state.selectedMessages.indexOf(messageId);
        if (index === -1) {
            state.selectedMessages.push(messageId);
        } else {
            state.selectedMessages.splice(index, 1);
        }
    },
    
    clearSelection(state) {
        state.selectedMessages = [];
    },
    
    selectAllVisible(state) {
        state.selectedMessages = state.messages.map(msg => msg.id);
    },
    
    // 统计更新工具
    updateStats(state, newStats) {
        for (const [key, value] of Object.entries(newStats)) {
            if (state.stats[key]) {
                state.stats[key].value = value;
            }
        }
    },
    
    // 筛选操作工具
    updateFilter(state, key, value) {
        if (state.filters.hasOwnProperty(key)) {
            state.filters[key] = value;
        }
    },
    
    clearFilters(state) {
        this.resetFiltersState(state);
    },
    
    // 状态序列化（用于调试）
    serialize(state) {
        const serialized = { ...state };
        // 转换Set为Array
        serialized.previousMessageIds = Array.from(state.previousMessageIds);
        serialized.processingMessages = Array.from(state.processingMessages);
        return JSON.stringify(serialized, null, 2);
    },
    
    // 计算属性辅助函数
    getUniqueChannels(channelInfo) {
        if (!channelInfo) return {};
        
        const uniqueChannels = {};
        const seenChannels = new Set();
        
        for (const [id, info] of Object.entries(channelInfo)) {
            if (!seenChannels.has(id) && info.is_listening) {
                uniqueChannels[id] = info;
                seenChannels.add(id);
            }
        }
        
        return uniqueChannels;
    },
    
    getFilteredMessages(messages, filters) {
        if (!messages || !Array.isArray(messages)) return [];
        
        return messages.filter(message => {
            // 状态筛选
            if (filters.status && message.status !== filters.status) {
                return false;
            }
            
            // 广告筛选
            if (filters.is_ad !== null && message.is_ad !== filters.is_ad) {
                return false;
            }
            
            // 频道筛选
            if (filters.source_channel && message.source_channel_id !== filters.source_channel) {
                return false;
            }
            
            // 过滤原因筛选
            if (filters.filter_reason && message.filter_reason !== filters.filter_reason) {
                return false;
            }
            
            return true;
        });
    }
};

// 导出模块
if (typeof module !== 'undefined' && module.exports) {
    module.exports = StateManager;
} else {
    window.StateManager = StateManager;
}