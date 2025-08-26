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
            updating: {},
            charts: {},
            
            // 手动调整阈值相关状态
            adjustmentVisible: {},
            pendingValues: {},
            thresholdRanges: {},
            
            // 实时预览相关状态
            previewData: {},
            testContents: {},
            previewDebounceTimers: {},
            
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
                        window.SimpleUI.Message.success('数据刷新成功');
                    }
                }
            } catch (error) {
                console.error('获取数据失败:', error);
                window.SimpleUI.Message.error('获取数据失败: ' + (error.response?.data?.detail || error.message));
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
                    window.SimpleUI.Message.success('阈值优化完成');
                }
            } catch (error) {
                console.error('优化失败:', error);
                window.SimpleUI.Message.error('优化失败: ' + (error.response?.data?.detail || error.message));
            } finally {
                this.optimizing = false;
            }
        },

        async resetThreshold(filterName, metricName) {
            const key = filterName + '_' + metricName;
            
            try {
                const confirmed = await window.SimpleUI.MessageBox.confirm(
                    `确定要重置 ${this.getFilterDisplayName(filterName)} - ${this.getMetricDisplayName(metricName)} 的阈值吗？`
                );
                if (!confirmed) return;

                this.resetting[key] = true;
                
                const response = await axios.post(API.training.thresholdsReset(filterName, metricName), {}, {
                    headers: { 'Authorization': 'Bearer ' + window.getAuthToken() }
                });
                
                if (response.data.success) {
                    await this.refreshData(true);
                    window.SimpleUI.Message.success('阈值重置成功');
                }
            } catch (error) {
                if (error !== 'cancel') {
                    console.error('重置失败:', error);
                    window.SimpleUI.Message.error('重置失败: ' + (error.response?.data?.detail || error.message));
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
                    window.SimpleUI.Message.success('反馈提交成功');
                }
            } catch (error) {
                console.error('提交反馈失败:', error);
                window.SimpleUI.Message.error('提交反馈失败: ' + (error.response?.data?.detail || error.message));
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
            window.SimpleUI.Message.success('优化设置已保存');
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
                
                window.SimpleUI.Message.success('配置导出成功');
            } catch (error) {
                window.SimpleUI.Message.error('导出失败: ' + error.message);
            }
        },

        updateCharts() {
            // 延迟一点时间确保DOM已更新
            this.$nextTick(() => {
                setTimeout(() => {
                    Object.keys(this.stats).forEach(filterName => {
                        Object.keys(this.stats[filterName]).forEach(metricName => {
                            const metricData = this.stats[filterName][metricName];
                            if (metricData.history && metricData.history.length > 1) {
                                this.createChart(filterName, metricName, metricData.history);
                            }
                        });
                    });
                }, 200);
            });
        },

        createChart(filterName, metricName, history) {
            const refName = this.getChartRef(filterName, metricName);
            
            // 尝试多种方式查找canvas元素
            let canvas = document.getElementById(refName) || 
                        document.querySelector(`canvas[data-ref="${refName}"]`) ||
                        document.querySelector(`#${refName}`);
            
            if (!canvas) {
                // Canvas元素不存在，跳过图表创建
                return;
            }
            
            // 检查canvas的渲染状态
            if (canvas.width === 0 || canvas.height === 0) {
                // Canvas尺寸为0，延迟创建
                setTimeout(() => {
                    this.createChart(filterName, metricName, history);
                }, 100);
                return;
            }
            
            let ctx;
            try {
                ctx = canvas.getContext('2d');
            } catch (e) {
                return;
            }
            
            if (!ctx) {
                return;
            }
            
            // 销毁现有图表
            const chartKey = filterName + '_' + metricName;
            if (this.charts[chartKey]) {
                try {
                    this.charts[chartKey].destroy();
                    delete this.charts[chartKey];
                } catch (e) {
                    // 销毁失败时继续
                }
            }
            
            try {
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
                        interaction: {
                            intersect: false
                        },
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
            } catch (error) {
                // 图表创建失败时不影响其他功能
            }
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
                'promo_content_filter': '推广内容过滤器',
                'promo_vector_filter': '推广向量过滤器',
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
                'promo_content_filter': '🚫',
                'promo_vector_filter': '🧠',
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
                'detection': '检测阈值',
                'similarity': '相似度阈值',
                'min_length': '最小长度'
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

        // 手动阈值调整相关方法
        toggleAdjustment(filterName, metricName) {
            const key = filterName + '_' + metricName;
            this.adjustmentVisible[key] = !this.adjustmentVisible[key];
        },

        updateSliderValue(filterName, metricName, value) {
            const key = filterName + '_' + metricName;
            this.pendingValues[key] = parseFloat(value);
            
            // 触发实时预览（带防抖）
            this.debouncePreview(filterName, metricName, parseFloat(value));
        },

        updateInputValue(filterName, metricName, value) {
            const key = filterName + '_' + metricName;
            this.pendingValues[key] = parseFloat(value);
        },

        async applyThresholdChange(filterName, metricName, value) {
            const key = filterName + '_' + metricName;
            const numericValue = parseFloat(value);
            
            if (isNaN(numericValue)) {
                window.SimpleUI.Message.error('请输入有效的数值');
                return;
            }
            
            const min = this.getMinThreshold(filterName, metricName);
            const max = this.getMaxThreshold(filterName, metricName);
            
            if (numericValue < min || numericValue > max) {
                window.SimpleUI.Message.error(`阈值必须在 ${min} - ${max} 范围内`);
                return;
            }
            
            try {
                const confirmed = await window.SimpleUI.MessageBox.confirm(
                    `确定将 ${this.getFilterDisplayName(filterName)} - ${this.getMetricDisplayName(metricName)} 的阈值从 ${this.stats[filterName][metricName].current_threshold.toFixed(3)} 调整为 ${numericValue.toFixed(3)} 吗？`
                );
                if (!confirmed) return;

                this.updating[key] = true;
                
                const response = await axios.post(API.training.thresholdsManualUpdate, {
                    filter_name: filterName,
                    metric_name: metricName,
                    new_value: numericValue
                }, {
                    headers: { 'Authorization': 'Bearer ' + window.getAuthToken() }
                });
                
                if (response.data.success) {
                    await this.refreshData(true);
                    window.SimpleUI.Message.success(`阈值更新成功: ${response.data.old_value?.toFixed(3) || 'N/A'} → ${numericValue.toFixed(3)}`);
                    
                    // 清理待处理值
                    delete this.pendingValues[key];
                }
            } catch (error) {
                if (error !== 'cancel') {
                    window.SimpleUI.Message.error('更新阈值失败: ' + (error.response?.data?.detail || error.message));
                }
            } finally {
                this.updating[key] = false;
            }
        },

        getMinThreshold(filterName, metricName) {
            // 从thresholds.json获取最小值，或使用默认值
            return this.thresholdRanges[filterName + '_' + metricName]?.min || 0.0;
        },

        getMaxThreshold(filterName, metricName) {
            // 从thresholds.json获取最大值，或使用默认值
            return this.thresholdRanges[filterName + '_' + metricName]?.max || 1.0;
        },

        loadThresholdRanges() {
            // 基于常见过滤器的默认范围配置
            const defaultRanges = {
                'tail_filter_intelligent': { min: 0.3, max: 0.9 },
                'tail_filter_semantic': { min: 0.2, max: 0.8 },
                'ad_detector_classifier': { min: 0.4, max: 0.95 },
                'ad_detector_keywords': { min: 0.5, max: 1.0 },
                'footer_promo_filter_separator_confidence': { min: 0.3, max: 0.9 },
                'footer_promo_filter_semantic_score': { min: 0.2, max: 0.8 },
                'promo_filter_score': { min: 0.3, max: 0.9 },
                'promo_content_filter_detection': { min: 0.4, max: 0.95 },
                'promo_content_filter_semantic': { min: 0.3, max: 0.85 },
                'promo_vector_filter_similarity': { min: 0.75, max: 0.95 },
                'promo_vector_filter_min_length': { min: 10, max: 50 },
                'chat_filter_detection': { min: 0.3, max: 0.8 }
            };
            
            this.thresholdRanges = defaultRanges;
        },

        // 实时预览相关方法
        debouncePreview(filterName, metricName, testValue) {
            const key = filterName + '_' + metricName;
            
            // 清除之前的定时器
            if (this.previewDebounceTimers[key]) {
                clearTimeout(this.previewDebounceTimers[key]);
            }
            
            // 设置新的防抖定时器
            this.previewDebounceTimers[key] = setTimeout(() => {
                this.fetchPreviewData(filterName, metricName, testValue);
            }, 500); // 500ms防抖
        },

        async fetchPreviewData(filterName, metricName, testValue) {
            const key = filterName + '_' + metricName;
            
            try {
                const response = await axios.post(API.training.thresholdsPreview, {
                    filter_name: filterName,
                    metric_name: metricName,
                    test_value: testValue,
                    sample_content: this.testContents[key] || ""
                }, {
                    headers: { 'Authorization': 'Bearer ' + window.getAuthToken() }
                });
                
                if (response.data.success) {
                    this.previewData[key] = response.data;
                }
            } catch (error) {
                // 预览失败时不显示错误消息，避免干扰用户体验
                delete this.previewData[key];
            }
        },

        updateTestContent(filterName, metricName, content) {
            const key = filterName + '_' + metricName;
            this.testContents[key] = content;
            
            // 如果有当前预览数据，重新获取预览
            const currentValue = this.pendingValues[key] || this.stats[filterName][metricName].current_threshold;
            if (this.previewData[key]) {
                this.debouncePreview(filterName, metricName, currentValue);
            }
        },

        async runContentPreview(filterName, metricName) {
            const key = filterName + '_' + metricName;
            const currentValue = this.pendingValues[key] || this.stats[filterName][metricName].current_threshold;
            
            // 立即获取内容预测
            await this.fetchPreviewData(filterName, metricName, currentValue);
        },

        // 预览数据格式化方法
        formatDelta(delta) {
            const sign = delta > 0 ? '+' : '';
            return `${sign}${delta.toFixed(3)}`;
        },

        getPreviewDeltaClass(delta) {
            if (delta > 0) return 'delta-increase';
            if (delta < 0) return 'delta-decrease';
            return 'delta-neutral';
        },

        formatPredictionAction(action) {
            const actionMap = {
                'pass': '✅ 通过过滤',
                'filter': '🚫 将被过滤',
                'unknown': '❓ 未知',
                '需要实际过滤器测试': '⚙️ 需要测试'
            };
            return actionMap[action] || action;
        },

        getPredictionActionClass(action) {
            if (action === 'pass') return 'prediction-pass';
            if (action === 'filter') return 'prediction-filter';
            return 'prediction-unknown';
        },

        // 消息提示已统一使用 window.SimpleUI.showMessage
    },
    
    mounted() {
        this.loadThresholdRanges();
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