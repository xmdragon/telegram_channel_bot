/**
 * 消息统计组件 - 极简版本
 *
 * 设计原则：
 * - 消除特殊情况，只有一种数据获取方式
 * - 不破坏用户空间，保持相同接口
 * - 实用主义，解决真实的性能问题
 * - 简洁执念，最少的代码做最多的事
 */

const MessageStatsComponent = {
    data() {
        return {
            loading: false,
            showLegacySummary: false,  // 显示兼容汇总

            messageStatus: {
                // 新7状态
                pending: 0,
                send_failed: 0,
                auto_approved: 0,
                manual_approved: 0,
                ad_rejected: 0,
                dup_rejected: 0,
                manual_rejected: 0,
                // 兼容旧3状态
                approved: 0,  // auto_approved + manual_approved
                rejected: 0,  // ad_rejected + dup_rejected + manual_rejected
                labels: {
                    pending: '待审核',
                    send_failed: '发送失败',
                    auto_approved: '自动发布',
                    manual_approved: '手动发布',
                    ad_rejected: '广告拒绝',
                    dup_rejected: '重复拒绝',
                    manual_rejected: '手动拒绝',
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
         * 加载统计数据 - 极简实现
         * 消除所有特殊情况：只有HTTP请求 + localStorage缓存
         */
        async loadStats() {
            // 防抖：避免重复请求
            if (this.isRefreshing) return;
            
            try {
                // 1. 检查缓存
                const cached = this.getCachedStats();
                if (cached) {
                    this.updateStats(cached);
                    return;
                }
                
                // 2. 显示加载状态
                this.loading = true;
                this.error = null;
                
                // 3. 直接HTTP请求 - 消除WebSocket等复杂逻辑
                const stats = await this.fetchStatsFromAPI();
                
                // 4. 更新界面和缓存
                this.updateStats(stats);
                this.setCachedStats(stats);
                
            } catch (error) {
                this.error = '加载统计数据失败';
                // 错误时尝试使用过期缓存
                const cached = this.getCachedStats(true);
                if (cached) {
                    this.updateStats(cached);
                    this.error = '数据可能不是最新的';
                }
            } finally {
                this.loading = false;
            }
        },
        
        /**
         * 从API获取统计数据 - 单一数据源
         */
        async fetchStatsFromAPI() {
            // 使用统一的消息统计API
            const apiUrl = window.API?.messages?.stats;
            const response = await axios.get(apiUrl, {
                headers: window.authManager?.getAuthHeaders?.() || {}
            });

            if (!response.data?.success) {
                throw new Error('API响应失败');
            }

            return response.data.data;
        },
        
        /**
         * 更新统计显示 - 直接映射
         */
        updateStats(data) {
            if (data?.message_status) {
                // 保留标签，只更新数字
                Object.keys(data.message_status).forEach(key => {
                    if (key !== 'labels' && typeof data.message_status[key] === 'number') {
                        this.messageStatus[key] = data.message_status[key];
                    }
                });

                // 计算兼容的旧状态总数
                this.messageStatus.approved = (this.messageStatus.auto_approved || 0) + (this.messageStatus.manual_approved || 0);
                this.messageStatus.rejected = (this.messageStatus.ad_rejected || 0) + (this.messageStatus.dup_rejected || 0) + (this.messageStatus.manual_rejected || 0);
            }
            
            this.lastUpdate = new Date();
            this.error = null;
        },
        
        /**
         * 获取缓存统计 - localStorage简单实现
         */
        getCachedStats(allowExpired = false) {
            try {
                const cached = localStorage.getItem('message_stats');
                if (!cached) return null;
                
                const { data, timestamp } = JSON.parse(cached);
                const age = Date.now() - timestamp;
                const TTL = 30 * 1000; // 30秒缓存
                
                if (age < TTL || allowExpired) {
                    return data;
                }
                
                // 过期时清理
                localStorage.removeItem('message_stats');
                return null;
            } catch {
                return null;
            }
        },
        
        /**
         * 设置缓存统计
         */
        setCachedStats(data) {
            try {
                localStorage.setItem('message_stats', JSON.stringify({
                    data,
                    timestamp: Date.now()
                }));
            } catch {
                // 忽略缓存错误
            }
        },
        
        /**
         * 手动刷新 - 重新加载数据
         */
        async refreshStats() {
            if (this.isRefreshing) return;
            
            this.isRefreshing = true;
            try {
                // 清除缓存，强制重新请求
                localStorage.removeItem('message_stats');
                await this.loadStats();
            } finally {
                this.isRefreshing = false;
            }
        },
        
        /**
         * 处理统计点击事件 - 保持向后兼容
         */
        handleStatClick(statKey) {
            if (this.$parent && typeof this.$parent.handleStatClick === 'function') {
                this.$parent.handleStatClick(statKey);
            }
        },
        
        /**
         * 格式化更新时间 - 保持原有功能
         */
        getLastUpdateText() {
            if (!this.lastUpdate) return '从未更新';
            
            const seconds = Math.floor((Date.now() - this.lastUpdate.getTime()) / 1000);
            if (seconds < 60) return `${seconds}秒前`;
            
            const minutes = Math.floor(seconds / 60);
            if (minutes < 60) return `${minutes}分钟前`;
            
            return `${Math.floor(minutes / 60)}小时前`;
        }
    },
    
    template: `
        <div class="message-stats-container">
            <!-- 错误提示 -->
            <div v-if="error" class="error-alert">
                <span class="error-icon">⚠️</span>
                <span class="error-text">{{ error }}</span>
            </div>
            
            <!-- 加载状态 - 简化判断条件 -->
            <div v-if="loading" class="loading-container">
                <div class="loading-bar">加载统计数据中...</div>
            </div>
            
            <!-- 统计内容 - 始终显示，即使加载中 -->
            <div v-show="!loading || messageStatus.pending > 0" class="stats-content">
                <div class="stats-grid stats-grid-7">
                    <!-- 7种状态统计 -->
                    <div class="stat-badge clickable status-pending" @click="handleStatClick('pending')">
                        <span class="stat-badge-number">{{ messageStatus.pending.toLocaleString() }}</span>
                        <span class="stat-badge-label">待审核</span>
                    </div>
                    <div class="stat-badge clickable status-send-failed" @click="handleStatClick('send_failed')">
                        <span class="stat-badge-number">{{ messageStatus.send_failed.toLocaleString() }}</span>
                        <span class="stat-badge-label">发送失败</span>
                    </div>
                    <div class="stat-badge clickable status-auto-approved" @click="handleStatClick('auto_approved')">
                        <span class="stat-badge-number">{{ messageStatus.auto_approved.toLocaleString() }}</span>
                        <span class="stat-badge-label">自动发布</span>
                    </div>
                    <div class="stat-badge clickable status-manual-approved" @click="handleStatClick('manual_approved')">
                        <span class="stat-badge-number">{{ messageStatus.manual_approved.toLocaleString() }}</span>
                        <span class="stat-badge-label">手动发布</span>
                    </div>
                    <div class="stat-badge clickable status-ad-rejected" @click="handleStatClick('ad_rejected')">
                        <span class="stat-badge-number">{{ messageStatus.ad_rejected.toLocaleString() }}</span>
                        <span class="stat-badge-label">广告拒绝</span>
                    </div>
                    <div class="stat-badge clickable status-dup-rejected" @click="handleStatClick('dup_rejected')">
                        <span class="stat-badge-number">{{ messageStatus.dup_rejected.toLocaleString() }}</span>
                        <span class="stat-badge-label">重复拒绝</span>
                    </div>
                    <div class="stat-badge clickable status-manual-rejected" @click="handleStatClick('manual_rejected')">
                        <span class="stat-badge-number">{{ messageStatus.manual_rejected.toLocaleString() }}</span>
                        <span class="stat-badge-label">手动拒绝</span>
                    </div>
                </div>

                <!-- 兼容汇总视图 -->
                <div v-if="showLegacySummary" class="stats-summary">
                    <div class="stats-summary-grid">
                        <div class="stat-summary-item">
                            <span class="stat-summary-number">{{ (messageStatus.pending + messageStatus.send_failed).toLocaleString() }}</span>
                            <span class="stat-summary-label">待处理</span>
                        </div>
                        <div class="stat-summary-item">
                            <span class="stat-summary-number">{{ messageStatus.approved.toLocaleString() }}</span>
                            <span class="stat-summary-label">已发布</span>
                        </div>
                        <div class="stat-summary-item">
                            <span class="stat-summary-number">{{ messageStatus.rejected.toLocaleString() }}</span>
                            <span class="stat-summary-label">已拒绝</span>
                        </div>
                    </div>
                </div>

                <!-- 切换按钮 -->
                <div class="stats-toggle">
                    <button @click="showLegacySummary = !showLegacySummary" class="btn-toggle">
                        {{ showLegacySummary ? '详细状态' : '汇总视图' }}
                    </button>
                </div>
            </div>
        </div>
    `
};

// 全局注册 - 保持向后兼容
window.MessageStatsComponent = MessageStatsComponent;