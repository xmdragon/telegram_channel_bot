/**
 * Linus式统计组件 - 重构版本
 * 
 * 重构理念：
 * - 消除轮询特殊情况，统一使用订阅模式
 * - 数据通过WebSocket主动推送，而不是客户端拉取
 * - 智能缓存，避免重复请求
 * 
 * "好的架构让复杂性消失，而不是把它隐藏起来"
 */

// Linus式统计组件 - 无轮询版本
const LinusStatsComponent = {
    data() {
        return {
            loading: false,
            
            // 消息处理状态统计
            messageStatus: {
                total: 0,
                pending: 0,
                accepted: 0,
                rejected: 0,
                labels: {
                    total: '总消息数',
                    pending: '待处理',
                    accepted: '已接受', 
                    rejected: '已拒绝'
                }
            },
            
            // 拒绝原因分析（仅对已拒绝消息）
            rejectionAnalysis: {
                ad: 0,
                duplicate: 0,
                chat: 0,
                other: 0,
                labels: {
                    ad: '广告内容',
                    duplicate: '重复消息',
                    chat: '聊天消息',
                    other: '其他原因'
                }
            },
            
            // 数据一致性状态
            consistency: {
                consistent: true,
                details: null
            },
            
            // 系统信息
            systemInfo: {
                data_model: 'linus_v1',
                performance: 'O(1) - 原子计数器',
                accuracy: '100% - 无采样估算'
            },
            
            // 错误状态
            error: null,
            
            // 连接状态
            connected: false,
            lastUpdate: null,
            
            // 订阅ID
            subscriptionId: null,
            
            // 页面可见性
            isVisible: true
        };
    },
    
    mounted() {
        this.initializeComponent();
        this.setupVisibilityDetection();
    },
    
    beforeUnmount() {
        this.cleanup();
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
                if (stats.total_messages !== undefined) {
                    this.messageStatus.total = stats.total_messages;
                }
                if (stats.pending_count !== undefined) {
                    this.messageStatus.pending = stats.pending_count;
                }
                if (stats.approved_count !== undefined) {
                    this.messageStatus.accepted = stats.approved_count; // approved -> accepted
                }
                if (stats.rejected_count !== undefined) {
                    this.messageStatus.rejected = stats.rejected_count;
                }
                
                // 兼容旧格式（如果存在）
                if (stats.message_status) {
                    this.messageStatus = { ...this.messageStatus, ...stats.message_status };
                }
                
                // 更新拒绝原因分析（使用后端labels）
                if (stats.rejection_analysis) {
                    this.rejectionAnalysis = { ...this.rejectionAnalysis, ...stats.rejection_analysis };
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
            this.loading = true;
            this.error = null;
            
            try {
                let stats = null;
                
                // 优先尝试从缓存获取
                if (window.StateManager && window.StateManager.has('linus_stats')) {
                    stats = window.StateManager.get('linus_stats');
                } else {
                    // 智能选择请求方式
                    stats = await this.requestStatsData();
                }
                
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
                return await window.RequestManager.request('/api/stats/linus-overview', {
                    method: 'GET',
                    headers: window.authManager?.getAuthHeaders?.() || {}
                });
            } else {
                // 最后的降级方案
                const response = await axios.get('/api/stats/linus-overview', {
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
        }
    },
    
    template: `
        <div class="linus-stats-container">
            
            <!-- 错误提示 -->
            <el-alert v-if="error" 
                :title="error" 
                type="error" 
                show-icon 
                :closable="false"
                style="margin-bottom: 20px;">
            </el-alert>
            
            <!-- 加载状态 -->
            <div v-if="loading && !messageStatus.total" class="loading-container">
                <el-skeleton :rows="4" animated />
            </div>
            
            <!-- 统计内容 -->
            <div v-else class="stats-content">
                <div class="stats-grid">
                    <!-- 消息处理状态 -->
                    <template v-for="(value, key) in messageStatus" :key="'status-'+key">
                        <div v-if="key !== 'labels'" 
                             class="stat-badge"
                             :class="'status-'+key">
                            <span class="stat-badge-number">{{ value.toLocaleString() }}</span>
                            <span class="stat-badge-label">{{ messageStatus.labels[key] }}</span>
                        </div>
                    </template>
                    
                    <!-- 拒绝原因分析 -->
                    <template v-for="(value, key) in rejectionAnalysis" :key="'rejection-'+key">
                        <div v-if="key !== 'labels'"
                             class="stat-badge"
                             :class="'rejection-'+key">
                            <span class="stat-badge-number">{{ value.toLocaleString() }}</span>
                            <span class="stat-badge-label">{{ rejectionAnalysis.labels[key] }}</span>
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