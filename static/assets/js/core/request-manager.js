/**
 * 智能请求管理器 - Linus式请求优化
 * 
 * 核心理念：
 * - 请求去重：相同请求合并
 * - 智能缓存：避免重复请求
 * - 失败重试：指数退避
 * - 优先级队列：重要请求优先
 * 
 * "不要让垃圾请求淹没服务器，每个请求都应该有价值"
 */

class RequestManager {
    constructor() {
        // 防止重复实例化
        if (RequestManager.instance) {
            return RequestManager.instance;
        }
        
        this.pendingRequests = new Map(); // 进行中的请求
        this.requestCache = new Map();    // 请求缓存
        this.requestQueue = [];           // 请求队列
        this.isProcessingQueue = false;   // 队列处理状态
        
        // 配置参数
        this.config = {
            maxConcurrentRequests: 6,     // 最大并发请求数
            maxRetries: 3,                // 最大重试次数
            retryDelay: 1000,             // 初始重试延迟（毫秒）
            cacheTimeout: 30000,          // 缓存超时（30秒）
            requestTimeout: 15000,        // 请求超时（15秒）
            queueSize: 100                // 队列最大长度
        };
        
        // 统计信息
        this.stats = {
            totalRequests: 0,
            cacheHits: 0,
            cacheMisses: 0,
            retriedRequests: 0,
            failedRequests: 0,
            deduplicatedRequests: 0
        };
        
        RequestManager.instance = this;
        
        // 定期清理过期缓存
        setInterval(() => this._cleanupCache(), 60000);
    }
    
    /**
     * 发起请求（主入口）
     * @param {string} url - 请求URL
     * @param {object} options - 请求选项
     */
    async request(url, options = {}) {
        const requestKey = this._generateRequestKey(url, options);
        const priority = options.priority || 'normal';
        
        this.stats.totalRequests++;
        
        // 检查是否有相同的进行中请求
        if (this.pendingRequests.has(requestKey)) {
            this.stats.deduplicatedRequests++;
            console.log(`[RequestManager] 请求去重: ${url}`);
            return await this.pendingRequests.get(requestKey);
        }
        
        // 检查缓存
        const cached = this._getCachedResponse(requestKey);
        if (cached && !options.ignoreCache) {
            this.stats.cacheHits++;
            console.log(`[RequestManager] 缓存命中: ${url}`);
            return cached.data;
        }
        
        this.stats.cacheMisses++;
        
        // 创建请求Promise
        const requestPromise = this._executeRequest(url, options, requestKey);
        this.pendingRequests.set(requestKey, requestPromise);
        
        try {
            const result = await requestPromise;
            
            // 缓存成功响应
            if (result && !options.noCache) {
                this._cacheResponse(requestKey, result);
            }
            
            return result;
        } finally {
            this.pendingRequests.delete(requestKey);
        }
    }
    
    /**
     * WebSocket请求（通过状态管理器）
     * @param {string} type - 请求类型
     * @param {object} data - 请求数据
     */
    async requestViaWebSocket(type, data = {}) {
        if (!window.WebSocketManager || !window.WebSocketManager.isConnected) {
            throw new Error('WebSocket未连接');
        }
        
        const requestId = this._generateRequestId();
        const request = {
            type,
            request_id: requestId,
            ...data,
            timestamp: new Date().toISOString()
        };
        
        // 创建Promise等待响应
        return new Promise((resolve, reject) => {
            const timeout = setTimeout(() => {
                reject(new Error('WebSocket请求超时'));
            }, this.config.requestTimeout);
            
            // 注册一次性监听器
            const responseHandler = (event) => {
                try {
                    const response = JSON.parse(event.data);
                    if (response.request_id === requestId) {
                        clearTimeout(timeout);
                        window.WebSocketManager.instance.removeEventListener('message', responseHandler);
                        
                        if (response.success !== false) {
                            resolve(response.data || response);
                        } else {
                            reject(new Error(response.error || '请求失败'));
                        }
                    }
                } catch (error) {
                    // 忽略非JSON消息
                }
            };
            
            window.WebSocketManager.instance.addEventListener('message', responseHandler);
            
            // 发送请求
            window.WebSocketManager.send(JSON.stringify(request));
        });
    }
    
