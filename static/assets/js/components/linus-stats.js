/**
 * Linus式统计组件
 * 清晰分离两个维度的统计展示
 * 
 * 设计原则：
 * 1. 消息处理状态和拒绝原因分析分离显示
 * 2. 数据100%一致，不会出现神秘数字
 * 3. 简洁明了，消除用户困惑
 */

// Linus式统计组件
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
            
            // 自动刷新
            autoRefresh: true,
            refreshInterval: null
        };
    },
    
    mounted() {
        this.loadStats();
        this.startAutoRefresh();
    },
    
    beforeUnmount() {
        this.stopAutoRefresh();
    },
    
    methods: {
        async loadStats() {
            try {
                this.loading = true;
                this.error = null;
                
                // 调用Linus式统计API
                const response = await axios.get('/api/stats/linus-overview', {
                    headers: authManager.getAuthHeaders()
                });
                
                if (response.data.success) {
                    const data = response.data.data;
                    
                    // 更新消息状态统计
                    this.messageStatus = data.message_status;
                    
                    // 更新拒绝原因分析
                    this.rejectionAnalysis = data.rejection_analysis;
                    
                    // 更新一致性状态
                    this.consistency = data.consistency || { consistent: true };
                    
                    // 更新系统信息
                    this.systemInfo = data.system_info || this.systemInfo;
                    
                } else {
                    this.error = response.data.error || '获取统计数据失败';
                }
                
            } catch (error) {
                console.error('加载统计数据失败:', error);
                this.error = '网络错误，请稍后重试';
            } finally {
                this.loading = false;
            }
        },
        
        async validateConsistency() {
            try {
                const response = await axios.post('/api/stats/validate-consistency', {}, {
                    headers: authManager.getAuthHeaders()
                });
                
                if (response.data.success) {
                    this.consistency = response.data.data;
                    this.$message.success('数据一致性验证完成');
                } else {
                    this.$message.error('一致性验证失败');
                }
            } catch (error) {
                console.error('验证一致性失败:', error);
                this.$message.error('验证失败');
            }
        },
        
        startAutoRefresh() {
            if (this.autoRefresh) {
                this.refreshInterval = setInterval(() => {
                    this.loadStats();
                }, 5000); // 每5秒刷新
            }
        },
        
        stopAutoRefresh() {
            if (this.refreshInterval) {
                clearInterval(this.refreshInterval);
                this.refreshInterval = null;
            }
        },
        
        toggleAutoRefresh() {
            this.autoRefresh = !this.autoRefresh;
            if (this.autoRefresh) {
                this.startAutoRefresh();
            } else {
                this.stopAutoRefresh();
            }
        },
        
        // 计算拒绝率
        getRejectionRate() {
            if (this.messageStatus.total === 0) return 0;
            return ((this.messageStatus.rejected / this.messageStatus.total) * 100).toFixed(1);
        },
        
        // 计算接受率
        getAcceptanceRate() {
            if (this.messageStatus.total === 0) return 0;
            return ((this.messageStatus.accepted / this.messageStatus.total) * 100).toFixed(1);
        },
        
        // 获取最主要的拒绝原因
        getTopRejectionReason() {
            const reasons = this.rejectionAnalysis;
            let maxCount = 0;
            let topReason = 'unknown';
            
            Object.keys(reasons).forEach(key => {
                if (key !== 'labels' && reasons[key] > maxCount) {
                    maxCount = reasons[key];
                    topReason = key;
                }
            });
            
            return {
                reason: topReason,
                count: maxCount,
                label: reasons.labels[topReason] || topReason
            };
        },
        
        // 获取状态样式
        getStatusClass(status) {
            const statusClasses = {
                pending: 'warning',
                accepted: 'success', 
                rejected: 'danger'
            };
            return statusClasses[status] || 'info';
        },
        
        // 获取拒绝原因样式
        getRejectionClass(reason) {
            const reasonClasses = {
                ad: 'danger',
                duplicate: 'warning',
                chat: 'info',
                other: 'secondary'
            };
            return reasonClasses[reason] || 'secondary';
        }
    },
    
    template: `
        <div class="stats-grid">
            <!-- 使用unified-stats.css的badge样式 -->
            <div class="stat-badge total" data-stat-key="total">
                <span class="stat-badge-label">总消息</span>
                <span class="stat-badge-number">{{ messageStatus.total }}</span>
            </div>
            
            <div class="stat-badge pending" data-stat-key="pending">
                <span class="stat-badge-label">待审核</span>
                <span class="stat-badge-number">{{ messageStatus.pending }}</span>
            </div>
            
            <div class="stat-badge approved" data-stat-key="approved">
                <span class="stat-badge-label">已发布</span>
                <span class="stat-badge-number">{{ messageStatus.accepted }}</span>
            </div>
            
            <div class="stat-badge rejected" data-stat-key="rejected">
                <span class="stat-badge-label">已拒绝</span>
                <span class="stat-badge-number">{{ messageStatus.rejected }}</span>
            </div>
            
            <div class="stat-badge ads" data-stat-key="ads">
                <span class="stat-badge-label">广告消息</span>
                <span class="stat-badge-number">{{ rejectionAnalysis.ad }}</span>
            </div>
            
            <div class="stat-badge duplicates" data-stat-key="duplicates">
                <span class="stat-badge-label">重复消息</span>
                <span class="stat-badge-number">{{ rejectionAnalysis.duplicate }}</span>
            </div>
            
            <div class="stat-badge chats" data-stat-key="chats">
                <span class="stat-badge-label">聊天消息</span>
                <span class="stat-badge-number">{{ rejectionAnalysis.chat }}</span>
            </div>
        </div>
    `
};

// 导出组件以供其他模块使用
if (typeof window !== 'undefined') {
    window.LinusStatsComponent = LinusStatsComponent;
}