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

    // 初始化WebSocket连接
    init(callbacks = {}) {
        this.callbacks = { ...this.callbacks, ...callbacks };
        this.connect();
        return this;
    },

    // 建立WebSocket连接
    connect() {
        if (this.instance && this.instance.readyState === WebSocket.OPEN) {
            return;
        }

        try {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws`;
            
            this.instance = new WebSocket(wsUrl);
            
            this.instance.onopen = this.handleOpen.bind(this);
            this.instance.onmessage = this.handleMessage.bind(this);
            this.instance.onclose = this.handleClose.bind(this);
            this.instance.onerror = this.handleError.bind(this);
            
        } catch (error) {
            console.error('WebSocket连接失败:', error);
            this.handleError(error);
        }
    },

    // 处理连接打开
    handleOpen(event) {
        console.log('WebSocket连接已建立');
        this.isConnected = true;
        this.reconnectAttempts = 0;
        
        if (this.callbacks.onStatusChange) {
            this.callbacks.onStatusChange(true);
        }
    },

    // 处理消息接收
    handleMessage(event) {
        try {
            const data = JSON.parse(event.data);
            
            if (this.callbacks.onMessage) {
                this.callbacks.onMessage(data);
            }
            
        } catch (error) {
            console.error('WebSocket消息解析失败:', error);
        }
    },

    // 处理连接关闭
    handleClose(event) {
        console.log('WebSocket连接已关闭:', event.code, event.reason);
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
        
        console.log(`${delay}ms后尝试第${this.reconnectAttempts}次重连...`);
        
        setTimeout(() => {
            if (!this.isConnected) {
                this.connect();
            }
        }, delay);
    },

    // 发送消息
    send(data) {
        if (this.instance && this.instance.readyState === WebSocket.OPEN) {
            try {
                this.instance.send(JSON.stringify(data));
                return true;
            } catch (error) {
                console.error('WebSocket发送消息失败:', error);
                return false;
            }
        } else {
            console.warn('WebSocket未连接，无法发送消息');
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
    }
};

// 导出模块
if (typeof module !== 'undefined' && module.exports) {
    module.exports = WebSocketManager;
} else {
    window.WebSocketManager = WebSocketManager;
}