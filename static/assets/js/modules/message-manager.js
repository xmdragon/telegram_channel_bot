/**
 * 消息管理模块
 * 处理消息的增删改查操作
 */

const MessageModule = {
    // 加载消息列表
    async loadMessages(filters = {}, append = false) {
        try {
            // 计算页码
            const currentPage = append ? Math.floor((filters.currentCount || 0) / 50) + 1 : 1;
            
            const params = {
                page: currentPage,
                size: 50
            };
            
            if (filters.status) params.status = filters.status;
            if (filters.is_ad !== null && filters.is_ad !== undefined) params.is_ad = filters.is_ad;
            if (filters.searchKeyword && filters.searchKeyword.trim()) {
                params.search = filters.searchKeyword.trim();
            }
            
            const response = await axios.get('/api/messages/', { params });
            
            // API直接返回数据，不包装在success字段中
            if (response.data && response.data.messages) {
                const messages = response.data.messages || [];
                const hasMore = messages.length === params.size;
                
                return {
                    messages,
                    hasMore,
                    success: true
                };
            }
            
            throw new Error('加载消息失败');
        } catch (error) {
            // console.error('加载消息失败:', error);
            MessageManager.error('加载消息失败: ' + (error.message || '未知错误'));
            return {
                messages: [],
                hasMore: false,
                success: false,
                error: error.message
            };
        }
    },
    
    // 批准消息
    async approveMessages(messageIds) {
        if (!messageIds || messageIds.length === 0) {
            MessageManager.warning('请选择要批准的消息');
            return { success: false };
        }
        
        try {
            const response = await axios.post('/api/messages/batch-approve', {
                message_ids: messageIds
            });
            
            // API返回200就是成功
            if (response.status === 200) {
                MessageManager.success(`成功批准 ${messageIds.length} 条消息`);
                return { success: true, data: response.data };
            }
            
            throw new Error('批准失败');
        } catch (error) {
            // console.error('批准消息失败:', error);
            MessageManager.error('批准失败: ' + (error.response?.data?.detail || error.message));
            return { success: false, error: error.message };
        }
    },
    
    // 拒绝消息
    async rejectMessages(messageIds) {
        if (!messageIds || messageIds.length === 0) {
            MessageManager.warning('请选择要拒绝的消息');
            return { success: false };
        }
        
        try {
            const response = await axios.post('/api/messages/batch-reject', {
                message_ids: messageIds
            });
            
            // API返回200就是成功
            if (response.status === 200) {
                MessageManager.success(`成功拒绝 ${messageIds.length} 条消息`);
                return { success: true, data: response.data };
            }
            
            throw new Error('拒绝失败');
        } catch (error) {
            // console.error('拒绝消息失败:', error);
            MessageManager.error('拒绝失败: ' + (error.response?.data?.detail || error.message));
            return { success: false, error: error.message };
        }
    },
    
    // 删除消息
    async deleteMessages(messageIds) {
        if (!messageIds || messageIds.length === 0) {
            MessageManager.warning('请选择要删除的消息');
            return { success: false };
        }
        
        if (!confirm(`确定要删除 ${messageIds.length} 条消息吗？此操作不可恢复。`)) {
            return { success: false };
        }
        
        try {
            const response = await axios.post('/api/messages/batch-delete', {
                message_ids: messageIds
            });
            
            // API返回200就是成功
            if (response.status === 200) {
                MessageManager.success(`成功删除 ${messageIds.length} 条消息`);
                return { success: true, data: response.data };
            }
            
            throw new Error('删除失败');
        } catch (error) {
            // console.error('删除消息失败:', error);
            MessageManager.error('删除失败: ' + (error.response?.data?.detail || error.message));
            return { success: false, error: error.message };
        }
    },
    
    // 编辑消息
    async updateMessage(messageId, content) {
        try {
            const response = await axios.put(`/api/messages/${messageId}`, {
                content: content
            });
            
            // API返回200就是成功
            if (response.status === 200) {
                MessageManager.success('消息已更新');
                return { success: true, data: response.data };
            }
            
            throw new Error('更新失败');
        } catch (error) {
            // console.error('更新消息失败:', error);
            MessageManager.error('更新失败: ' + (error.response?.data?.detail || error.message));
            return { success: false, error: error.message };
        }
    },
    
    // 标记为广告
    async markAsAd(messageId) {
        try {
            const response = await axios.post('/api/training/mark-ad', {
                message_id: messageId
            });
            
            if (response.data.success) {
                MessageManager.success('已标记为广告并加入训练样本');
                return { success: true, data: response.data };
            }
            
            throw new Error(response.data.message || '标记失败');
        } catch (error) {
            // console.error('标记广告失败:', error);
            MessageManager.error('标记失败: ' + (error.response?.data?.detail || error.message));
            return { success: false, error: error.message };
        }
    }
};

window.MessageModule = MessageModule;