/* Threshold-dashboard.js - 原生JavaScript阈值监控功能 */

// 全局Vue应用实例
let thresholdApp;

// 等待DOM加载完成
document.addEventListener('DOMContentLoaded', function() {
    // 初始化Vue应用
    const { createApp } = Vue;
    
    thresholdApp = createApp({
        data() {
            return {
                // 加载状态
                loading: false,
                optimizing: false,
                
                // 搜索文本
                searchText: '',
                
                // 统计数据
                stats: {},
                
                // 重置状态
                resetting: {},
                
                // 反馈对话框
                feedbackDialog: {
                    visible: false,
                    filterName: '',
                    metricName: '',
                    submitting: false,
                    form: {
                        predicted_score: 0.5,
                        actual_result: 'positive',
                        action: 'approve',
                        comments: ''
                    }
                },
                
                // 优化设置对话框
                optimizeDialog: {
                    visible: false,
                    settings: {
                        min_feedback: 20,
                        optimization_interval: 50,
                        window_size: 500
                    }
                }
            }
        },
        
        computed: {
            // 过滤后的统计数据
            filteredStats() {
                if (!this.searchText) {
                    return this.stats;
                }
                
                const search = this.searchText.toLowerCase();
                const filtered = {};
                
                for (const [filterName, filterData] of Object.entries(this.stats)) {
                    const displayName = this.getFilterDisplayName(filterName).toLowerCase();
                    if (displayName.includes(search)) {
                        filtered[filterName] = filterData;
                        continue;
                    }
                    
                    // 搜索指标
                    const matchingMetrics = {};
                    for (const [metricName, metricData] of Object.entries(filterData)) {
                        const metricDisplayName = this.getMetricDisplayName(metricName).toLowerCase();
                        if (metricDisplayName.includes(search)) {
                            matchingMetrics[metricName] = metricData;
                        }
                    }
                    
                    if (Object.keys(matchingMetrics).length > 0) {
                        filtered[filterName] = matchingMetrics;
                    }
                }
                
                return filtered;
            },
            
            // 总反馈数
            totalFeedback() {
                let total = 0;
                for (const filterData of Object.values(this.stats)) {
                    for (const metricData of Object.values(filterData)) {
                        total += metricData.feedback_count || 0;
                    }
                }
                return total;
            },
            
            // 平均准确率
            averageAccuracy() {
                const metrics = [];
                for (const filterData of Object.values(this.stats)) {
                    for (const metricData of Object.values(filterData)) {
                        if (metricData.accuracy !== undefined) {
                            metrics.push(metricData.accuracy);
                        }
                    }
                }
                
                if (metrics.length === 0) return 0;
                return metrics.reduce((sum, acc) => sum + acc, 0) / metrics.length;
            },
            
            // 最后更新时间
            lastUpdate() {
                let latest = null;
                for (const filterData of Object.values(this.stats)) {
                    for (const metricData of Object.values(filterData)) {
                        if (metricData.last_updated) {
                            const time = new Date(metricData.last_updated);
                            if (!latest || time > latest) {
                                latest = time;
                            }
                        }
                    }
                }
                return latest;
            }
        },
        
        methods: {
            // 刷新数据
            async refreshData() {
                this.loading = true;
                try {
                    const response = await axios.get(API.threshold.stats);
                    this.stats = response.data;
                } catch (error) {
                    console.error('刷新数据失败:', error);
                    this.showMessage(error.response?.data?.detail || '刷新数据失败', 'error');
                } finally {
                    this.loading = false;
                }
            },
            
            // 批量优化阈值
            async optimizeAllThresholds() {
                this.optimizing = true;
                try {
                    const response = await axios.post(API.threshold.optimize);
                    this.showMessage('批量优化完成！', 'success');
                    await this.refreshData();
                } catch (error) {
                    console.error('批量优化失败:', error);
                    this.showMessage(error.response?.data?.detail || '批量优化失败', 'error');
                } finally {
                    this.optimizing = false;
                }
            },
            
            // 重置阈值
            async resetThreshold(filterName, metricName) {
                const key = `${filterName}_${metricName}`;
                this.resetting = { ...this.resetting, [key]: true };
                
                try {
                    const response = await axios.post(API.threshold.reset, {
                        filter_name: filterName,
                        metric_name: metricName
                    });
                    
                    this.showMessage('阈值重置成功！', 'success');
                    await this.refreshData();
                } catch (error) {
                    console.error('重置阈值失败:', error);
                    this.showMessage(error.response?.data?.detail || '重置阈值失败', 'error');
                } finally {
                    delete this.resetting[key];
                    this.resetting = { ...this.resetting };
                }
            },
            
            // 显示反馈对话框
            showFeedbackDialog(filterName, metricName) {
                this.feedbackDialog.filterName = filterName;
                this.feedbackDialog.metricName = metricName;
                this.feedbackDialog.form = {
                    predicted_score: 0.5,
                    actual_result: 'positive',
                    action: 'approve',
                    comments: ''
                };
                this.feedbackDialog.visible = true;
            },
            
            // 关闭反馈对话框
            closeFeedbackDialog() {
                this.feedbackDialog.visible = false;
            },
            
            // 提交反馈
            async submitFeedback() {
                if (!this.feedbackDialog.form.predicted_score || !this.feedbackDialog.form.actual_result || !this.feedbackDialog.form.action) {
                    this.showMessage('请填写完整的反馈信息', 'warning');
                    return;
                }
                
                this.feedbackDialog.submitting = true;
                try {
                    const response = await axios.post(API.threshold.feedback, {
                        filter_name: this.feedbackDialog.filterName,
                        metric_name: this.feedbackDialog.metricName,
                        predicted_score: parseFloat(this.feedbackDialog.form.predicted_score),
                        actual_result: this.feedbackDialog.form.actual_result,
                        action: this.feedbackDialog.form.action,
                        comments: this.feedbackDialog.form.comments
                    });
                    
                    this.showMessage('反馈提交成功！', 'success');
                    this.closeFeedbackDialog();
                    await this.refreshData();
                } catch (error) {
                    console.error('提交反馈失败:', error);
                    this.showMessage(error.response?.data?.detail || '提交反馈失败', 'error');
                } finally {
                    this.feedbackDialog.submitting = false;
                }
            },
            
            // 显示优化设置对话框
            showOptimizeDialog() {
                this.optimizeDialog.visible = true;
                // 加载当前设置
                this.loadOptimizeSettings();
            },
            
            // 关闭优化设置对话框
            closeOptimizeDialog() {
                this.optimizeDialog.visible = false;
            },
            
            // 加载优化设置
            async loadOptimizeSettings() {
                try {
                    const response = await axios.get(API.threshold.optimizeSettings);
                    this.optimizeDialog.settings = response.data;
                } catch (error) {
                    console.error('加载优化设置失败:', error);
                }
            },
            
            // 保存优化设置
            async saveOptimizeSettings() {
                try {
                    const response = await axios.post(API.threshold.optimizeSettings, this.optimizeDialog.settings);
                    this.showMessage('优化设置保存成功！', 'success');
                    this.closeOptimizeDialog();
                } catch (error) {
                    console.error('保存优化设置失败:', error);
                    this.showMessage(error.response?.data?.detail || '保存优化设置失败', 'error');
                }
            },
            
            // 获取过滤器图标
            getFilterIcon(filterName) {
                const icons = {
                    'tail_filter': '📏',
                    'ad_filter': '🚫',
                    'promo_filter': '🔗',
                    'keyword_filter': '🔤'
                };
                return icons[filterName] || '🔧';
            },
            
            // 获取过滤器显示名称
            getFilterDisplayName(filterName) {
                const names = {
                    'tail_filter': '尾部过滤器',
                    'ad_filter': '广告过滤器',
                    'promo_filter': '推广过滤器',
                    'keyword_filter': '关键词过滤器'
                };
                return names[filterName] || filterName;
            },
            
            // 获取指标显示名称
            getMetricDisplayName(metricName) {
                const names = {
                    'confidence': '置信度',
                    'similarity': '相似度',
                    'relevance': '相关性',
                    'threshold': '阈值'
                };
                return names[metricName] || metricName;
            },
            
            // 获取过滤器状态类型
            getFilterStatusClass(filterData) {
                const accuracies = [];
                for (const metricData of Object.values(filterData)) {
                    if (metricData.accuracy !== undefined) {
                        accuracies.push(metricData.accuracy);
                    }
                }
                
                if (accuracies.length === 0) return 'status-warning';
                
                const avgAccuracy = accuracies.reduce((sum, acc) => sum + acc, 0) / accuracies.length;
                
                if (avgAccuracy >= 0.9) return 'status-success';
                if (avgAccuracy >= 0.7) return 'status-warning';
                return 'status-danger';
            },
            
            // 获取过滤器状态文本
            getFilterStatusText(filterData) {
                const accuracies = [];
                for (const metricData of Object.values(filterData)) {
                    if (metricData.accuracy !== undefined) {
                        accuracies.push(metricData.accuracy);
                    }
                }
                
                if (accuracies.length === 0) return '无数据';
                
                const avgAccuracy = accuracies.reduce((sum, acc) => sum + acc, 0) / accuracies.length;
                
                if (avgAccuracy >= 0.9) return '优秀';
                if (avgAccuracy >= 0.7) return '良好';
                return '需要改进';
            },
            
            // 获取准确率样式类
            getAccuracyClass(accuracy) {
                if (accuracy >= 0.9) return 'high-accuracy';
                if (accuracy >= 0.7) return 'medium-accuracy';
                return 'low-accuracy';
            },
            
            // 获取图表引用
            getChartRef(filterName, metricName) {
                return `chart_${filterName}_${metricName}`;
            },
            
            // 格式化时间
            formatTime(time) {
                if (!time) return '从未';
                
                const date = new Date(time);
                const now = new Date();
                const diff = (now - date) / 1000; // 秒
                
                if (diff < 60) {
                    return `${Math.floor(diff)}秒前`;
                } else if (diff < 3600) {
                    return `${Math.floor(diff / 60)}分钟前`;
                } else if (diff < 86400) {
                    return `${Math.floor(diff / 3600)}小时前`;
                } else if (diff < 2592000) {
                    return `${Math.floor(diff / 86400)}天前`;
                } else {
                    return date.toLocaleDateString('zh-CN');
                }
            },
            
            // 显示消息提示
            showMessage(message, type = 'info') {
                // 创建消息提示元素
                const messageDiv = document.createElement('div');
                messageDiv.className = `message-toast message-${type}`;
                messageDiv.textContent = message;
                
                // 添加样式
                messageDiv.style.cssText = `
                    position: fixed;
                    top: 20px;
                    right: 20px;
                    padding: 12px 20px;
                    border-radius: 6px;
                    color: white;
                    font-weight: 500;
                    z-index: 10000;
                    animation: slideIn 0.3s ease;
                    max-width: 300px;
                    word-wrap: break-word;
                `;
                
                // 根据类型设置背景色
                switch (type) {
                    case 'success':
                        messageDiv.style.backgroundColor = '#67c23a';
                        break;
                    case 'warning':
                        messageDiv.style.backgroundColor = '#e6a23c';
                        break;
                    case 'error':
                        messageDiv.style.backgroundColor = '#f56c6c';
                        break;
                    default:
                        messageDiv.style.backgroundColor = '#409eff';
                }
                
                document.body.appendChild(messageDiv);
                
                // 3秒后自动移除
                setTimeout(() => {
                    messageDiv.style.animation = 'slideOut 0.3s ease';
                    setTimeout(() => {
                        if (messageDiv.parentNode) {
                            messageDiv.parentNode.removeChild(messageDiv);
                        }
                    }, 300);
                }, 3000);
            },
            
            // 检查认证状态
            async checkAuth() {
                try {
                    const token = localStorage.getItem('authToken');
                    if (!token) {
                        window.location.href = '/static/login.html';
                        return false;
                    }
                    
                    // 验证token有效性
                    const response = await axios.get(API.admin.profile);
                    return true;
                } catch (error) {
                    if (error.response && error.response.status === 401) {
                        localStorage.removeItem('authToken');
                        window.location.href = '/static/login.html';
                    }
                    return false;
                }
            }
        },
        
        async mounted() {
            // 检查认证状态
            const isAuthenticated = await this.checkAuth();
            if (!isAuthenticated) {
                return;
            }
            
            // 加载初始数据
            await this.refreshData();
            
            // 设置axios拦截器
            if (typeof setupAxiosAuth === 'function') {
                setupAxiosAuth();
            }
            
            // 设置定时刷新
            setInterval(() => {
                if (!this.loading && !this.optimizing) {
                    this.refreshData();
                }
            }, 30000); // 每30秒刷新一次
        }
    });
    
    // 挂载应用
    thresholdApp.mount('#app');
});

// 添加CSS动画
const style = document.createElement('style');
style.textContent = `
@keyframes slideIn {
    from {
        transform: translateX(100%);
        opacity: 0;
    }
    to {
        transform: translateX(0);
        opacity: 1;
    }
}

@keyframes slideOut {
    from {
        transform: translateX(0);
        opacity: 1;
    }
    to {
        transform: translateX(100%);
        opacity: 0;
    }
}

.message-toast {
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}
`;
document.head.appendChild(style);