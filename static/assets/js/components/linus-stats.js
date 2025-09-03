/**
 * Linus式统计组件 - 极简版本
 * 
 * Linus原则：
 * - 消除特殊情况，只有一种数据获取方式
 * - 不破坏用户空间，保持相同接口
 * - 实用主义，解决真实的性能问题
 * - 简洁执念，最少的代码做最多的事
 */

const LinusStatsComponent = {
    data() {
        return {
            loading: false,
            
            messageStatus: {
                pending: 0,
                approved: 0,
                rejected: 0,
                labels: {
                    pending: '待审核',
                    approved: '已发布', 
                    rejected: '已拒绝'
                }
            },
            
            error: null,
            lastUpdate: null,
            isRefreshing: false
        };
    },
    
    mounted() {
        this.loadStats();
    },
    
    methods: {
        /**
         * 初始化组件 - Linus式干净启动
         */
        async initializeComponent() {
            try {
                // 1. 订阅状态管理器
                this.subscribeToStatsUpdates();
                
                // 2. 初始加载数据
                await this.loadInitialData();
                
                // 3. 设置WebSocket监听
                this.setupWebSocketListeners();
                
                
            } catch (error) {
                this.error = '组件初始化失败';
            }
        },
        
        /**
         * 订阅统计数据更新
         */
        subscribeToStatsUpdates() {
            if (!window.StateManager) {
                return;
            }
            
            this.subscriptionId = window.StateManager.subscribe(
                'linus_stats',
                (newStats, oldStats) => {
                    this.handleStatsUpdate(newStats);
                },
                {
                    immediate: true,
                    component: 'linus-stats'
                }
            );
        },
        
        /**
         * 处理统计数据更新 - Linus式修复：直接映射后端数据格式
         */
        handleStatsUpdate(stats) {
            if (!stats) return;
            
            try {
                // 直接映射后端数据格式到前端显示
                if (stats.message_status) {
                    this.messageStatus = { ...this.messageStatus, ...stats.message_status };
                }
                
                
                // 更新一致性状态
                if (stats.consistency) {
                    this.consistency = stats.consistency;
                }
                
                // 更新系统信息
                if (stats.system_info) {
                    this.systemInfo = { ...this.systemInfo, ...stats.system_info };
                }
                
                this.lastUpdate = new Date();
                this.error = null;
                this.loading = false;
                
                
            } catch (error) {
                this.error = '数据更新失败';
            }
        },
        
        /**
         * 设置WebSocket监听器
         */
        setupWebSocketListeners() {
            if (!window.WebSocketManager) {
                return;
            }
            
            // 监听连接状态
            const originalConnect = window.WebSocketManager.handleOpen;
            window.WebSocketManager.handleOpen = (event) => {
                originalConnect?.call(window.WebSocketManager, event);
                this.connected = true;
            };
            
            const originalDisconnect = window.WebSocketManager.handleClose;
            window.WebSocketManager.handleClose = (event) => {
                originalDisconnect?.call(window.WebSocketManager, event);
                this.connected = false;
            };
            
            // 监听数据推送
            const originalMessage = window.WebSocketManager.handleMessage;
            window.WebSocketManager.handleMessage = (event) => {
                originalMessage?.call(window.WebSocketManager, event);
                
                try {
                    const data = JSON.parse(event.data);
                    
                    if (data.type === 'data_update' && data.data?.stats) {
                        // 服务器主动推送的统计数据
                        window.StateManager.setState('linus_stats', data.data.stats);
                    } else if (data.type === 'stats_response') {
                        // WebSocket请求的响应
                        if (data.success && data.data) {
                            window.StateManager.setState('linus_stats', data.data);
                        }
                    }
                } catch (error) {
                    // 忽略非JSON消息
                }
            };
        },
        
        /**
         * 初始加载数据 - 智能选择请求方式
         */
        async loadInitialData() {
            this.error = null;
            
            try {
                let stats = null;
                
                // 优先尝试从缓存获取
                if (window.StateManager && window.StateManager.has('linus_stats')) {
                    stats = window.StateManager.get('linus_stats');
                    // 缓存有数据时立即显示，不显示loading
                    if (stats) {
                        this.handleStatsUpdate(stats);
                        return;
                    }
                }
                
                // 只有在没有缓存数据时才显示loading
                this.loading = true;
                
                // 智能选择请求方式
                stats = await this.requestStatsData();
                
                if (stats) {
                    // 更新状态管理器
                    if (window.StateManager) {
                        window.StateManager.setState('linus_stats', stats);
                    } else {
                        // 降级处理
                        this.handleStatsUpdate(stats);
                    }
                }
                
            } catch (error) {
                this.error = '加载数据失败';
            } finally {
                this.loading = false;
            }
        },
        
        /**
         * 等待RequestManager初始化完成
         */
        async waitForRequestManager(maxRetries = 10) {
            return new Promise((resolve) => {
                let retries = 0;
                const checkInterval = setInterval(() => {
                    if (window.RequestManager && 
                        typeof window.RequestManager.request === 'function' && 
                        typeof window.RequestManager.requestViaWebSocket === 'function') {
                        clearInterval(checkInterval);
                        resolve(true);
                    } else if (retries >= maxRetries) {
                        clearInterval(checkInterval);
                        resolve(false);
                    }
                    retries++;
                }, 50);
            });
        },
        
        /**
         * 请求统计数据 - 智能选择方式
         */
        async requestStatsData() {
            // 等待RequestManager初始化完成
            const requestManagerReady = await this.waitForRequestManager();
            
            // 优先使用WebSocket请求（如果可用）
            if (requestManagerReady && window.WebSocketManager && window.WebSocketManager.isConnected) {
                try {
                    return await window.RequestManager.requestViaWebSocket('request_stats');
                } catch (error) {
                    // WebSocket请求失败，降级到HTTP
                }
            }
            
            // 降级到HTTP请求
            if (requestManagerReady) {
                return await window.RequestManager.request(window.API.messages.linusStatsOverview, {
                    method: 'GET',
                    headers: window.authManager?.getAuthHeaders?.() || {}
                });
            } else {
                // 最后的降级方案
                const response = await axios.get(window.API.messages.linusStatsOverview, {
                    headers: window.authManager?.getAuthHeaders?.() || {}
                });
                return response.data?.data;
            }
        },
        
        /**
         * 手动刷新数据
         */
        async refreshStats() {
            if (this.loading) return;
            
            try {
                const stats = await this.requestStatsData();
                if (stats && window.StateManager) {
                    window.StateManager.setState('linus_stats', stats, { force: true });
                }
            } catch (error) {
                this.error = '刷新失败';
            }
        },
        
        /**
         * 验证数据一致性
         */
        async validateConsistency() {
            try {
                const requestManagerReady = await this.waitForRequestManager();
                
                if (requestManagerReady) {
                    const result = await window.RequestManager.request('/api/stats/validate-consistency', {
                        method: 'POST'
                    });
                    
                    if (result?.success) {
                        this.consistency = result.data;
                        this.$message.success('一致性验证完成');
                    }
                } else {
                    // 降级方案
                    const response = await axios.post('/api/stats/validate-consistency', {}, {
                        headers: window.authManager?.getAuthHeaders?.() || {}
                    });
                    
                    if (response.data?.success) {
                        this.consistency = response.data.data;
                        this.$message.success('一致性验证完成');
                    }
                }
            } catch (error) {
                this.$message.error('一致性验证失败');
            }
        },
        
        /**
         * 设置页面可见性检测
         */
        setupVisibilityDetection() {
            // 页面可见性API
            document.addEventListener('visibilitychange', () => {
                this.isVisible = !document.hidden;
                
                if (this.isVisible) {
                    // 页面重新可见时，请求最新数据
                    setTimeout(() => {
                        this.refreshStats();
                    }, 500);
                }
            });
            
            // 窗口焦点事件
            window.addEventListener('focus', () => {
                this.isVisible = true;
                setTimeout(() => {
                    this.refreshStats();
                }, 500);
            });
            
            window.addEventListener('blur', () => {
                this.isVisible = false;
            });
        },
        
        /**
         * 清理资源
         */
        cleanup() {
            // 取消订阅
            if (this.subscriptionId && window.StateManager) {
                window.StateManager.unsubscribe('linus_stats', this.subscriptionId);
            }
            
        },
        
        /**
         * 获取格式化的最后更新时间
         */
        getLastUpdateText() {
            if (!this.lastUpdate) return '从未更新';
            
            const diff = Date.now() - this.lastUpdate.getTime();
            const seconds = Math.floor(diff / 1000);
            
            if (seconds < 60) return `${seconds}秒前`;
            const minutes = Math.floor(seconds / 60);
            if (minutes < 60) return `${minutes}分钟前`;
            const hours = Math.floor(minutes / 60);
            return `${hours}小时前`;
        },

        /**
         * 处理统计标签点击事件
         */
        handleStatClick(statKey) {
            // 调用父组件的切换筛选方法
            if (this.$parent && typeof this.$parent.handleStatClick === 'function') {
                this.$parent.handleStatClick(statKey);
            } else {
                console.warn('父组件未提供handleStatClick方法');
            }
        },

    },
    
    template: `
        <div class="linus-stats-container">
            
            <!-- 错误提示 -->
            <div v-if="error" class="error-alert">
                <span class="error-icon">⚠️</span>
                <span class="error-text">{{ error }}</span>
            </div>
            
            <!-- 加载状态 -->
            <div v-if="loading && !messageStatus.pending && !messageStatus.approved && !messageStatus.rejected" class="loading-container">
                <div class="loading-bar">加载统计数据中...</div>
            </div>
            
            <!-- 统计内容 -->
            <div v-else class="stats-content">
                <div class="stats-grid">
                    <!-- 消息处理状态 -->
                    <template v-for="(value, key) in messageStatus" :key="'status-'+key">
                        <div v-if="key !== 'labels'" 
                             class="stat-badge clickable"
                             :class="'status-'+key"
                             @click="handleStatClick(key)">
                            <span class="stat-badge-number">{{ value.toLocaleString() }}</span>
                            <span class="stat-badge-label">{{ messageStatus.labels[key] }}</span>
                        </div>
                    </template>
                </div>
            </div>
        </div>
    `
};

// 注册到window对象供index.js使用
window.LinusStatsComponent = LinusStatsComponent;

// Vue 3 - 组件通过全局变量提供给app实例注册

// 注册为全局变量
if (typeof window !== 'undefined') {
    window.LinusStatsComponent = LinusStatsComponent;
}