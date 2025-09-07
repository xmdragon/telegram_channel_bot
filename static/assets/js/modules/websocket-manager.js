// WebSocket连接管理模块

const WebSocketManager = {
    instance: null,
    isConnected: false,
    reconnectAttempts: 0,
    maxReconnectAttempts: 5,
    reconnectDelay: 1000,
    callbacks: {
        onMessage: null,
        onStatusChange: null,
        onError: null
    },
    // 保存连接参数用于重连
    connectionUrl: null,
    connectionOptions: null,

    // 初始化WebSocket连接
    init(callbacks = {}) {
        // 获取WebSocket URL
        const wsUrl = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${wsUrl}//${window.location.host}/ws`;
        
        // 使用带日志和心跳的连接方法
        this.connectWithOptions(url, {
            enableHeartbeat: true,
            heartbeatInterval: 20000,
            ...callbacks
        });
        
        return this;
    },

    // 处理连接打开
    handleOpen(event) {
        console.log('🔗 WebSocketManager.handleOpen: 连接已建立');
        this.isConnected = true;
        this.reconnectAttempts = 0;
        
        if (this.callbacks.onStatusChange) {
            console.log('🔗 WebSocketManager.handleOpen: 调用状态回调 onStatusChange(true)');
            this.callbacks.onStatusChange(true);
        } else {
            console.log('🔗 WebSocketManager.handleOpen: 没有状态回调');
        }
    },

    // 处理消息接收
    handleMessage(event) {
        try {
            console.log('🔍 WebSocketManager.handleMessage: 原始消息', event.data);
            const data = JSON.parse(event.data);
            console.log('🔍 WebSocketManager.handleMessage: 解析后消息', data);
            
            // 检查是否为心跳响应
            if (data.type === 'pong') {
                console.log('💚 WebSocketManager收到pong响应');
                return;
            }
            
            if (this.callbacks.onMessage) {
                console.log('📦 WebSocketManager.handleMessage: 调用消息回调 onMessage:', data);
                this.callbacks.onMessage(data);
            } else {
                console.log('📦 WebSocketManager.handleMessage: 没有消息回调');
            }
            
        } catch (error) {
            console.error('WebSocket消息解析失败:', error, ' 原始数据:', event.data);
        }
    },

    // 处理连接关闭
    handleClose(event) {
        // WebSocket连接已关闭（生产环境已移除日志）
        this.isConnected = false;
        
        if (this.callbacks.onStatusChange) {
            this.callbacks.onStatusChange(false);
        }

        // 自动重连
        if (!event.wasClean && this.reconnectAttempts < this.maxReconnectAttempts) {
            this.scheduleReconnect();
        }
    },

    // 处理连接错误
    handleError(error) {
        console.error('WebSocket错误:', error);
        this.isConnected = false;
        
        if (this.callbacks.onError) {
            this.callbacks.onError(error);
        }
    },

    // 计划重连
    scheduleReconnect() {
        this.reconnectAttempts++;
        const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
        
        
        setTimeout(() => {
            if (!this.isConnected && this.connectionUrl && this.connectionOptions) {
                this.connectWithOptions(this.connectionUrl, this.connectionOptions);
            }
        }, delay);
    },

    // 发送消息
    send(data) {
        if (this.instance && this.instance.readyState === WebSocket.OPEN) {
            try {
                // 如果data已经是字符串，直接发送；否则JSON编码
                const message = typeof data === 'string' ? data : JSON.stringify(data);
                this.instance.send(message);
                return true;
            } catch (error) {
                console.error('WebSocket发送消息失败:', error);
                return false;
            }
        } else {
            return false;
        }
    },

    // 关闭连接
    close() {
        if (this.instance) {
            this.instance.close(1000, '主动关闭');
            this.instance = null;
        }
        this.isConnected = false;
    },

    // 获取连接状态
    getStatus() {
        return {
            connected: this.isConnected,
            readyState: this.instance ? this.instance.readyState : null,
            reconnectAttempts: this.reconnectAttempts
        };
    },

    // 重置重连计数
    resetReconnectAttempts() {
        this.reconnectAttempts = 0;
    },

    // 心跳管理
    startHeartbeat(interval = 30000) {
        this.stopHeartbeat();
        
        this.heartbeatInterval = setInterval(() => {
            if (this.instance && this.instance.readyState === WebSocket.OPEN) {
                console.log('💓 WebSocketManager发送心跳');
                this.send(JSON.stringify({type: 'ping'}));
            }
        }, interval);
    },

    stopHeartbeat() {
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
            this.heartbeatInterval = null;
        }
    },

    // 连接超时管理
    setConnectionTimeout(timeout = 10000) {
        if (this.connectionTimeout) {
            clearTimeout(this.connectionTimeout);
        }
        
        this.connectionTimeout = setTimeout(() => {
            if (this.instance && this.instance.readyState === WebSocket.CONNECTING) {
                this.instance.close();
            }
        }, timeout);
    },

    clearConnectionTimeout() {
        if (this.connectionTimeout) {
            clearTimeout(this.connectionTimeout);
            this.connectionTimeout = null;
        }
    },

    // 高级连接管理
    connectWithOptions(url, options = {}) {
        const {
            timeout = 10000,
            enableHeartbeat = true,
            heartbeatInterval = 20000,  // 20秒心跳，避免服务器30秒超时
            ...callbacks
        } = options;

        // 保存连接参数用于重连
        this.connectionUrl = url;
        this.connectionOptions = options;

        // 设置回调
        this.callbacks = { ...this.callbacks, ...callbacks };
        
        // 创建连接
        if (this.instance && this.instance.readyState === WebSocket.CONNECTING) {
            return; // 避免重复连接
        }
        
        if (this.instance) {
            this.instance.close();
        }

        try {
            this.instance = new WebSocket(url);
            this.setConnectionTimeout(timeout);

            this.instance.onopen = (event) => {
                console.log('🔗 WebSocketManager连接已建立');
                this.clearConnectionTimeout();
                this.handleOpen(event);
                if (enableHeartbeat) {
                    console.log(`🔄 WebSocketManager启动心跳，间隔${heartbeatInterval}毫秒`);
                    this.startHeartbeat(heartbeatInterval);
                }
            };

            this.instance.onmessage = this.handleMessage.bind(this);
            this.instance.onclose = (event) => {
                this.clearConnectionTimeout();
                this.stopHeartbeat();
                this.handleClose(event);
            };
            this.instance.onerror = (error) => {
                this.clearConnectionTimeout();
                this.handleError(error);
            };

        } catch (error) {
            console.error('WebSocket连接失败:', error);
            this.handleError(error);
        }
    },

    // 检查并重连
    checkAndReconnect(url, options = {}) {
        if (!this.isConnected && (!this.instance || this.instance.readyState === WebSocket.CLOSED)) {
            if (this.reconnectAttempts < this.maxReconnectAttempts) {
                this.connectWithOptions(url, options);
            }
        }
    },

    // 清理资源
    cleanup() {
        this.stopHeartbeat();
        this.clearConnectionTimeout();
        this.close();
        this.callbacks = {
            onMessage: null,
            onStatusChange: null,
            onError: null
        };
    }
};

// 导出模块
if (typeof module !== 'undefined' && module.exports) {
    module.exports = WebSocketManager;
} else {
    window.WebSocketManager = WebSocketManager;
}