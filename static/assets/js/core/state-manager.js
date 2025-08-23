/**
 * 统一状态管理器 - Linus式架构核心
 * 
 * 核心理念：
 * - 单一数据源，消除数据重复
 * - 发布订阅模式，消除轮询特殊情况
 * - 智能缓存，按需更新
 * 
 * "好品味就是消除特殊情况，让所有组件用同一套逻辑"
 */

class StateManager {
    constructor() {
        // 防止重复实例化
        if (StateManager.instance) {
            return StateManager.instance;
        }
        
        this.state = new Map();
        this.subscribers = new Map();
        this.cache = new Map();
        this.cacheExpiry = new Map();
        
        // 默认缓存时间（毫秒）
        this.defaultTTL = 30 * 1000; // 30秒
        
        StateManager.instance = this;
    }
    
    /**
     * 订阅状态变化
     * @param {string} key - 状态键
     * @param {function} callback - 回调函数
     * @param {object} options - 选项
     */
    subscribe(key, callback, options = {}) {
        if (!this.subscribers.has(key)) {
            this.subscribers.set(key, new Set());
        }
        
        const subscription = {
            id: this._generateId(),
            callback,
            immediate: options.immediate !== false, // 默认立即执行
            component: options.component || null
        };
        
        this.subscribers.get(key).add(subscription);
        
        // 立即返回缓存数据
        if (subscription.immediate && this.has(key)) {
            setTimeout(() => callback(this.get(key)), 0);
        }
        
        return subscription.id;
    }
    
    /**
     * 取消订阅
     * @param {string} key - 状态键
     * @param {string} subscriptionId - 订阅ID
     */
    unsubscribe(key, subscriptionId) {
        const subscribers = this.subscribers.get(key);
        if (subscribers) {
            for (const subscription of subscribers) {
                if (subscription.id === subscriptionId) {
                    subscribers.delete(subscription);
                    break;
                }
            }
            
            // 清理空的订阅集合
            if (subscribers.size === 0) {
                this.subscribers.delete(key);
            }
        }
    }
    
    /**
     * 设置状态并通知订阅者
     * @param {string} key - 状态键
     * @param {any} value - 状态值
     * @param {object} options - 选项
     */
    setState(key, value, options = {}) {
        const oldValue = this.state.get(key);
        const hasChanged = !this._deepEqual(oldValue, value);
        
        // 只有数据真正变化才更新
        if (!hasChanged && !options.force) {
            return;
        }
        
        this.state.set(key, value);
        
        // 更新缓存
        this.cache.set(key, {
            data: value,
            timestamp: Date.now()
        });
        
        // 设置过期时间
        const ttl = options.ttl || this.defaultTTL;
        this.cacheExpiry.set(key, Date.now() + ttl);
        
        // 通知订阅者
        this._notifySubscribers(key, value, oldValue);
        
    }
    
    /**
     * 获取状态
     * @param {string} key - 状态键
     * @param {any} defaultValue - 默认值
     */
    get(key, defaultValue = null) {
        // 检查缓存是否过期
        if (this._isCacheExpired(key)) {
            this.state.delete(key);
            this.cache.delete(key);
            this.cacheExpiry.delete(key);
            return defaultValue;
        }
        
        return this.state.get(key) || defaultValue;
    }
    
    /**
     * 检查状态是否存在
     * @param {string} key - 状态键
     */
    has(key) {
        return this.state.has(key) && !this._isCacheExpired(key);
    }
    
    /**
     * 清除状态
     * @param {string} key - 状态键
     */
    clear(key) {
        this.state.delete(key);
        this.cache.delete(key);
        this.cacheExpiry.delete(key);
        
        // 通知订阅者
        this._notifySubscribers(key, null, null);
    }
    
    /**
     * 批量更新状态
     * @param {object} updates - 更新对象
     */
    batchUpdate(updates) {
        const changedKeys = [];
        
        for (const [key, value] of Object.entries(updates)) {
            const oldValue = this.state.get(key);
            const hasChanged = !this._deepEqual(oldValue, value);
            
            if (hasChanged) {
                this.state.set(key, value);
                this.cache.set(key, {
                    data: value,
                    timestamp: Date.now()
                });
                this.cacheExpiry.set(key, Date.now() + this.defaultTTL);
                changedKeys.push({ key, value, oldValue });
            }
        }
        
        // 批量通知
        changedKeys.forEach(({ key, value, oldValue }) => {
            this._notifySubscribers(key, value, oldValue);
        });
        
    }
    
    /**
     * 获取缓存信息
     */
    getCacheInfo() {
        const info = {};
        for (const [key, cache] of this.cache.entries()) {
            const expiry = this.cacheExpiry.get(key);
            info[key] = {
                size: JSON.stringify(cache.data).length,
                timestamp: cache.timestamp,
                expiry: expiry,
                expired: this._isCacheExpired(key),
                age: Date.now() - cache.timestamp
            };
        }
        return info;
    }
    
    /**
     * 清理过期缓存
     */
    cleanupExpiredCache() {
        let cleanedCount = 0;
        for (const key of this.cache.keys()) {
            if (this._isCacheExpired(key)) {
                this.clear(key);
                cleanedCount++;
            }
        }
        
        if (cleanedCount > 0) {
        }
        
        return cleanedCount;
    }
    
    // ========== 私有方法 ==========
    
    /**
     * 通知订阅者
     */
    _notifySubscribers(key, newValue, oldValue) {
        const subscribers = this.subscribers.get(key);
        if (!subscribers) return;
        
        let notifiedCount = 0;
        for (const subscription of subscribers) {
            try {
                subscription.callback(newValue, oldValue);
                notifiedCount++;
            } catch (error) {
                // 忽略订阅者回调错误，避免影响其他订阅者
            }
        }
        
        if (notifiedCount > 0) {
        }
    }
    
    /**
     * 检查缓存是否过期
     */
    _isCacheExpired(key) {
        const expiry = this.cacheExpiry.get(key);
        return expiry && Date.now() > expiry;
    }
    
    /**
     * 深度比较对象
     */
    _deepEqual(a, b) {
        if (a === b) return true;
        if (a == null || b == null) return false;
        if (typeof a !== typeof b) return false;
        
        if (typeof a === 'object') {
            const keysA = Object.keys(a);
            const keysB = Object.keys(b);
            
            if (keysA.length !== keysB.length) return false;
            
            for (const key of keysA) {
                if (!keysB.includes(key)) return false;
                if (!this._deepEqual(a[key], b[key])) return false;
            }
            
            return true;
        }
        
        return false;
    }
    
    /**
     * 生成唯一ID
     */
    _generateId() {
        return 'sub_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now();
    }
}

// 创建全局单例
if (typeof window !== 'undefined') {
    window.StateManager = window.StateManager || new StateManager();
    
    // 自动清理过期缓存（每分钟）
    setInterval(() => {
        window.StateManager.cleanupExpiredCache();
    }, 60000);
    
    // 页面卸载时清理资源
    window.addEventListener('beforeunload', () => {
        window.StateManager.state.clear();
        window.StateManager.subscribers.clear();
        window.StateManager.cache.clear();
        window.StateManager.cacheExpiry.clear();
    });
}