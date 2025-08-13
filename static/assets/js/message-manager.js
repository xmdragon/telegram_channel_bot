/**
 * 全局消息管理器 - 防止重复消息
 * 用于统一管理页面中的成功/错误/警告消息，避免短时间内显示重复内容
 */
window.MessageManager = {
    lastMessages: new Map(),
    
    /**
     * 显示消息，如果短时间内显示过相同消息则跳过
     * @param {string} type - 消息类型: success, error, warning, info
     * @param {string} message - 消息内容
     * @param {number} duration - 消息显示持续时间（毫秒），默认3000
     * @param {object} options - Element Plus Message 的其他选项
     */
    show(type, message, duration = 3000, options = {}) {
        const key = `${type}:${message}`;
        const now = Date.now();
        
        // 检查是否在短时间内显示过相同消息
        if (this.lastMessages.has(key)) {
            const lastTime = this.lastMessages.get(key);
            if (now - lastTime < duration) {
                return; // 跳过重复消息
            }
        }
        
        this.lastMessages.set(key, now);
        
        // 定期清理过期的消息记录
        this.cleanup();
        
        // 显示消息
        if (typeof ElMessage !== 'undefined') {
            ElMessage[type]({
                message,
                duration,
                ...options
            });
        } else {
            // 降级处理，如果Element Plus不可用则使用console
            // console.log(`[${type.toUpperCase()}] ${message}`);
        }
    },
    
    /**
     * 成功消息
     */
    success(message, duration = 3000, options = {}) {
        this.show('success', message, duration, options);
    },
    
    /**
     * 错误消息
     */
    error(message, duration = 5000, options = {}) {
        this.show('error', message, duration, options);
    },
    
    /**
     * 警告消息
     */
    warning(message, duration = 4000, options = {}) {
        this.show('warning', message, duration, options);
    },
    
    /**
     * 信息消息
     */
    info(message, duration = 3000, options = {}) {
        this.show('info', message, duration, options);
    },
    
    /**
     * 清理过期的消息记录
     */
    cleanup() {
        const now = Date.now();
        const expireTime = 10000; // 10秒后清理记录
        
        for (const [key, time] of this.lastMessages.entries()) {
            if (now - time > expireTime) {
                this.lastMessages.delete(key);
            }
        }
    },
    
    /**
     * 清空所有消息记录
     */
    clear() {
        this.lastMessages.clear();
    }
};