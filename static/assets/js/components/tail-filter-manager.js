// 尾部过滤数据管理组件
const { createApp } = Vue;
const { ElMessage, ElMessageBox } = ElementPlus;

const app = createApp({
    data() {
        return {
            // 表格数据
            allSamples: [],  // 所有数据
            samples: [],      // 当前页显示的数据
            selectedSamples: [],
            currentPage: 1,
            pageSize: 20,
            totalCount: 0,
            loading: false,
            
            // 搜索
            searchText: '',
            
            // 统计
            totalSamples: 0,
            validSamples: 0,
            samplesWithSeparator: 0,
            todayAdded: 0,
            
            // 对话框
            detailDialog: false,
            currentSample: null
        }
    },
    
    methods: {
        // 加载样本数据
        async loadSamples() {
            this.loading = true;
            try {
                const response = await axios.get('/api/training/tail-filter-samples');
                this.allSamples = response.data.samples || [];
                this.totalCount = this.allSamples.length;
                
                // 计算统计信息
                this.calculateStats();
                
                // 更新当前页数据
                this.updatePageData();
            } catch (error) {
                console.error('加载尾部过滤样本失败:', error);
                ElMessage.error('加载数据失败');
            } finally {
                this.loading = false;
            }
        },
        
        // 更新当前页显示的数据
        updatePageData() {
            // 先进行搜索过滤
            let filteredSamples = this.allSamples;
            
            if (this.searchText && this.searchText.trim()) {
                const searchLower = this.searchText.toLowerCase().trim();
                filteredSamples = this.allSamples.filter(sample => {
                    // 搜索内容、描述和尾部内容
                    return (sample.content && sample.content.toLowerCase().includes(searchLower)) ||
                           (sample.description && sample.description.toLowerCase().includes(searchLower)) ||
                           (sample.tail_part && sample.tail_part.toLowerCase().includes(searchLower)) ||
                           (sample.separator && sample.separator.toLowerCase().includes(searchLower));
                });
            }
            
            // 更新总数
            this.totalCount = filteredSamples.length;
            
            // 分页
            const start = (this.currentPage - 1) * this.pageSize;
            const end = start + this.pageSize;
            this.samples = filteredSamples.slice(start, end);
        },
        
        // 计算统计信息
        calculateStats() {
            this.totalSamples = this.allSamples.length;
            this.validSamples = this.allSamples.filter(s => s.content && s.tail_part).length;
            this.samplesWithSeparator = this.allSamples.filter(s => s.separator).length;
            
            // 计算今日新增
            const today = new Date().toISOString().split('T')[0];
            this.todayAdded = this.allSamples.filter(s => {
                if (s.created_at) {
                    const sampleDate = new Date(s.created_at).toISOString().split('T')[0];
                    return sampleDate === today;
                }
                return false;
            }).length;
        },
        
        // 处理选择变化
        handleSelectionChange(selection) {
            this.selectedSamples = selection;
        },
        
        // 处理分页
        handlePageChange(page) {
            this.currentPage = page;
            this.updatePageData();
        },
        
        // 显示详情
        showDetail(sample) {
            this.currentSample = sample;
            this.detailDialog = true;
        },
        
        // 跳转到训练页面
        goToTrainingPage() {
            window.location.href = '/static/train.html';
        },
        
        // 处理搜索
        handleSearch() {
            // 重置到第一页
            this.currentPage = 1;
            // 更新显示数据
            this.updatePageData();
        },
        
        
        // 删除单个样本
        async deleteSample(sample) {
            try {
                await ElMessageBox.confirm(
                    '确定要删除这个尾部过滤样本吗？',
                    '确认删除',
                    {
                        confirmButtonText: '确定',
                        cancelButtonText: '取消',
                        type: 'warning',
                    }
                );
                
                const response = await axios.delete(`/api/training/tail-filter-samples/${sample.id}`);
                
                if (response.data.success) {
                    ElMessage.success('删除成功');
                    await this.loadSamples();
                } else {
                    ElMessage.error('删除失败');
                }
            } catch (error) {
                if (error !== 'cancel') {
                    console.error('删除失败:', error);
                    ElMessage.error('删除失败');
                }
            }
        },
        
        // 批量删除
        async deleteSelected() {
            if (!this.selectedSamples.length) return;
            
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
                
                // 逐个删除（因为API可能不支持批量删除）
                let successCount = 0;
                for (const id of ids) {
                    try {
                        await axios.delete(`/api/training/tail-filter-samples/${id}`);
                        successCount++;
                    } catch (e) {
                        console.error(`删除样本 ${id} 失败:`, e);
                    }
                }
                
                ElMessage.success(`成功删除 ${successCount} 个样本`);
                await this.loadSamples();
                
            } catch (error) {
                if (error !== 'cancel') {
                    console.error('批量删除失败:', error);
                    ElMessage.error('批量删除失败');
                }
            }
        },
        
        // 格式化函数
        formatTime(timestamp) {
            if (!timestamp) return '';
            const date = new Date(timestamp);
            return date.toLocaleString('zh-CN');
        },
        
        truncateText(text, length) {
            if (!text) return '';
            if (text.length <= length) return text;
            return text.substring(0, length) + '...';
        }
    },
    
    async mounted() {
        // 初始化权限检查
        const isAuthorized = await authManager.initPageAuth('training.view');
        if (!isAuthorized) {
            return;
        }
        
        // 初始加载数据
        this.loadSamples();
    }
});

app.use(ElementPlus);
if (window.NavBar) {
    app.component('nav-bar', window.NavBar);
}
if (window.TrainingNav) {
    app.component('training-nav', window.TrainingNav);
}
app.mount('#app');