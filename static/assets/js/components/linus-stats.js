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
                
                console.log('[LinusStats] 组件初始化完成 - 无轮询架构');
                
            } catch (error) {
                console.error('[LinusStats] 初始化失败:', error);
                this.error = '组件初始化失败';
            }
        },
        
        /**
         * 订阅统计数据更新
         */
        subscribeToStatsUpdates() {
            if (!window.StateManager) {
                console.error('[LinusStats] StateManager未找到');
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
         * 处理统计数据更新
         */
        handleStatsUpdate(stats) {
            if (!stats) return;
            
            try {
                // 更新消息状态统计
                if (stats.message_status) {
                    this.messageStatus = { ...this.messageStatus, ...stats.message_status };
                }
                
                // 更新拒绝原因分析
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
                
                console.log('[LinusStats] 统计数据已更新');
                
            } catch (error) {
                console.error('[LinusStats] 处理统计更新失败:', error);
                this.error = '数据更新失败';
            }
        },
        
        /**
         * 设置WebSocket监听器
         */
        setupWebSocketListeners() {
            if (!window.WebSocketManager) {
                console.warn('[LinusStats] WebSocket管理器未找到，将使用HTTP请求');
                return;
            }
            
            // 监听连接状态
            const originalConnect = window.WebSocketManager.handleOpen;
            window.WebSocketManager.handleOpen = (event) => {
                originalConnect?.call(window.WebSocketManager, event);
                this.connected = true;
                console.log('[LinusStats] WebSocket已连接');
            };
            
            const originalDisconnect = window.WebSocketManager.handleClose;
            window.WebSocketManager.handleClose = (event) => {
                originalDisconnect?.call(window.WebSocketManager, event);
                this.connected = false;
                console.log('[LinusStats] WebSocket连接断开');
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
                    console.log('[LinusStats] 使用缓存数据');
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
                console.error('[LinusStats] 加载初始数据失败:', error);
                this.error = '加载数据失败';
                this.loading = false;
            }
        },
        
        /**
         * 请求统计数据 - 智能选择方式
         */
        async requestStatsData() {
            // 优先使用WebSocket请求（如果可用）
            if (window.WebSocketManager && window.WebSocketManager.isConnected && window.RequestManager) {
                try {
                    return await window.RequestManager.requestViaWebSocket('request_stats');
                } catch (error) {
                    console.warn('[LinusStats] WebSocket请求失败，降级到HTTP:', error);
                }
            }
            
            // 降级到HTTP请求
            if (window.RequestManager) {
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
                console.error('[LinusStats] 手动刷新失败:', error);
                this.error = '刷新失败';
            }
        },
        
        /**
         * 验证数据一致性
         */
        async validateConsistency() {
            try {
                if (window.RequestManager) {
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
                console.error('[LinusStats] 一致性验证失败:', error);
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
            
            console.log('[LinusStats] 组件已清理');
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
            <!-- 标题栏 -->
            <div class="stats-header">
                <h3>
                    <i class="el-icon-data-analysis"></i>
                    Linus式统计分析
                </h3>
                <div class="header-actions">
                    <el-button 
                        @click="refreshStats" 
                        :loading="loading"
                        icon="el-icon-refresh"
                        size="small"
                        type="primary">
                        刷新
                    </el-button>
                    <span class="connection-status" :class="{ connected }">
                        {{ connected ? '实时连接' : '离线模式' }}
                    </span>
                </div>
            </div>
            
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
                <!-- 消息处理状态 -->
                <el-card class="stats-card" shadow="hover">
                    <template #header>
                        <span class="card-title">消息处理状态</span>
                    </template>
                    <div class="status-grid">
                        <div v-for="(value, key) in messageStatus" 
                             :key="key"
                             v-if="key !== 'labels'"
                             class="status-item"
                             :class="key">
                            <div class="status-value">{{ value.toLocaleString() }}</div>
                            <div class="status-label">{{ messageStatus.labels[key] }}</div>
                        </div>
                    </div>
                </el-card>
                
                <!-- 拒绝原因分析 -->
                <el-card class="stats-card" shadow="hover">
                    <template #header>
                        <span class="card-title">拒绝原因分析</span>
                        <span class="card-subtitle">（仅统计已拒绝消息）</span>
                    </template>
                    <div class="rejection-grid">
                        <div v-for="(value, key) in rejectionAnalysis" 
                             :key="key"
                             v-if="key !== 'labels'"
                             class="rejection-item">
                            <div class="rejection-value">{{ value.toLocaleString() }}</div>
                            <div class="rejection-label">{{ rejectionAnalysis.labels[key] }}</div>
                        </div>
                    </div>
                </el-card>
                
                <!-- 系统信息 -->
                <el-card class="stats-card" shadow="hover">
                    <template #header>
                        <span class="card-title">系统信息</span>
                        <el-button 
                            @click="validateConsistency"
                            size="mini"
                            type="text"
                            icon="el-icon-check">
                            验证一致性
                        </el-button>
                    </template>
                    <div class="system-info">
                        <div class="info-item">
                            <span class="info-label">数据模型:</span>
                            <span class="info-value">{{ systemInfo.data_model }}</span>
                        </div>
                        <div class="info-item">
                            <span class="info-label">性能:</span>
                            <span class="info-value">{{ systemInfo.performance }}</span>
                        </div>
                        <div class="info-item">
                            <span class="info-label">准确性:</span>
                            <span class="info-value">{{ systemInfo.accuracy }}</span>
                        </div>
                        <div class="info-item">
                            <span class="info-label">一致性:</span>
                            <span class="info-value" :class="{ 'error': !consistency.consistent }">
                                {{ consistency.consistent ? '✓ 一致' : '✗ 不一致' }}
                            </span>
                        </div>
                        <div class="info-item">
                            <span class="info-label">最后更新:</span>
                            <span class="info-value">{{ getLastUpdateText() }}</span>
                        </div>
                    </div>
                </el-card>
            </div>
        </div>
    `
};

// 注册到window对象供index.js使用
window.LinusStatsComponent = LinusStatsComponent;

// 注册组件
if (typeof Vue !== 'undefined') {
    Vue.component('linus-stats', LinusStatsComponent);
}

export default LinusStatsComponent;