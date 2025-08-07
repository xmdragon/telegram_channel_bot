/**
 * 消息管理模块
 * 处理消息列表、审核、批量操作等功能
 */
class MessageManager {
    constructor() {
        this.messages = [];
        this.selectedMessages = new Set();
        this.pagination = {
            current: 1,
            size: 20,
            total: 0
        };
        this.filters = {
            status: 'all',
            search: '',
            channel: 'all',
            isAd: 'all'
        };
    }

    // 加载消息列表
    async loadMessages(page = 1, pageSize = 20, filters = {}) {
        const params = {
            page: page,
            page_size: pageSize,
            ...filters
        };
        
        const result = await apiClient.get('/messages/list', { params });
        
        if (result.success) {
            this.messages = result.data.messages || [];
            this.pagination = {
                current: page,
                size: pageSize,
                total: result.data.total || 0
            };
            return this.messages;
        } else {
            throw new Error(result.message);
        }
    }

    // 审核消息
    async reviewMessage(messageId, action, reason = '') {
        const result = await apiClient.post(`/messages/${messageId}/${action}`, {
            reason: reason
        });
        
        if (result.success) {
            // 更新本地消息状态
            this._updateMessageStatus(messageId, action);
            return result.data;
        } else {
            throw new Error(result.message);
        }
    }

    // 批量审核消息
    async batchReviewMessages(messageIds, action, reason = '') {
        const result = await apiClient.post('/messages/batch_review', {
            message_ids: Array.from(messageIds),
            action: action,
            reason: reason
        });
        
        if (result.success) {
            // 更新本地消息状态
            messageIds.forEach(id => this._updateMessageStatus(id, action));
            this.selectedMessages.clear();
            return result.data;
        } else {
            throw new Error(result.message);
        }
    }

    // 编辑消息内容
    async editMessage(messageId, newContent) {
        const result = await apiClient.put(`/messages/${messageId}`, {
            content: newContent
        });
        
        if (result.success) {
            // 更新本地消息内容
            this._updateMessageContent(messageId, newContent);
            return result.data;
        } else {
            throw new Error(result.message);
        }
    }

    // 获取消息统计信息
    async getMessageStats() {
        const result = await apiClient.get('/messages/stats');
        
        if (result.success) {
            return result.data;
        } else {
            throw new Error(result.message);
        }
    }

    // 选择/取消选择消息
    toggleMessageSelection(messageId) {
        if (this.selectedMessages.has(messageId)) {
            this.selectedMessages.delete(messageId);
        } else {
            this.selectedMessages.add(messageId);
        }
    }

    // 全选/取消全选
    toggleSelectAll(selectAll = true) {
        if (selectAll) {
            this.messages.forEach(msg => this.selectedMessages.add(msg.id));
        } else {
            this.selectedMessages.clear();
        }
    }

    // 是否已选择消息
    isMessageSelected(messageId) {
        return this.selectedMessages.has(messageId);
    }

    // 获取选中的消息数量
    getSelectedCount() {
        return this.selectedMessages.size;
    }

    // 过滤消息
    filterMessages(messages, filters) {
        return messages.filter(message => {
            // 状态过滤
            if (filters.status && filters.status !== 'all' && message.status !== filters.status) {
                return false;
            }
            
            // 频道过滤
            if (filters.channel && filters.channel !== 'all' && message.source_channel !== filters.channel) {
                return false;
            }
            
            // 广告过滤
            if (filters.isAd && filters.isAd !== 'all') {
                const isAd = filters.isAd === 'true';
                if (message.is_ad !== isAd) {
                    return false;
                }
            }
            
            // 搜索过滤
            if (filters.search && filters.search.trim()) {
                const searchTerm = filters.search.toLowerCase();
                const content = (message.content || '').toLowerCase();
                const filteredContent = (message.filtered_content || '').toLowerCase();
                
                if (!content.includes(searchTerm) && !filteredContent.includes(searchTerm)) {
                    return false;
                }
            }
            
            return true;
        });
    }

    // 格式化消息用于显示
    formatMessageForDisplay(message) {
        return {
            ...message,
            statusText: this._getStatusText(message.status),
            statusClass: this._getStatusClass(message.status),
            displayContent: message.filtered_content || message.content || '',
            hasMedia: !!(message.media_type && message.media_url),
            mediaCount: message.media_group ? message.media_group.length : (message.media_type ? 1 : 0),
            timeFormatted: this._formatTime(message.created_at),
            channelDisplay: this._formatChannelName(message.source_channel)
        };
    }

    // 更新本地消息状态
    _updateMessageStatus(messageId, action) {
        const message = this.messages.find(msg => msg.id === messageId);
        if (message) {
            message.status = action === 'approve' ? 'approved' : 'rejected';
        }
    }

    // 更新本地消息内容
    _updateMessageContent(messageId, newContent) {
        const message = this.messages.find(msg => msg.id === messageId);
        if (message) {
            message.filtered_content = newContent;
        }
    }

    // 获取状态文本
    _getStatusText(status) {
        const statusMap = {
            'pending': '待审核',
            'approved': '已通过',
            'rejected': '已拒绝',
            'auto_forwarded': '自动转发'
        };
        return statusMap[status] || status;
    }

    // 获取状态样式类
    _getStatusClass(status) {
        const classMap = {
            'pending': 'warning',
            'approved': 'success',
            'rejected': 'danger',
            'auto_forwarded': 'info'
        };
        return classMap[status] || 'info';
    }

    // 格式化时间
    _formatTime(timeString) {
        if (!timeString) return '';
        try {
            const date = new Date(timeString);
            return date.toLocaleString('zh-CN');
        } catch (error) {
            return timeString;
        }
    }

    // 格式化频道名称
    _formatChannelName(channelId) {
        // 这里可以从频道管理器获取频道名称
        return channelId;
    }
}

// 全局消息管理器实例
window.messageManager = new MessageManager();