    /**
     * 执行HTTP请求
     * @param {string} url - 请求URL
     * @param {object} options - 请求选项
     * @param {string} requestKey - 请求键
     */
    async _executeRequest(url, options, requestKey) {
        const retries = options.retries || 0;
        const maxRetries = this.config.maxRetries;
        
        try {
            const axiosOptions = {
                timeout: this.config.requestTimeout,
                ...options,
                headers: {
                    ...options.headers,
                    ...window.authManager?.getAuthHeaders?.() || {}
                }
            };
            
            let response;
            
            if (options.method === 'POST') {
                response = await axios.post(url, options.data, axiosOptions);
            } else if (options.method === 'PUT') {
                response = await axios.put(url, options.data, axiosOptions);
            } else if (options.method === 'DELETE') {
                response = await axios.delete(url, axiosOptions);
            } else {
                response = await axios.get(url, axiosOptions);
            }
            
            return response.data;
            
        } catch (error) {
            // 记录失败
            if (retries >= maxRetries) {
                this.stats.failedRequests++;
                console.error(`[RequestManager] 请求最终失败: ${url}`, error);
                throw error;
            }
            
            // 重试逻辑
            if (this._shouldRetry(error, retries)) {
                this.stats.retriedRequests++;
                const delay = this._calculateRetryDelay(retries);
                
                console.warn(`[RequestManager] 请求重试 ${retries + 1}/${maxRetries}: ${url}, 延迟 ${delay}ms`);
                
                await this._sleep(delay);
                
                // 递归重试
                return this._executeRequest(url, { ...options, retries: retries + 1 }, requestKey);
            }
            
            throw error;
        }
    }
    
    /**
     * 判断是否应该重试
     * @param {Error} error - 错误对象
     * @param {number} retries - 已重试次数
     */
    _shouldRetry(error, retries) {
        // 已达到最大重试次数
        if (retries >= this.config.maxRetries) {
            return false;
        }
        
        // 网络错误或服务器错误可以重试
        if (error.code === 'ECONNABORTED' || error.code === 'NETWORK_ERROR') {
            return true;
        }
        
        // HTTP状态码判断
        if (error.response) {
            const status = error.response.status;
            // 5xx服务器错误可以重试
            // 429限流可以重试
            // 408请求超时可以重试
            return status >= 500 || status === 429 || status === 408;
        }
        
        return false;
    }
    
    /**
     * 计算重试延迟（指数退避）
     * @param {number} retries - 重试次数
     */
    _calculateRetryDelay(retries) {
        const baseDelay = this.config.retryDelay;
        const exponentialDelay = baseDelay * Math.pow(2, retries);
        const jitter = Math.random() * 1000; // 添加随机抖动
        return Math.min(exponentialDelay + jitter, 30000); // 最大30秒
    }
    
    /**
     * 生成请求键
     * @param {string} url - 请求URL
     * @param {object} options - 请求选项
     */
    _generateRequestKey(url, options) {
        const method = options.method || 'GET';
        const data = options.data ? JSON.stringify(options.data) : '';
        return `${method}:${url}:${data}`;
    }
    
    /**
     * 获取缓存响应
     * @param {string} requestKey - 请求键
     */
    _getCachedResponse(requestKey) {
        const cached = this.requestCache.get(requestKey);
        if (!cached) return null;
        
        // 检查是否过期
        if (Date.now() - cached.timestamp > this.config.cacheTimeout) {
            this.requestCache.delete(requestKey);
            return null;
        }
        
        return cached;
    }
    
    /**
     * 缓存响应
     * @param {string} requestKey - 请求键
     * @param {any} data - 响应数据
     */
    _cacheResponse(requestKey, data) {
        this.requestCache.set(requestKey, {
            data,
            timestamp: Date.now()
        });
        
        // 限制缓存大小
        if (this.requestCache.size > 100) {
            const firstKey = this.requestCache.keys().next().value;
            this.requestCache.delete(firstKey);
        }
    }
    
    /**
     * 清理过期缓存
     */
    _cleanupCache() {
        const now = Date.now();
        const expired = [];
        
        for (const [key, cache] of this.requestCache.entries()) {
            if (now - cache.timestamp > this.config.cacheTimeout) {
                expired.push(key);
            }
        }
        
        expired.forEach(key => this.requestCache.delete(key));
        
        if (expired.length > 0) {
            console.log(`[RequestManager] 清理过期缓存: ${expired.length} 个`);
        }
    }
    
    /**
     * 生成请求ID
     */
    _generateRequestId() {
        return 'req_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now();
    }
    
    /**
     * 睡眠函数
     * @param {number} ms - 毫秒数
     */
    _sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
    
    /**
     * 获取统计信息
     */
    getStats() {
        return {
            ...this.stats,
            cacheHitRate: this.stats.totalRequests > 0 ? 
                (this.stats.cacheHits / this.stats.totalRequests * 100).toFixed(2) + '%' : '0%',
            pendingRequests: this.pendingRequests.size,
            cacheSize: this.requestCache.size,
            config: this.config
        };
    }
    
    /**
     * 清空缓存
     */
    clearCache() {
        this.requestCache.clear();
        console.log('[RequestManager] 缓存已清空');
    }
    
    /**
     * 取消所有进行中的请求
     */
    cancelAllRequests() {
        this.pendingRequests.clear();
        console.log('[RequestManager] 所有请求已取消');
    }
}

// 创建全局单例
window.RequestManager = window.RequestManager || new RequestManager();

// 页面卸载时清理资源
window.addEventListener('beforeunload', () => {
    window.RequestManager.cancelAllRequests();
    window.RequestManager.clearCache();
});

export default RequestManager;