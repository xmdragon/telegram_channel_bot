// 阈值监控组件 - 简化版本用于调试

// 确保API配置可用
const API = window.API;

// 检查依赖
if (!window.Vue) {
    console.error('Vue 未加载!');
}


const { createApp } = Vue;

const app = createApp({
    data() {
        return {
            loading: false,
            optimizing: false,
            searchText: '',
            stats: {},
            resetting: {},
            charts: {},
            
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
            
            optimizeDialog: {
                visible: false,
                settings: {
                    min_feedback: 10,
                    optimization_interval: 50,
                    window_size: 1000
                }
            }
        };
    },
    
    computed: {
        filteredStats() {
            if (!this.searchText) return this.stats;
            
            const search = this.searchText.toLowerCase();
            const filtered = {};
            
            Object.keys(this.stats).forEach(filterName => {
                if (this.getFilterDisplayName(filterName).toLowerCase().includes(search)) {
                    filtered[filterName] = this.stats[filterName];
                } else {
                    const matchingMetrics = {};
                    Object.keys(this.stats[filterName]).forEach(metricName => {
                        if (this.getMetricDisplayName(metricName).toLowerCase().includes(search)) {
                            matchingMetrics[metricName] = this.stats[filterName][metricName];
                        }
                    });
                    if (Object.keys(matchingMetrics).length > 0) {
                        filtered[filterName] = matchingMetrics;
                    }
                }
            });
            
            return filtered;
        },

        totalFeedback() {
            let total = 0;
            Object.values(this.stats).forEach(filterData => {
                Object.values(filterData).forEach(metricData => {
                    total += metricData.feedback_count || 0;
                });
            });
            return total;
        },

        averageAccuracy() {
            const metrics = [];
            Object.values(this.stats).forEach(filterData => {
                Object.values(filterData).forEach(metricData => {
                    if (metricData.feedback_count > 0) {
                        metrics.push(metricData.accuracy || 0);
                    }
                });
            });
            return metrics.length ? metrics.reduce((sum, acc) => sum + acc, 0) / metrics.length : 0;
        },

        lastUpdate() {
            let latest = null;
            Object.values(this.stats).forEach(filterData => {
                Object.values(filterData).forEach(metricData => {
                    if (metricData.last_updated) {
                        const time = new Date(metricData.last_updated);
                        if (!latest || time > latest) {
                            latest = time;
                        }
                    }
                });
            });
            return latest;
        }
    },
    
    methods: {
        async refreshData(silent = false) {
            if (!silent) this.loading = true;
            try {
                const response = await axios.get(API.training.thresholdsStats, {
                    headers: { 'Authorization': 'Bearer ' + window.getAuthToken() }
                });
                
                if (response.data.success) {
                    this.stats = response.data.data;
                    await this.$nextTick();
                    this.updateCharts();
                    
                    if (!silent) {
                        window.SimpleUI.showMessage('数据刷新成功');
                    }
                }
            } catch (error) {
                console.error('获取数据失败:', error);
                window.SimpleUI.showMessage('获取数据失败: ' + (error.response?.data?.detail || error.message), 'error');
            } finally {
                this.loading = false;
            }
        },

        async optimizeAllThresholds() {
            this.optimizing = true;
            try {
                const response = await axios.post(API.training.thresholdsOptimize, {}, {
                    headers: { 'Authorization': 'Bearer ' + window.getAuthToken() }
                });
                
                if (response.data.success) {
                    this.stats = response.data.data;
                    await this.$nextTick();
                    this.updateCharts();
                    window.SimpleUI.showMessage('阈值优化完成');
                }
            } catch (error) {
                console.error('优化失败:', error);
                window.SimpleUI.showMessage('优化失败: ' + (error.response?.data?.detail || error.message), 'error');
            } finally {
                this.optimizing = false;
            }
        },

        async resetThreshold(filterName, metricName) {
            const key = filterName + '_' + metricName;
            
            try {
                const confirmed = await window.SimpleUI.confirm(
                    `确定要重置 ${this.getFilterDisplayName(filterName)} - ${this.getMetricDisplayName(metricName)} 的阈值吗？`
                );
                if (!confirmed) return;

                this.resetting[key] = true;
                
                const response = await axios.post(API.training.thresholdsReset(filterName, metricName), {}, {
                    headers: { 'Authorization': 'Bearer ' + window.getAuthToken() }
                });
                
                if (response.data.success) {
                    await this.refreshData(true);
                    window.SimpleUI.showMessage('阈值重置成功');
                }
            } catch (error) {
                if (error !== 'cancel') {
                    console.error('重置失败:', error);
                    window.SimpleUI.showMessage('重置失败: ' + (error.response?.data?.detail || error.message), 'error');
                }
            } finally {
                this.resetting[key] = false;
            }
        },

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

        async submitFeedback() {
            this.feedbackDialog.submitting = true;
            try {
                const data = {
                    filter_name: this.feedbackDialog.filterName,
                    metric_name: this.feedbackDialog.metricName,
                    ...this.feedbackDialog.form
                };

                const response = await axios.post(API.messages.testMessageFeedback, data, {
                    headers: { 'Authorization': 'Bearer ' + window.getAuthToken() }
                });
                
                if (response.data.success) {
                    this.feedbackDialog.visible = false;
                    await this.refreshData(true);
                    window.SimpleUI.showMessage('反馈提交成功');
                }
            } catch (error) {
                console.error('提交反馈失败:', error);
                window.SimpleUI.showMessage('提交反馈失败: ' + (error.response?.data?.detail || error.message), 'error');
            } finally {
                this.feedbackDialog.submitting = false;
            }
        },

        showOptimizeDialog() {
            this.optimizeDialog.visible = true;
        },

        closeFeedbackDialog() {
            this.feedbackDialog.visible = false;
        },

        closeOptimizeDialog() {
            this.optimizeDialog.visible = false;
        },

        saveOptimizeSettings() {
            window.SimpleUI.showMessage('优化设置已保存');
            this.optimizeDialog.visible = false;
        },

        async exportConfig() {
            try {
                const response = await axios.get(API.training.thresholdsStats, {
                    headers: { 'Authorization': 'Bearer ' + window.getAuthToken() }
                });
                
                const data = JSON.stringify(response.data.data, null, 2);
                const blob = new Blob([data], { type: 'application/json' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `threshold_config_${new Date().toISOString().slice(0, 19).replace(/[:-]/g, '')}.json`;
                a.click();
                URL.revokeObjectURL(url);
                
                window.SimpleUI.showMessage('配置导出成功');
            } catch (error) {
                window.SimpleUI.showMessage('导出失败: ' + error.message, 'error');
            }
        },

        updateCharts() {
            Object.keys(this.stats).forEach(filterName => {
                Object.keys(this.stats[filterName]).forEach(metricName => {
                    const metricData = this.stats[filterName][metricName];
                    if (metricData.history && metricData.history.length > 1) {
                        this.createChart(filterName, metricName, metricData.history);
                    }
                });
            });
        },

        createChart(filterName, metricName, history) {
            const refName = this.getChartRef(filterName, metricName);
            const canvas = document.querySelector(`canvas[data-ref="${refName}"]`);
            
            if (!canvas) return;
            
            const ctx = canvas.getContext('2d');
            
            // 销毁现有图表
            const chartKey = filterName + '_' + metricName;
            if (this.charts[chartKey]) {
                this.charts[chartKey].destroy();
            }
            
            // 创建新图表
            this.charts[chartKey] = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: history.map((_, i) => `更新${i + 1}`),
                    datasets: [{
                        label: '阈值变化',
                        data: history,
                        borderColor: '#409eff',
                        backgroundColor: 'rgba(64, 158, 255, 0.1)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.3
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true,
                            max: 1
                        }
                    },
                    plugins: {
                        legend: {
                            display: false
                        }
                    }
                }
            });
        },

        // 工具函数
        getChartRef(filterName, metricName) {
            return 'chart_' + filterName + '_' + metricName;
        },

        getFilterDisplayName(filterName) {
            const names = {
                'tail_filter': '尾部过滤器',
                'ad_detector': '广告检测器',
                'footer_promo_filter': '推广链接过滤器',
                'promo_filter': '推广过滤器',
                'chat_filter': '聊天检测器'
            };
            return names[filterName] || filterName;
        },

        getFilterIcon(filterName) {
            const icons = {
                'tail_filter': '✂️',
                'ad_detector': '🛡️',
                'footer_promo_filter': '🔗',
                'promo_filter': '🚫',
                'chat_filter': '💬'
            };
            return icons[filterName] || '🎯';
        },

        getMetricDisplayName(metricName) {
            const names = {
                'intelligent': '智能过滤',
                'semantic': '语义过滤',
                'separator_confidence': '分隔符置信度',
                'semantic_score': '语义分析',
                'classifier': '分类器',
                'keywords': '关键词',
                'score': '综合评分',
                'detection': '检测阈值'
            };
            return names[metricName] || metricName;
        },

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

        getFilterStatusType(filterData) {
            const metrics = Object.values(filterData);
            const avgAccuracy = metrics.reduce((sum, m) => sum + (m.accuracy || 0), 0) / metrics.length;
            
            if (avgAccuracy >= 0.9) return 'success';
            if (avgAccuracy >= 0.7) return 'warning';
            return 'danger';
        },

        getFilterStatusText(filterData) {
            const metrics = Object.values(filterData);
            const avgAccuracy = metrics.reduce((sum, m) => sum + (m.accuracy || 0), 0) / metrics.length;
            
            if (avgAccuracy >= 0.9) return '优秀';
            if (avgAccuracy >= 0.7) return '良好';
            return '待优化';
        },

        getAccuracyClass(accuracy) {
            if (accuracy >= 0.9) return 'accuracy-good';
            if (accuracy >= 0.7) return 'accuracy-warning';
            return 'accuracy-danger';
        },

        formatTime(timestamp) {
            if (!timestamp) return '未更新';
            const date = new Date(timestamp);
            return date.toLocaleDateString() + ' ' + date.toLocaleTimeString().slice(0, 5);
        },

        // 消息提示已统一使用 window.SimpleUI.showMessage
    },
    
    mounted() {
        this.refreshData();
        // 每30秒自动刷新
        setInterval(() => {
            if (!this.loading) {
                this.refreshData(true);
            }
        }, 30000);
    }
});

// 注册组件
app.component('nav-bar', NavBar);
app.component('training-nav', TrainingNav);

// 注册Element Plus组件

// 挂载应用 - 确保DOM就绪
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        app.mount('#app');
    });
} else {
    // DOM已准备就绪
    app.mount('#app');
}