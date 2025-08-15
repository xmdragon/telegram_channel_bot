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
            todayAdded: 0,
            
            // 对话框
            detailDialog: false,
            currentSample: null,
            
            // 编辑对话框
            editDialog: false,
            editingSample: null,
            submitting: false,
            
            // 重复检测对话框
            duplicateDialog: false,
            duplicateLoading: false,
            duplicateGroups: [],
            duplicateSamplesCount: 0
        }
    },
    
    methods: {
        // 加载样本数据
        async loadSamples() {
            console.log('🔄 开始加载尾部过滤样本数据...');
            this.loading = true;
            try {
                console.log('📡 发送API请求: GET /api/training/tail-filter-samples');
                const response = await axios.get('/api/training/tail-filter-samples');
                console.log('📥 收到API响应:', {
                    status: response.status,
                    dataKeys: Object.keys(response.data || {}),
                    samplesCount: response.data.samples ? response.data.samples.length : 0
                });
                
                this.allSamples = response.data.samples || [];
                this.totalCount = this.allSamples.length;
                
                console.log(`✅ 成功加载 ${this.totalCount} 条样本数据`);
                
                // 按创建时间倒序排序（最新的在前）
                this.allSamples.sort((a, b) => {
                    const timeA = new Date(a.created_at || 0).getTime();
                    const timeB = new Date(b.created_at || 0).getTime();
                    return timeB - timeA;
                });
                
                // 计算统计信息
                this.calculateStats();
                console.log('📊 统计信息计算完成:', {
                    totalSamples: this.totalSamples,
                    validSamples: this.validSamples,
                    todayAdded: this.todayAdded
                });
                
                // 更新当前页数据
                this.updatePageData();
                console.log(`📄 页面数据更新完成 - 当前页: ${this.currentPage}, 显示: ${this.samples.length} 条`);
            } catch (error) {
                console.error('❌ 加载尾部过滤样本失败:', error);
                console.error('错误详情:', {
                    message: error.message,
                    status: error.response?.status,
                    data: error.response?.data
                });
                ElMessage.error('加载数据失败');
            } finally {
                this.loading = false;
                console.log('🏁 加载过程结束');
            }
        },
        
        // 更新当前页显示的数据
        updatePageData() {
            console.log('🔄 更新页面数据...', {
                allSamples: this.allSamples.length,
                currentPage: this.currentPage,
                pageSize: this.pageSize,
                searchText: this.searchText
            });
            
            // 先进行搜索过滤
            let filteredSamples = this.allSamples;
            
            if (this.searchText && this.searchText.trim()) {
                const searchLower = this.searchText.toLowerCase().trim();
                filteredSamples = this.allSamples.filter(sample => {
                    // 搜索内容、描述和尾部内容
                    return (sample.content && sample.content.toLowerCase().includes(searchLower)) ||
                           (sample.description && sample.description.toLowerCase().includes(searchLower)) ||
                           (sample.tail_part && sample.tail_part.toLowerCase().includes(searchLower));
                });
            }
            
            // 更新总数
            this.totalCount = filteredSamples.length;
            
            // 分页
            const start = (this.currentPage - 1) * this.pageSize;
            const end = start + this.pageSize;
            this.samples = filteredSamples.slice(start, end);
            
            console.log('📄 页面数据更新完成:', {
                filteredCount: filteredSamples.length,
                pageStart: start,
                pageEnd: end,
                displayedCount: this.samples.length
            });
        },
        
        // 计算统计信息
        calculateStats() {
            this.totalSamples = this.allSamples.length;
            this.validSamples = this.allSamples.filter(s => s.content && s.tail_part).length;
            
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
            console.log('🔍 显示详情:', sample);
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
                    // console.error('删除失败:', error);
                    ElMessage.error('删除失败');
                }
            }
        },
        
        // 编辑样本
        editSample(sample) {
            console.log('✏️ 编辑样本:', sample);
            this.editingSample = {
                id: sample.id,
                tail_content: sample.tail_content
            };
            this.editDialog = true;
        },
        
        // 保存编辑
        async saveEdit() {
            if (!this.editingSample || !this.editingSample.tail_content.trim()) {
                ElMessage.warning('请输入尾部内容');
                return;
            }
            
            this.submitting = true;
            try {
                const response = await axios.put(`/api/training/tail-filter-samples/${this.editingSample.id}`, {
                    tail_content: this.editingSample.tail_content.trim()
                });
                
                if (response.data.success) {
                    ElMessage.success('保存成功');
                    this.editDialog = false;
                    this.editingSample = null;
                    await this.loadSamples();
                } else {
                    ElMessage.error(response.data.message || '保存失败');
                }
            } catch (error) {
                console.error('保存编辑失败:', error);
                ElMessage.error('保存失败');
            } finally {
                this.submitting = false;
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
                        // console.error(`删除样本 ${id} 失败:`, e);
                    }
                }
                
                ElMessage.success(`成功删除 ${successCount} 个样本`);
                await this.loadSamples();
                
            } catch (error) {
                if (error !== 'cancel') {
                    // console.error('批量删除失败:', error);
                    ElMessage.error('批量删除失败');
                }
            }
        },
        
        // 显示重复检测
        async showDuplicates() {
            this.duplicateDialog = true;
            this.duplicateLoading = true;
            
            try {
                const response = await axios.post('/api/training/tail-filter-samples/detect-duplicates');
                
                // 检查API响应是否成功
                if (response.data.success) {
                    this.duplicateGroups = response.data.groups || [];
                    this.duplicateSamplesCount = response.data.total_duplicates || 0;
                    
                    if (!this.duplicateGroups.length) {
                        ElMessage.info('没有发现重复的样本');
                        this.duplicateDialog = false;
                    }
                } else {
                    ElMessage.error('检测重复失败: ' + (response.data.error || '未知错误'));
                    this.duplicateDialog = false;
                }
            } catch (error) {
                console.error('检测重复失败:', error);
                ElMessage.error('检测重复失败: ' + (error.response?.data?.message || error.message));
                this.duplicateDialog = false;
            } finally {
                this.duplicateLoading = false;
            }
        },
        
        // 合并重复组
        mergeGroup(group) {
            // 默认保留第一个，删除其他
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
                            const sampleId = sample.id;
                            if (sampleId) {
                                toDelete.push(sampleId);
                            }
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
                
                const response = await axios.post('/api/training/tail-filter-samples/deduplicate', {
                    remove_ids: toDelete
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
        console.log('🚀 尾部过滤管理器组件开始挂载...');
        
        // 初始化权限检查
        console.log('🔐 检查权限...');
        const isAuthorized = await authManager.initPageAuth('training.view');
        if (!isAuthorized) {
            console.log('❌ 权限检查失败');
            return;
        }
        console.log('✅ 权限检查通过');
        
        // 初始加载数据
        console.log('📊 开始初始化数据加载...');
        await this.loadSamples();
        console.log('🎉 组件挂载完成');
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