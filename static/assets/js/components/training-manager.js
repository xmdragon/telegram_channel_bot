// 训练数据管理组件
const { createApp } = Vue;
const { ElMessage, ElMessageBox } = ElementPlus;

const app = createApp({
    data() {
        return {
            // 统计数据
            stats: {
                totalSamples: 0,
                uniqueSamples: 0,
                mediaFiles: 0,
                storageSize: 0
            },
            
            // 表格数据
            samples: [],
            selectedSamples: [],
            currentPage: 1,
            pageSize: 20,
            totalCount: 0,
            loading: false,
            
            // 搜索和筛选
            searchText: '',
            filterType: 'all',
            
            // 对话框
            detailDialog: false,
            currentSample: null,
            duplicateDialog: false,
            duplicateLoading: false,
            duplicateGroups: [],
            duplicateSamplesCount: 0
        }
    },
    
    computed: {
        // 是否为管理员
        isAdmin() {
            const adminInfo = localStorage.getItem('admin_info');  // 修正键名
            if (adminInfo) {
                const admin = JSON.parse(adminInfo);
                return admin.is_super_admin || (admin.permissions && admin.permissions.includes('training.manage'));
            }
            return false;
        }
    },
    
    methods: {
        // 加载样本数据
        async loadSamples() {
            this.loading = true;
            try {
                const params = {
                    page: this.currentPage,
                    size: this.pageSize,
                    search: this.searchText,
                    filter: this.filterType
                };
                
                const response = await axios.get('/api/training/ad-samples', { params });
                this.samples = response.data.samples;
                this.totalCount = response.data.total;
                
                // 加载统计信息
                await this.loadStatistics();
            } catch (error) {
                console.error('加载样本数据失败:', error);
                ElMessage.error('加载样本数据失败');
            } finally {
                this.loading = false;
            }
        },
        
        // 加载统计信息
        async loadStatistics() {
            try {
                const response = await axios.get('/api/training/statistics');
                this.stats = response.data;
            } catch (error) {
                console.error('加载统计信息失败:', error);
            }
        },
        
        // 处理选择变化
        handleSelectionChange(selection) {
            this.selectedSamples = selection;
        },
        
        // 显示详情
        showDetail(sample) {
            this.currentSample = sample;
            this.detailDialog = true;
        },
        
        // 删除单个样本
        async deleteSample(sample) {
            try {
                await ElMessageBox.confirm(
                    `确定要删除ID为 ${sample.id} 的训练样本吗？`,
                    '删除确认',
                    {
                        confirmButtonText: '确定删除',
                        cancelButtonText: '取消',
                        type: 'warning',
                    }
                );
                
                await axios.delete(`/api/training/ad-samples/${sample.id}`);
                ElMessage.success('删除成功');
                await this.loadSamples();
            } catch (error) {
                if (error !== 'cancel') {
                    console.error('删除失败:', error);
                    ElMessage.error('删除失败');
                }
            }
        },
        
        // 批量删除
        async deleteSelected() {
            if (!this.selectedSamples.length) {
                ElMessage.warning('请先选择要删除的样本');
                return;
            }
            
            try {
                await ElMessageBox.confirm(
                    `确定要删除选中的 ${this.selectedSamples.length} 个样本吗？`,
                    '批量删除确认',
                    {
                        confirmButtonText: '确定删除',
                        cancelButtonText: '取消',
                        type: 'warning',
                    }
                );
                
                const ids = this.selectedSamples.map(s => s.id);
                await axios.delete('/api/training/ad-samples/batch', { data: { ids } });
                
                ElMessage.success(`成功删除 ${ids.length} 个样本`);
                await this.loadSamples();
            } catch (error) {
                if (error !== 'cancel') {
                    console.error('批量删除失败:', error);
                    ElMessage.error('批量删除失败');
                }
            }
        },
        
        // 显示重复检测
        async showDuplicates() {
            this.duplicateDialog = true;
            this.duplicateLoading = true;
            
            try {
                // axios拦截器会自动添加认证头
                const response = await axios.post('/api/training/ad-samples/detect-duplicates');
                this.duplicateGroups = response.data.groups;
                this.duplicateSamplesCount = response.data.total_duplicates;
                
                if (!this.duplicateGroups.length) {
                    ElMessage.success('没有发现重复或相似的样本');
                    this.duplicateDialog = false;
                }
            } catch (error) {
                console.error('检测重复失败:', error);
                ElMessage.error('检测重复失败');
                this.duplicateDialog = false;
            } finally {
                this.duplicateLoading = false;
            }
        },
        
        // 合并组
        mergeGroup(group) {
            // 保留第一个，其他都不保留
            group.samples.forEach((sample, idx) => {
                sample.keep = idx === 0;
            });
        },
        
        // 应用去重
        async applyDeduplicate() {
            try {
                // 收集要删除的样本ID
                const toDelete = [];
                this.duplicateGroups.forEach(group => {
                    group.samples.forEach(sample => {
                        if (!sample.keep) {
                            toDelete.push(sample.id);
                        }
                    });
                });
                
                if (!toDelete.length) {
                    ElMessage.warning('没有选择要删除的样本');
                    return;
                }
                
                await ElMessageBox.confirm(
                    `将删除 ${toDelete.length} 个重复样本，是否继续？`,
                    '去重确认',
                    {
                        confirmButtonText: '确定',
                        cancelButtonText: '取消',
                        type: 'warning',
                    }
                );
                
                const response = await axios.post('/api/training/ad-samples/deduplicate', {
                    to_delete: toDelete
                });
                
                ElMessage.success(response.data.message);
                this.duplicateDialog = false;
                await this.loadSamples();
            } catch (error) {
                if (error !== 'cancel') {
                    console.error('去重失败:', error);
                    ElMessage.error('去重失败');
                }
            }
        },
        
        // 优化存储
        async optimizeStorage() {
            try {
                await ElMessageBox.confirm(
                    '优化存储将：\n1. 转换视频为快照\n2. 压缩图片\n3. 清理无效文件\n\n是否继续？',
                    '优化存储',
                    {
                        confirmButtonText: '开始优化',
                        cancelButtonText: '取消',
                        type: 'info',
                        dangerouslyUseHTMLString: true
                    }
                );
                
                ElMessage.info('正在优化存储，请稍候...');
                const response = await axios.post('/api/training/optimize-storage');
                
                ElMessage.success(`优化完成！节省空间: ${this.formatSize(response.data.saved_space)}`);
                await this.loadStatistics();
            } catch (error) {
                if (error !== 'cancel') {
                    console.error('优化存储失败:', error);
                    ElMessage.error('优化存储失败');
                }
            }
        },
        
        // 打开媒体文件管理
        openMediaManager() {
            window.open('/static/media_manager.html', '_blank');
        },
        
        // 重载模型
        async reloadModel() {
            try {
                await ElMessageBox.confirm(
                    '重新加载训练数据到AI模型，这将刷新所有缓存的训练数据。是否继续？',
                    '重载模型',
                    {
                        confirmButtonText: '确定重载',
                        cancelButtonText: '取消',
                        type: 'info',
                    }
                );
                
                ElMessage.info('正在重载模型...');
                const response = await axios.post('/api/training/reload-model');
                
                ElMessage.success(response.data.message || '模型重载成功');
            } catch (error) {
                if (error !== 'cancel') {
                    console.error('重载模型失败:', error);
                    ElMessage.error('重载模型失败');
                }
            }
        },
        
        // 格式化函数
        formatSize(bytes) {
            if (!bytes) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        },
        
        formatTime(timestamp) {
            if (!timestamp) return '';
            const date = new Date(timestamp);
            return date.toLocaleString('zh-CN');
        },
        
        formatSource(source) {
            const sourceMap = {
                'user_feedback': '用户反馈',
                'manual': '手动添加',
                'auto': '自动学习',
                'import': '导入'
            };
            return sourceMap[source] || source;
        },
        
        getSourceType(source) {
            const typeMap = {
                'user_feedback': 'warning',
                'manual': 'success',
                'auto': 'info',
                'import': 'primary'
            };
            return typeMap[source] || '';
        },
        
        truncateText(text, length) {
            if (!text) return '';
            if (text.length <= length) return text;
            return text.substring(0, length) + '...';
        },
        
        // 检查权限
        checkPermission() {
            if (!this.isAdmin) {
                ElMessage.warning('您没有权限访问此页面');
                setTimeout(() => {
                    window.location.href = '/';
                }, 1500);
                return false;
            }
            return true;
        }
    },
    
    async mounted() {
        // 初始化权限检查
        const isAuthorized = await authManager.initPageAuth('training.view');
        if (!isAuthorized) {
            return;
        }
        
        // 检查管理权限
        if (!this.checkPermission()) {
            return;
        }
        
        // 初始加载数据
        this.loadSamples();
        
        // 定期刷新统计信息
        this.statsInterval = setInterval(() => {
            this.loadStatistics();
        }, 30000); // 30秒刷新一次
    },
    
    beforeUnmount() {
        if (this.statsInterval) {
            clearInterval(this.statsInterval);
        }
    }
});

app.use(ElementPlus);

// 确保组件加载navbar
if (window.NavBar) {
    app.component('nav-bar', window.NavBar);
}

app.mount('#app');