// 广告检测数据管理组件

// 确保API配置可用
const API = window.API;

const { createApp } = Vue;

const app = createApp({
    data() {
        return {
            // 统计数据
            stats: {
                totalSamples: 0,
                uniqueSamples: 0,
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
            
            // 选择和排序
            selectedSampleIds: [],
            allSelected: false,
            sortField: '',
            sortOrder: 'desc',
            
            // 对话框
            detailDialog: false,
            currentSample: null,
            duplicateDialog: false,
            duplicateLoading: false,
            duplicateGroups: [],
            duplicateSamplesCount: 0,
            
        }
    },
    
    computed: {
        // 是否为管理员
        isAdmin() {
            const adminInfo = localStorage.getItem('admin_info');
            if (adminInfo) {
                const admin = JSON.parse(adminInfo);
                return admin.is_super_admin || (admin.permissions && admin.permissions.includes('training.manage'));
            }
            return false;
        },
        
        // 计算总页数
        totalPages() {
            return Math.ceil(this.totalCount / this.pageSize);
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
                
                const response = await axios.get(API.training.adSamples, { params });
                this.samples = response.data.samples || [];
                this.totalCount = response.data.total || this.samples.length;
                
                // 按创建时间倒序排序（最新的在前）
                this.samples.sort((a, b) => {
                    const timeA = new Date(a.created_at || a.timestamp || 0).getTime();
                    const timeB = new Date(b.created_at || b.timestamp || 0).getTime();
                    return timeB - timeA;
                });
                
                // 加载统计信息
                await this.loadStatistics();
            } catch (error) {
                console.error('加载样本数据失败:', error);
                window.SimpleUI.Message.error('加载样本数据失败');
            } finally {
                this.loading = false;
            }
        },
        
        // 加载统计信息
        async loadStatistics() {
            try {
                const response = await axios.get(API.training.adStatistics);
                if (response.data.success && response.data.statistics) {
                    const stats = response.data.statistics;
                    this.stats = {
                        totalSamples: stats.total_samples || 0,
                        uniqueSamples: stats.total_samples || 0,  // 使用总样本数作为去重后数量
                        storageSize: stats.storage_size || 0
                    };
                }
            } catch (error) {
                console.error('加载统计信息失败:', error);
            }
        },
        
        // 处理选择变化
        handleSelectionChange(selection) {
            this.selectedSamples = selection;
        },
        
        // 全选处理
        selectAll(event) {
            if (event.target.checked) {
                this.selectedSampleIds = this.samples.map(s => s.id);
                this.selectedSamples = [...this.samples];
            } else {
                this.selectedSampleIds = [];
                this.selectedSamples = [];
            }
        },
        
        // 单个选择处理
        handleSampleSelection(event) {
            const sampleId = event.target.value.id;
            if (event.target.checked) {
                if (!this.selectedSampleIds.includes(sampleId)) {
                    this.selectedSampleIds.push(sampleId);
                    this.selectedSamples.push(event.target.value);
                }
            } else {
                this.selectedSampleIds = this.selectedSampleIds.filter(id => id !== sampleId);
                this.selectedSamples = this.selectedSamples.filter(s => s.id !== sampleId);
            }
            
            // 更新全选状态
            this.allSelected = this.selectedSampleIds.length === this.samples.length && this.samples.length > 0;
        },
        
        // 排序处理
        sortBy(field) {
            if (this.sortField === field) {
                this.sortOrder = this.sortOrder === 'asc' ? 'desc' : 'asc';
            } else {
                this.sortField = field;
                this.sortOrder = 'desc';
            }
            
            this.samples.sort((a, b) => {
                let valueA = a[field];
                let valueB = b[field];
                
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
        },
        
        // 清除搜索
        clearSearch() {
            this.searchText = '';
            this.loadSamples();
        },
        
        // 处理分页
        handlePageChange(page) {
            this.currentPage = page;
            this.loadSamples();
        },
        
        // 显示详情
        showDetail(sample) {
            this.currentSample = sample;
            this.detailDialog = true;
        },
        
        // 删除单个样本
        async deleteSample(sample) {
            try {
                // 现在所有样本都有统一的样本ID
                const sampleId = sample.id;
                if (!sampleId) {
                    window.SimpleUI.Message.info('样本ID缺失，无法删除');
                    return;
                }
                
                await window.SimpleUI.MessageBox.confirm(
                    '确定要删除这个广告训练样本吗？',
                    '确认删除',
                    {
                        confirmButtonText: '确定',
                        cancelButtonText: '取消',
                        type: 'warning',
                    }
                );
                
                const response = await axios.delete(API.training.adSampleById(sampleId));
                
                if (response.data.success) {
                    window.SimpleUI.Message.success('删除成功');
                } else {
                    window.SimpleUI.Message.info(response.data.message || '删除可能失败');
                }
                await this.loadSamples();
            } catch (error) {
                if (error !== 'cancel') {
                    console.error('删除失败:', error);
                    window.SimpleUI.Message.info('删除失败: ' + (error.response?.data?.message || error.message));
                }
            }
        },
        
        // 批量删除
        async deleteSelected() {
            if (!this.selectedSamples.length) return;
            
            try {
                await window.SimpleUI.MessageBox.confirm(
                    `确定要删除选中的 ${this.selectedSamples.length} 个样本吗？`,
                    '批量删除确认',
                    {
                        confirmButtonText: '确定删除',
                        cancelButtonText: '取消',
                        type: 'warning',
                    }
                );
                
                const ids = this.selectedSamples.map(s => s.id).filter(id => id);
                if (ids.length === 0) {
                    window.SimpleUI.Message.info('所选样本ID缺失，无法删除');
                    return;
                }
                await axios.delete(API.training.adSamplesBatch, { data: { ids } });
                
                window.SimpleUI.Message.success('批量删除成功');
                await this.loadSamples();
            } catch (error) {
                if (error !== 'cancel') {
                    window.SimpleUI.Message.info('批量删除失败');
                }
            }
        },
        
        // 显示重复检测
        async showDuplicates() {
            this.duplicateDialog = true;
            this.duplicateLoading = true;
            
            try {
                const response = await axios.post(API.training.adSamplesDetectDuplicates);
                
                // 检查API响应是否成功
                if (response.data.success) {
                    this.duplicateGroups = response.data.groups || [];
                    this.duplicateSamplesCount = response.data.total_duplicates || 0;
                    
                    // 初始化每个样本的keep属性 - 默认保留第一个  
                    this.duplicateGroups.forEach((group, groupIdx) => {
                        console.log(`处理第 ${groupIdx + 1} 组，共 ${group.samples.length} 个样本`);
                        group.samples.forEach((sample, idx) => {
                            sample.keep = (idx === 0); // Vue 3 自动响应式
                            console.log(`初始化样本 ID ${sample.id}: keep=${sample.keep} (索引: ${idx})`);
                        });
                    });
                    
                    if (!this.duplicateGroups.length) {
                        window.SimpleUI.Message.info('没有发现重复的样本');
                        this.duplicateDialog = false;
                    }
                } else {
                    window.SimpleUI.Message.info('检测重复失败: ' + (response.data.error || '未知错误'));
                    this.duplicateDialog = false;
                }
            } catch (error) {
                console.error('检测重复失败:', error);
                window.SimpleUI.Message.info('检测重复失败: ' + (error.response?.data?.message || error.message));
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
                console.log(`合并操作 - 样本 ID ${sample.id}: keep=${sample.keep}`);
            });
        },
        
        // 调试方法：检查样本状态变化
        onKeepChange(sample) {
            console.log(`样本 ID ${sample.id} 状态变化: keep=${sample.keep}`);
        },
        
        // 应用去重
        async applyDeduplicate() {
            try {
                // 调试信息：打印所有样本的keep状态
                console.log('=== 去重调试信息 ===');
                this.duplicateGroups.forEach((group, groupIdx) => {
                    console.log(`组 ${groupIdx + 1}:`);
                    group.samples.forEach((sample, sampleIdx) => {
                        console.log(`  样本 ${sampleIdx + 1} (ID: ${sample.id}): keep=${sample.keep}`);
                    });
                });
                
                // 收集要删除的样本ID
                const toDelete = [];
                this.duplicateGroups.forEach(group => {
                    group.samples.forEach(sample => {
                        console.log(`检查样本 ID ${sample.id}: keep=${sample.keep}`);
                        if (!sample.keep) {
                            const sampleId = sample.id;
                            if (sampleId) {
                                toDelete.push(sampleId);
                                console.log(`添加到删除列表: ${sampleId}`);
                            }
                        }
                    });
                });
                
                console.log('要删除的样本ID列表:', toDelete);
                
                if (!toDelete.length) {
                    window.SimpleUI.Message.info('没有选择要删除的样本');
                    return;
                }
                
                await window.SimpleUI.MessageBox.confirm(
                    `将删除 ${toDelete.length} 个重复样本，是否继续？`,
                    '去重确认',
                    {
                        confirmButtonText: '确定',
                        cancelButtonText: '取消',
                        type: 'warning',
                    }
                );
                
                const response = await axios.post(API.training.adSamplesDeduplicate, {
                    remove_ids: toDelete
                });
                
                window.SimpleUI.Message.info(response.data.message);
                this.duplicateDialog = false;
                await this.loadSamples();
            } catch (error) {
                if (error !== 'cancel') {
                    window.SimpleUI.Message.info('去重失败');
                }
            }
        },
        
        // 优化存储
        async optimizeStorage() {
            try {
                await window.SimpleUI.MessageBox.confirm(
                    '优化存储将：\n1. 转换视频为快照\n2. 压缩图片\n3. 清理无效文件\n\n是否继续？',
                    '优化存储',
                    {
                        confirmButtonText: '开始优化',
                        cancelButtonText: '取消',
                        type: 'info',
                        dangerouslyUseHTMLString: true
                    }
                );
                
                window.SimpleUI.Message.info('正在优化存储，请稍候...');
                const response = await axios.post(API.training.optimizeStorage);
                
                window.SimpleUI.Message.info(`优化完成！节省空间: ${this.formatSize(response.data.saved_space)}`);
                await this.loadStatistics();
            } catch (error) {
                if (error !== 'cancel') {
                    window.SimpleUI.Message.info('优化存储失败');
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
            return sourceMap[source] || source || '未知';
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
                window.SimpleUI.Message.info('您没有权限访问此页面');
                setTimeout(() => {
                    window.location.href = '/';
                }, 1500);
                return false;
            }
            return true;
        },
        
        // 关闭详情对话框
        closeDetailDialog() {
            this.detailDialog = false;
            this.currentSample = null;
        },
        
        // 关闭重复检测对话框
        closeDuplicateDialog() {
            this.duplicateDialog = false;
            this.duplicateGroups = [];
            this.duplicateSamplesCount = 0;
        },
        
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
        
        // 加载统计信息（只加载一次）
        this.loadStatistics();
    },
    
    beforeUnmount() {
        // 组件销毁时清理资源
    }
});

if (window.NavBar) {
    app.component('nav-bar', window.NavBar);
}
if (window.TrainingNav) {
    app.component('training-nav', window.TrainingNav);
}
if (window.PaginationComponent) {
    app.component('pagination-component', window.PaginationComponent);
}
app.mount('#app');