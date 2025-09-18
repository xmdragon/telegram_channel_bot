/**
 * WebSocket工厂类
 *
 * 核心原则：
 * 1. 消除所有重复的WebSocket URL构造逻辑
 * 2. 统一的连接管理，不再有特殊情况
 * 3. 一个地方定义，到处使用
 */

class WebSocketFactory {
    /**
     * 创建WebSocket连接
     * @param {string} type - WebSocket类型，默认'main'
     * @param {Object} options - 连接选项
     * @returns {WebSocket} WebSocket实例
     */
    static create(type = 'main', options = {}) {
        if (!window.API || !window.API.websocket) {
            throw new Error('API配置未加载，无法创建WebSocket连接');
        }

        const endpoint = window.API.websocket[type];
        if (!endpoint) {
            throw new Error(`未知的WebSocket类型: ${type}`);
        }

        // 使用API配置中的工具函数构造完整URL
        const wsUrl = window.API.utils.getWebSocketUrl(endpoint);
        
        const websocket = new WebSocket(wsUrl);
        
        // 设置默认配置
        if (options.timeout) {
            const timeoutId = setTimeout(() => {
                if (websocket.readyState === WebSocket.CONNECTING) {
                    websocket.close();
                    console.error(`WebSocket连接超时: ${wsUrl}`);
                }
            }, options.timeout);
            
            // 连接成功后清除超时
            websocket.addEventListener('open', () => clearTimeout(timeoutId), { once: true });
        }
        
        return websocket;
    }

    /**
     * 创建带重连机制的WebSocket
     * @param {string} type - WebSocket类型
     * @param {Object} options - 连接选项
     * @returns {Object} 包含WebSocket和重连控制的对象
     */
    static createWithReconnect(type = 'main', options = {}) {
        const defaultOptions = {
            maxRetries: 5,
            retryInterval: 1000,
            timeout: 10000,
            ...options
        };

        let websocket = null;
        let retryCount = 0;
        let reconnectTimer = null;

        const connect = () => {
            try {
                websocket = WebSocketFactory.create(type, { timeout: defaultOptions.timeout });
                
                websocket.onopen = (event) => {
                    retryCount = 0; // 重置重试计数
                    if (defaultOptions.onOpen) defaultOptions.onOpen(event);
                };

                websocket.onclose = (event) => {
                    if (defaultOptions.onClose) defaultOptions.onClose(event);
                    
                    // 自动重连
                    if (retryCount < defaultOptions.maxRetries && !event.wasClean) {
                        retryCount++;
                        const delay = defaultOptions.retryInterval * Math.pow(2, retryCount - 1); // 指数退避
                        
                        reconnectTimer = setTimeout(connect, delay);
                        console.log(`WebSocket重连中... (${retryCount}/${defaultOptions.maxRetries})`);
                    }
                };

                websocket.onerror = (event) => {
                    if (defaultOptions.onError) defaultOptions.onError(event);
                };

                websocket.onmessage = (event) => {
                    if (defaultOptions.onMessage) defaultOptions.onMessage(event);
                };

            } catch (error) {
                console.error('创建WebSocket失败:', error);
                if (defaultOptions.onError) defaultOptions.onError(error);
            }
        };

        // 立即连接
        connect();

        return {
            get websocket() { return websocket; },
            get readyState() { return websocket ? websocket.readyState : WebSocket.CLOSED; },
            
            send(data) {
                if (websocket && websocket.readyState === WebSocket.OPEN) {
                    websocket.send(data);
                } else {
                    console.warn('WebSocket未连接，无法发送消息');
                }
            },
            
            close() {
                if (reconnectTimer) {
                    clearTimeout(reconnectTimer);
                    reconnectTimer = null;
                }
                if (websocket) {
                    websocket.close();
                }
            }
        };
    }

    /**
     * 检查WebSocket是否可用
     * @returns {boolean}
     */
    static isSupported() {
        return typeof WebSocket !== 'undefined';
    }
}

// 导出到全局
// 全局暴露（浏览器环境）
if (typeof window !== 'undefined') {
    window.WebSocketFactory = WebSocketFactory;
}

// ES6导出（如果支持）
if (typeof module !== 'undefined' && module.exports) {
    module.exports = WebSocketFactory;
}