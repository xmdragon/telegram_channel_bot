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

            const response = await axios.get(`/api/messages/?${params}`);
            
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

            const response = await axios.post('/api/messages/batch/approve', {
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

            const response = await axios.post('/api/messages/batch/reject', {
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
    },

    // 消息提示方法
    success(message) {
        if (typeof ElMessage !== 'undefined') {
            ElMessage.success(message);
        } else {
            console.log('SUCCESS:', message);
        }
    },

    error(message) {
        if (typeof ElMessage !== 'undefined') {
            ElMessage.error(message);
        } else {
            console.error('ERROR:', message);
        }
    },

    info(message) {
        if (typeof ElMessage !== 'undefined') {
            ElMessage.info(message);
        } else {
            console.info('INFO:', message);
        }
    },

    warning(message) {
        if (typeof ElMessage !== 'undefined') {
            ElMessage.warning(message);
        } else {
            console.warn('WARNING:', message);
        }
    },

    // 单个消息审核
    async approveSingleMessage(messageId) {
        if (!messageId) {
            return { success: false, error: '消息ID不能为空' };
        }

        try {
            this.processingMessages.add(messageId);

            const response = await axios.post(`/api/messages/${messageId}/approve`);
            
            if (response.data.success) {
                return {
                    success: true,
                    data: response.data.data
                };
            } else {
                throw new Error(response.data.message || '发布失败');
            }
        } catch (error) {
            console.error('发布消息失败:', error);
            return {
                success: false,
                error: error.message || '网络错误'
            };
        } finally {
            this.processingMessages.delete(messageId);
        }
    },

    // 单个消息拒绝
    async rejectSingleMessage(messageId) {
        if (!messageId) {
            return { success: false, error: '消息ID不能为空' };
        }

        try {
            this.processingMessages.add(messageId);

            const response = await axios.post(`/api/messages/${messageId}/reject`);
            
            if (response.data.success) {
                return {
                    success: true,
                    data: response.data.data
                };
            } else {
                throw new Error(response.data.message || '拒绝失败');
            }
        } catch (error) {
            console.error('拒绝消息失败:', error);
            return {
                success: false,
                error: error.message || '网络错误'
            };
        } finally {
            this.processingMessages.delete(messageId);
        }
    },

    // 批量删除消息
    async batchDelete(messageIds) {
        if (!messageIds || messageIds.length === 0) {
            return { success: false, error: '请选择要删除的消息' };
        }

        try {
            messageIds.forEach(id => this.processingMessages.add(id));

            const response = await axios.post('/api/messages/batch/delete', {
                message_ids: messageIds
            });

            if (response.data.success) {
                return {
                    success: true,
                    data: response.data.data
                };
            } else {
                throw new Error(response.data.message || '批量删除失败');
            }
        } catch (error) {
            console.error('批量删除失败:', error);
            return {
                success: false,
                error: error.message || '网络错误'
            };
        } finally {
            messageIds.forEach(id => this.processingMessages.delete(id));
        }
    }
};

// 导出模块
if (typeof module !== 'undefined' && module.exports) {
    module.exports = MessageManager;
} else {
    window.MessageManager = MessageManager;
}