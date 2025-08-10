/**
 * AI训练页面组件
 */
const { createApp } = Vue;
const { ElMessage, ElMessageBox } = ElementPlus;

const TrainApp = {
    data() {
        return {
            activeTab: 'train',
            loading: false,
            loadingText: '加载中...',
            submitting: false,
            applying: false,
            
            // 频道列表
            channels: [],
            
            // 训练表单
            trainingForm: {
                channel_id: '',
                original_message: '',
                tail_content: ''
            },
            
            // 预览
            filteredPreview: '',
            
            // 统计信息
            stats: {
                totalChannels: 0,
                trainedChannels: 0,
                totalSamples: 0,
                todayTraining: 0
            },
            
            // 训练历史
            trainingHistory: []
        };
    },
    
    mounted() {
        this.init();
    },
    
    methods: {
        async init() {
            await this.loadChannels();
            await this.loadStats();
            await this.loadHistory();
        },
        
        async loadChannels() {
            try {
                const response = await axios.get('/api/training/channels');
                this.channels = response.data.channels || [];
            } catch (error) {
                console.error('加载频道失败:', error);
                ElMessage.error('加载频道列表失败');
            }
        },
        
        async loadStats() {
            try {
                const response = await axios.get('/api/training/stats');
                this.stats = response.data;
            } catch (error) {
                console.error('加载统计失败:', error);
            }
        },
        
        async loadHistory() {
            try {
                const response = await axios.get('/api/training/history');
                this.trainingHistory = response.data.history || [];
            } catch (error) {
                console.error('加载历史失败:', error);
            }
        },
        
        updatePreview() {
            if (this.trainingForm.original_message && this.trainingForm.tail_content) {
                const tailIndex = this.trainingForm.original_message.indexOf(this.trainingForm.tail_content);
                if (tailIndex > -1) {
                    this.filteredPreview = this.trainingForm.original_message.substring(0, tailIndex).trim();
                } else {
                    this.filteredPreview = this.trainingForm.original_message;
                }
            } else {
                this.filteredPreview = '';
            }
        },
        
        clearForm() {
            this.trainingForm = {
                channel_id: '',
                original_message: '',
                tail_content: ''
            };
            this.filteredPreview = '';
        },
        
        async submitTraining() {
            if (!this.trainingForm.channel_id) {
                ElMessage.warning('请选择频道');
                return;
            }
            
            if (!this.trainingForm.original_message || !this.trainingForm.tail_content) {
                ElMessage.warning('请填写完整的训练数据');
                return;
            }
            
            this.submitting = true;
            try {
                const response = await axios.post('/api/training/submit', this.trainingForm);
                
                if (response.data.success) {
                    ElMessage.success('训练样本已提交');
                    this.clearForm();
                    await this.loadHistory();
                    await this.loadStats();
                    
                    // 更新频道的训练计数
                    const channel = this.channels.find(c => c.id === this.trainingForm.channel_id);
                    if (channel) {
                        channel.trained_count = (channel.trained_count || 0) + 1;
                    }
                } else {
                    ElMessage.error(response.data.message || '提交失败');
                }
            } catch (error) {
                ElMessage.error('提交失败: ' + (error.response?.data?.detail || error.message));
            } finally {
                this.submitting = false;
            }
        },
        
        async applyTraining() {
            try {
                await ElMessageBox.confirm(
                    '确定要应用所有训练数据吗？这将重新训练AI模型。',
                    '确认操作',
                    {
                        confirmButtonText: '确定',
                        cancelButtonText: '取消',
                        type: 'warning'
                    }
                );
                
                this.applying = true;
                const response = await axios.post('/api/training/apply');
                if (response.data.success) {
                    ElMessage.success(response.data.message || '训练已应用，AI模型已更新');
                } else {
                    ElMessage.error(response.data.message || '应用失败');
                }
            } catch (error) {
                if (error !== 'cancel') {
                    ElMessage.error('应用失败: ' + (error.response?.data?.detail || error.message));
                }
            } finally {
                this.applying = false;
            }
        },
        
        async deleteTraining(id) {
            try {
                await ElMessageBox.confirm(
                    '确定要删除这条训练记录吗？',
                    '确认删除',
                    {
                        confirmButtonText: '确定',
                        cancelButtonText: '取消',
                        type: 'warning'
                    }
                );
                
                const response = await axios.delete(`/api/training/${id}`);
                if (response.data.success) {
                    ElMessage.success('删除成功');
                    await this.loadHistory();
                    await this.loadStats();
                } else {
                    ElMessage.error(response.data.message || '删除失败');
                }
            } catch (error) {
                if (error !== 'cancel') {
                    console.error('删除失败:', error);
                }
            }
        },
        
        formatTime(timeStr) {
            if (!timeStr) return '';
            const date = new Date(timeStr);
            const now = new Date();
            const diff = (now - date) / 1000 / 60; // 分钟
            
            if (diff < 60) return `${Math.floor(diff)}分钟前`;
            if (diff < 1440) return `${Math.floor(diff / 60)}小时前`;
            
            return date.toLocaleDateString('zh-CN', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit'
            });
        }
    }
};

// 导出到全局变量供页面使用
window.TrainApp = TrainApp;