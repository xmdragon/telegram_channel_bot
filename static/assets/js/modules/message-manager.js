// 消息管理模块

const MessageManager = {
    // 消息状态管理
    processingMessages: new Set(),
    
    // 加载消息列表
    async loadMessages(filters = {}, page = 1, pageSize = 20, append = false) {
        try {
            const params = new URLSearchParams({
                page: page.toString(),
                limit: pageSize.toString(),
                ...filters
            });

            // 移除空值参数
            for (const [key, value] of params.entries()) {
                if (value === '' || value === null || value === undefined) {
                    params.delete(key);
                }
            }

            const response = await axios.get(`${API_ENDPOINTS.messages.list}?${params}`);
            
            if (response.data.success) {
                return {
                    success: true,
                    data: response.data.data,
                    has_more: response.data.has_more,
                    total: response.data.total
                };
            } else {
                throw new Error(response.data.message || '加载消息失败');
            }
        } catch (error) {
            console.error('加载消息失败:', error);
            return {
                success: false,
                error: error.message || '网络错误'
            };
        }
    },

    // 批量审核消息
    async batchApprove(messageIds) {
        if (!messageIds || messageIds.length === 0) {
            return { success: false, error: '请选择要发布的消息' };
        }

        try {
            // 添加到处理中的消息集合
            messageIds.forEach(id => this.processingMessages.add(id));

            const response = await axios.post(API_ENDPOINTS.messages.batchApprove, {
                message_ids: messageIds
            });

            if (response.data.success) {
                return {
                    success: true,
                    data: response.data.data
                };
            } else {
                throw new Error(response.data.message || '批量发布失败');
            }
        } catch (error) {
            console.error('批量发布失败:', error);
            return {
                success: false,
                error: error.message || '网络错误'
            };
        } finally {
            // 从处理中的消息集合移除
            messageIds.forEach(id => this.processingMessages.delete(id));
        }
    },

    // 批量拒绝消息
    async batchReject(messageIds) {
        if (!messageIds || messageIds.length === 0) {
            return { success: false, error: '请选择要拒绝的消息' };
        }

        try {
            messageIds.forEach(id => this.processingMessages.add(id));

            const response = await axios.post(API_ENDPOINTS.messages.batchReject, {
                message_ids: messageIds
            });

            if (response.data.success) {
                return {
                    success: true,
                    data: response.data.data
                };
            } else {
                throw new Error(response.data.message || '批量拒绝失败');
            }
        } catch (error) {
            console.error('批量拒绝失败:', error);
            return {
                success: false,
                error: error.message || '网络错误'
            };
        } finally {
            messageIds.forEach(id => this.processingMessages.delete(id));
        }
    },

    // 检查消息是否正在处理
    isProcessing(messageId) {
        return this.processingMessages.has(messageId);
    },

    // 清除所有处理状态
    clearProcessingStates() {
        this.processingMessages.clear();
    }
};

// 导出模块
if (typeof module !== 'undefined' && module.exports) {
    module.exports = MessageManager;
} else {
    window.MessageManager = MessageManager;
}