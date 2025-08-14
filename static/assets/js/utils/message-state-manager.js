// 消息状态管理器 - 优化实时更新性能

class MessageStateManager {
    constructor() {
        this.messageMap = new Map(); // 使用Map提高查找性能
        this.pendingUpdates = new Map(); // 批量更新队列
        this.updateQueue = [];
        this.isProcessing = false;
        this.batchSize = 50; // 每批处理的消息数量
        this.debounceDelay = 100; // 防抖延迟
        
        // 绑定方法
        this.processBatch = this.processBatch.bind(this);
    }
    
    // 初始化消息列表
    initialize(messages) {
        this.messageMap.clear();
        messages.forEach(msg => {
            this.messageMap.set(msg.id, { ...msg });
        });
        console.log(`MessageStateManager initialized with ${messages.length} messages`);
    }
    
    // 添加单个消息
    addMessage(message) {
        this.messageMap.set(message.id, { ...message });
        this.queueUpdate({
            type: 'add',
            messageId: message.id,
            data: message
        });
    }
    
    // 更新消息状态
    updateMessageStatus(messageId, status, additionalData = {}) {
        const message = this.messageMap.get(messageId);
        if (message) {
            const updatedMessage = {
                ...message,
                status,
                ...additionalData,
                updatedAt: new Date().toISOString()
            };
            
            this.messageMap.set(messageId, updatedMessage);
            this.queueUpdate({
                type: 'update',
                messageId,
                data: updatedMessage,
                changes: { status, ...additionalData }
            });
        }
    }
    
    // 批量更新消息状态
    batchUpdateStatus(messageIds, status) {
        const updates = messageIds.map(id => {
            const message = this.messageMap.get(id);
            if (message) {
                const updatedMessage = { ...message, status };
                this.messageMap.set(id, updatedMessage);
                return {
                    type: 'update',
                    messageId: id,
                    data: updatedMessage,
                    changes: { status }
                };
            }
            return null;
        }).filter(Boolean);
        
        this.queueBatchUpdate(updates);
    }
    
    // 删除消息
    removeMessage(messageId) {
        if (this.messageMap.has(messageId)) {
            this.messageMap.delete(messageId);
            this.queueUpdate({
                type: 'remove',
                messageId
            });
        }
    }
    
    // 获取过滤后的消息列表
    getFilteredMessages(filters) {
        const messages = Array.from(this.messageMap.values());
        
        return messages.filter(msg => {
            // 状态过滤
            if (filters.status && msg.status !== filters.status) {
                return false;
            }
            
            // 广告过滤
            if (filters.is_ad !== null && msg.is_ad !== filters.is_ad) {
                return false;
            }
            
            // 搜索关键词过滤
            if (filters.search) {
                const content = (msg.filtered_content || msg.content || '').toLowerCase();
                if (!content.includes(filters.search.toLowerCase())) {
                    return false;
                }
            }
            
            return true;
        }).sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    }
    
    // 获取统计信息
    getStats() {
        const messages = Array.from(this.messageMap.values());
        return {
            total: messages.length,
            pending: messages.filter(m => m.status === 'pending').length,
            approved: messages.filter(m => m.status === 'approved').length,
            rejected: messages.filter(m => m.status === 'rejected').length,
            ads: messages.filter(m => m.is_ad).length
        };
    }
    
    // 队列更新
    queueUpdate(update) {
        this.updateQueue.push(update);
        this.debouncedProcess();
    }
    
    // 批量队列更新
    queueBatchUpdate(updates) {
        this.updateQueue.push(...updates);
        this.debouncedProcess();
    }
    
    // 防抖处理
    debouncedProcess() {
        if (this.debounceTimer) {
            clearTimeout(this.debounceTimer);
        }
        
        this.debounceTimer = setTimeout(() => {
            this.processBatch();
        }, this.debounceDelay);
    }
    
    // 批量处理更新
    async processBatch() {
        if (this.isProcessing || this.updateQueue.length === 0) {
            return;
        }
        
        this.isProcessing = true;
        
        try {
            const batch = this.updateQueue.splice(0, this.batchSize);
            
            // 按类型分组更新
            const groupedUpdates = this.groupUpdatesByType(batch);
            
            // 通知观察者
            this.notifyObservers(groupedUpdates);
            
            // 如果还有待处理的更新，继续处理
            if (this.updateQueue.length > 0) {
                setTimeout(this.processBatch, 0);
            }
        } catch (error) {
            console.error('批量处理更新失败:', error);
        } finally {
            this.isProcessing = false;
        }
    }
    
    // 按类型分组更新
    groupUpdatesByType(updates) {
        const grouped = {
            add: [],
            update: [],
            remove: []
        };
        
        updates.forEach(update => {
            if (grouped[update.type]) {
                grouped[update.type].push(update);
            }
        });
        
        return grouped;
    }
    
    // 观察者模式 - 通知UI更新
    observers = new Set();
    
    subscribe(observer) {
        this.observers.add(observer);
        return () => this.observers.delete(observer);
    }
    
    notifyObservers(updates) {
        this.observers.forEach(observer => {
            try {
                observer(updates);
            } catch (error) {
                console.error('通知观察者失败:', error);
            }
        });
    }
    
    // 内存清理
    cleanup() {
        this.messageMap.clear();
        this.updateQueue.length = 0;
        this.observers.clear();
        
        if (this.debounceTimer) {
            clearTimeout(this.debounceTimer);
        }
    }
}

// 创建全局实例
window.messageStateManager = new MessageStateManager();