// 推广链接数据管理组件
const { createApp } = Vue;

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
            
            // 模态框
            detailDialog: false,
            currentSample: null,
            
            // 编辑模态框
            editDialog: false,
            editingSample: null,
            submitting: false,
            
            // 重复检测模态框
            duplicateDialog: false,
            duplicateLoading: false,
            duplicateGroups: [],
            duplicateSamplesCount: 0,
            
            // 排序相关
            sortField: 'created_at',
            sortOrder: 'desc',
            
            // 分页跳转
            jumpToPage: 1,
            
            // 分隔符类型映射（从API动态加载）
            separatorTypeLabels: {},
            separatorOptions: []
        }
    },
    
    methods: {
        // 加载分隔符配置
        async loadSeparatorPatterns() {
            try {
                const response = await axios.get(API.training.separatorPatterns, {
                    headers: { 'Authorization': 'Bearer ' + window.getAuthToken() }
                });
                
                if (response.data.success && response.data.data) {
                    const patterns = response.data.data;
                    this.separatorOptions = [];
                    this.separatorTypeLabels = {};
                    
                    // 添加"无分隔符"选项
                    this.separatorOptions.push({
                        value: '',
                        label: '无分隔符'
                    });
                    this.separatorTypeLabels[''] = '无分隔符';
                    
                    // 添加配置的分隔符（按权重排序）
                    const sortedPatterns = patterns.sort((a, b) => (b.weight || 0) - (a.weight || 0));
                    
                    sortedPatterns.forEach((pattern, index) => {
                        // 使用regex作为值，description作为标签
                        const value = pattern.regex;
                        const label = pattern.description;
                        
                        this.separatorOptions.push({
                            value: value,
                            label: label
                        });
                        this.separatorTypeLabels[value] = label;
                    });
                }
            } catch (error) {
                console.error('加载分隔符配置失败:', error);
                // 使用默认配置
                this.separatorOptions = [
                    { value: '', label: '无分隔符' },
                    { value: 'line_separator', label: '横线类 (━━━)' },
                    { value: 'dot_separator', label: '点类 (···)' },
                    { value: 'dash_separator', label: '破折号类 (---)' }
                ];
                this.separatorTypeLabels = {
                    '': '无分隔符',
                    'line_separator': '横线类 (━━━)',
                    'dot_separator': '点类 (···)',
                    'dash_separator': '破折号类 (---)'
                };
            }
        },
        
        // 加载样本数据
        async loadSamples() {
            this.loading = true;
            try {
                const response = await axios.get(API.training.promoSamples);
                
                this.allSamples = response.data.data?.samples || [];
                this.totalCount = this.allSamples.length;
                
                // 按创建时间倒序排序（最新的在前）
                this.allSamples.sort((a, b) => {
                    const timeA = new Date(a.created_at || 0).getTime();
                    const timeB = new Date(b.created_at || 0).getTime();
                    return timeB - timeA;
                });
                
                // 更新统计信息
                if (response.data.data?.statistics) {
                    this.totalSamples = response.data.data.statistics.total_samples || this.allSamples.length;
                    this.validSamples = response.data.data.statistics.active_samples || this.allSamples.length;
                    this.todayAdded = response.data.data.statistics.today_added || 0;
                } else {
                    this.calculateStats();
                }
                
                // 更新当前页数据
                this.updatePageData();
                
            } catch (error) {
                console.error('加载推广链接样本失败:', error);
                SimpleUI.showMessage('加载数据失败: ' + (error.response?.data?.detail || error.message), 'error');
                
                // 设置默认空数据
                this.allSamples = [];
                this.samples = [];
                this.totalCount = 0;
                this.totalSamples = 0;
                this.validSamples = 0;
                this.todayAdded = 0;
            } finally {
                this.loading = false;
            }
        },
        
        // 计算统计信息（后备方案）
        calculateStats() {
            this.totalSamples = this.allSamples.length;
            this.validSamples = this.allSamples.filter(s => s.promo_content && s.promo_content.trim()).length;
            
            // 计算今日新增
            const today = new Date();
            today.setHours(0, 0, 0, 0);
            this.todayAdded = this.allSamples.filter(s => {
                if (!s.created_at) return false;
                const sampleDate = new Date(s.created_at);
                sampleDate.setHours(0, 0, 0, 0);
                return sampleDate.getTime() === today.getTime();
            }).length;
        },
        
        // 更新当前页数据
        updatePageData() {
            let filteredSamples = this.allSamples;
            
            // 搜索过滤
            if (this.searchText) {
                const searchLower = this.searchText.toLowerCase();
                filteredSamples = this.allSamples.filter(sample =>
                    (sample.promo_content && sample.promo_content.toLowerCase().includes(searchLower)) ||
                    (sample.separator_type && this.getSeparatorTypeLabel(sample.separator_type).toLowerCase().includes(searchLower)) ||
                    (sample.id && sample.id.toString().includes(searchLower))
                );
            }
            
            // 分页
            const start = (this.currentPage - 1) * this.pageSize;
            const end = start + this.pageSize;
            this.samples = filteredSamples.slice(start, end);
            this.totalCount = filteredSamples.length;
        },
        
        // 搜索处理
        handleSearch() {
            this.currentPage = 1; // 重置到第一页
            this.updatePageData();
        },
        
        // 显示详情
        showDetail(sample) {
            this.currentSample = sample;
            this.detailDialog = true;
        },
        
        // 编辑样本
        editSample(sample) {
            this.editingSample = {
                id: sample.id,
                promo_content: sample.promo_content || '',
                separator_type: sample.separator_type || ''
            };
            this.editDialog = true;
        },
        
        // 保存编辑
        async saveEdit() {
            if (!this.editingSample || !this.editingSample.promo_content.trim()) {
                SimpleUI.showMessage('推广内容不能为空', 'error');
                return;
            }
            
            this.submitting = true;
            try {
                // 注意：这里需要后端实现PUT/PATCH端点
                const response = await axios.put(API.training.promoSampleById(this.editingSample.id), {
                    promo_content: this.editingSample.promo_content,
                    separator_type: this.editingSample.separator_type || null
                });
                
                SimpleUI.showMessage('样本更新成功', 'success');
                this.editDialog = false;
                this.editingSample = null;
                await this.loadSamples();
            } catch (error) {
                console.error('更新样本失败:', error);
                SimpleUI.showMessage('更新失败: ' + (error.response?.data?.detail || error.message), 'error');
            } finally {
                this.submitting = false;
            }
        },
        
        // 删除样本
        async deleteSample(sample) {
            const confirmed = await SimpleUI.showConfirm(
                '确定要删除这个推广链接样本吗？',
                '删除确认'
            );
            
            if (!confirmed) return;
            
            try {
                // 注意：这里需要后端实现DELETE端点
                await axios.delete(API.training.promoSampleById(sample.id));
                SimpleUI.showMessage('样本删除成功', 'success');
                await this.loadSamples();
            } catch (error) {
                console.error('删除样本失败:', error);
                SimpleUI.showMessage('删除失败: ' + (error.response?.data?.detail || error.message), 'error');
            }
        },
        
        // 跳转到训练页面
        goToTrainingPage(sample = null) {
            if (sample) {
                // 带样本数据的跳转（预填充）
                const params = new URLSearchParams({
                    promo_content: sample.promo_content || '',
                    separator_type: sample.separator_type || ''
                });
                window.location.href = API.pages.promoTraining + '?' + params.toString();
            } else {
                // 普通跳转
                window.location.href = API.pages.promoTraining;
            }
        },
        
        // 全选/取消全选
        selectAll(event) {
            if (event.target.checked) {
                this.selectedSamples = [...this.samples];
            } else {
                this.selectedSamples = [];
            }
        },
        
        // 处理单个样本选择
        handleSampleSelection(event) {
            const sample = event.target.value;
            if (event.target.checked) {
                if (!this.selectedSamples.includes(sample)) {
                    this.selectedSamples.push(sample);
                }
            } else {
                const index = this.selectedSamples.indexOf(sample);
                if (index > -1) {
                    this.selectedSamples.splice(index, 1);
                }
            }
        },
        
        // 批量删除
        async deleteSelected() {
            if (!this.selectedSamples.length) return;
            
            const confirmed = await SimpleUI.showConfirm(
                `确定要删除选中的 ${this.selectedSamples.length} 个样本吗？`,
                '批量删除确认'
            );
            
            if (!confirmed) return;
            
            try {
                const deletePromises = this.selectedSamples.map(sample =>
                    axios.delete(API.training.promoSampleById(sample.id))
                );
                
                await Promise.all(deletePromises);
                SimpleUI.showMessage(`成功删除 ${this.selectedSamples.length} 个样本`, 'success');
                this.selectedSamples = [];
                await this.loadSamples();
            } catch (error) {
                console.error('批量删除失败:', error);
                SimpleUI.showMessage('批量删除失败: ' + (error.response?.data?.detail || error.message), 'error');
            }
        },
        
        // 检测重复样本
        async showDuplicates() {
            this.duplicateDialog = true;
            this.duplicateLoading = true;
            this.duplicateGroups = [];
            
            try {
                // 注意：这里需要后端实现重复检测端点
                const response = await axios.post('/api/training/promo-detect-duplicates');
                
                this.duplicateGroups = response.data.duplicate_groups || [];
                this.duplicateSamplesCount = this.duplicateGroups.reduce((count, group) => 
                    count + group.samples.length, 0);
                    
            } catch (error) {
                console.error('检测重复失败:', error);
                SimpleUI.showMessage('检测重复失败，暂不支持此功能', 'warning');
            } finally {
                this.duplicateLoading = false;
            }
        },
        
        // 同步向量
        async syncVectors() {
            try {
                SimpleUI.showMessage('开始同步向量...', 'info');
                // 注意：这里需要后端实现向量同步端点
                const response = await axios.post('/api/training/promo-sync-vectors');
                SimpleUI.showMessage(response.data.message || '向量同步完成', 'success');
            } catch (error) {
                console.error('同步向量失败:', error);
                SimpleUI.showMessage('同步向量失败，暂不支持此功能', 'warning');
            }
        },
        
        // 获取分隔符类型标签
        getSeparatorTypeLabel(type) {
            return this.separatorTypeLabels[type] || type;
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
            
            // 截断文本，尽量在空格、标点符号处截断
            let truncated = text.substring(0, length);
            const lastSpace = truncated.lastIndexOf(' ');
            const lastPunctuation = Math.max(
                truncated.lastIndexOf('，'),
                truncated.lastIndexOf('。'),
                truncated.lastIndexOf('！'),
                truncated.lastIndexOf('？'),
                truncated.lastIndexOf('、')
            );
            
            // 如果在前80%位置找到合适的截断点，使用它
            const cutoffPoint = Math.max(lastSpace, lastPunctuation);
            if (cutoffPoint > length * 0.8) {
                return text.substring(0, cutoffPoint);
            }
            
            return truncated;
        },
        
        // 排序功能
        sortBy(field) {
            if (this.sortField === field) {
                this.sortOrder = this.sortOrder === 'asc' ? 'desc' : 'asc';
            } else {
                this.sortField = field;
                this.sortOrder = 'asc';
            }
            
            this.allSamples.sort((a, b) => {
                let valueA = a[field];
                let valueB = b[field];
                
                // 处理日期排序
                if (field === 'created_at') {
                    valueA = new Date(valueA || 0).getTime();
                    valueB = new Date(valueB || 0).getTime();
                }
                
                if (this.sortOrder === 'asc') {
                    return valueA > valueB ? 1 : -1;
                } else {
                    return valueA < valueB ? 1 : -1;
                }
            });
            
            this.updatePageData();
        },
        
        getSortClass(field) {
            if (this.sortField !== field) return '';
            return this.sortOrder === 'asc' ? 'sort-asc' : 'sort-desc';
        },
        
        // 分页功能
        handlePageChange(page) {
            if (page < 1 || page > this.totalPages) return;
            this.currentPage = page;
            this.updatePageData();
        },
        
        jumpToPageHandler() {
            if (this.jumpToPage && this.jumpToPage >= 1 && this.jumpToPage <= this.totalPages) {
                this.handlePageChange(this.jumpToPage);
            }
        },
        
        getPageNumbers() {
            const totalPages = this.totalPages;
            const current = this.currentPage;
            const pages = [];
            
            if (totalPages <= 7) {
                for (let i = 1; i <= totalPages; i++) {
                    pages.push(i);
                }
            } else {
                pages.push(1);
                if (current > 4) pages.push('...');
                
                const start = Math.max(2, current - 2);
                const end = Math.min(totalPages - 1, current + 2);
                
                for (let i = start; i <= end; i++) {
                    pages.push(i);
                }
                
                if (current < totalPages - 3) pages.push('...');
                if (totalPages > 1) pages.push(totalPages);
            }
            
            return pages;
        }
    },
    
    computed: {
        totalPages() {
            return Math.ceil(this.totalCount / this.pageSize);
        },
        
        allSelected() {
            return this.samples.length > 0 && this.selectedSamples.length === this.samples.length;
        }
    },
    
    async mounted() {
        // 并行加载分隔符配置和样本数据
        await Promise.all([
            this.loadSeparatorPatterns(),
            this.loadSamples()
        ]);
    }
});

// 注册组件 - 移除Element Plus，使用轻量级UI
if (window.NavBar) {
    app.component('nav-bar', window.NavBar);
}
if (window.TrainingNav) {
    app.component('training-nav', window.TrainingNav);
}
app.mount('#app');