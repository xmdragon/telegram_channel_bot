// 广告向量管理组件

// 确保API配置可用
const API = window.API;

const { createApp } = Vue;

const app = createApp({
    data() {
        return {
            // 统计数据
            stats: {
                totalVectors: 0,
                lastUpdate: ''
            },
            
            // 表格数据
            vectors: [],
            selectedVectors: [],
            currentPage: 1,
            pageSize: 20,
            totalCount: 0,
            loading: false,
            
            // 搜索和筛选
            searchText: '',
            
            // 选择和排序
            selectedVectorIds: [],
            allSelected: false,
            sortField: '',
            sortOrder: 'desc',
            
            // 对话框
            detailDialog: false,
            currentVector: null,
            duplicateDialog: false,
            duplicateLoading: false,
            duplicateGroups: [],
            duplicateVectorsCount: 0,
            
            // 测试功能
            testDialog: false,
            testContent: '',
            testResult: null,
            testLoading: false,
            
            // 添加向量
            addDialog: false,
            addContent: '',
            addSource: 'manual',
            addLoading: false
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
        // 加载向量数据
        async loadVectors() {
            this.loading = true;
            try {
                const params = {
                    page: this.currentPage,
                    page_size: this.pageSize,
                    search: this.searchText
                };
                
                const response = await axios.get(API.training.adVectors, { params });
                this.vectors = response.data.vectors || [];
                this.totalCount = response.data.total || this.vectors.length;
                
                // 按创建时间倒序排序（最新的在前）
                this.vectors.sort((a, b) => {
                    const timeA = new Date(a.created_at || 0).getTime();
                    const timeB = new Date(b.created_at || 0).getTime();
                    return timeB - timeA;
                });
                
                // 加载统计信息
                await this.loadStatistics();
            } catch (error) {
                console.error('加载向量数据失败:', error);
                window.SimpleUI.Message.error('加载向量数据失败');
            } finally {
                this.loading = false;
            }
        },
        
        // 加载统计信息
        async loadStatistics() {
            try {
                const response = await axios.get(API.training.adVectorStatistics);
                if (response.data.success) {
                    const stats = response.data.statistics;
                    this.stats = {
                        totalVectors: stats.total_vectors || 0,
                        lastUpdate: stats.last_updated || ''
                    };
                }
            } catch (error) {
                console.error('加载统计信息失败:', error);
            }
        },
        
        // 搜索向量
        async searchVectors() {
            this.currentPage = 1;
            await this.loadVectors();
        },
        
        // 选择向量
        handleSelectionChange(selection) {
            this.selectedVectors = selection;
            this.selectedVectorIds = selection.map(v => v.id);
            this.allSelected = selection.length === this.vectors.length && this.vectors.length > 0;
        },
        
        // 全选/取消全选
        toggleAllSelection() {
            this.allSelected = !this.allSelected;
            if (this.allSelected) {
                this.selectedVectors = [...this.vectors];
                this.selectedVectorIds = this.vectors.map(v => v.id);
            } else {
                this.selectedVectors = [];
                this.selectedVectorIds = [];
            }
        },
        
        // 排序
        handleSort(field) {
            if (this.sortField === field) {
                this.sortOrder = this.sortOrder === 'asc' ? 'desc' : 'asc';
            } else {
                this.sortField = field;
                this.sortOrder = 'desc';
            }
            
            this.vectors.sort((a, b) => {
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
            this.loadVectors();
        },
        
        // 处理分页
        handlePageChange(page) {
            this.currentPage = page;
            this.loadVectors();
        },
        
        // 显示详情
        showDetail(vector) {
            this.currentVector = vector;
            this.detailDialog = true;
        },
        
        // 删除单个向量
        async deleteVector(vector) {
            try {
                const vectorId = vector.id;
                if (!vectorId) {
                    window.SimpleUI.Message.info('向量ID缺失，无法删除');
                    return;
                }
                
                await window.SimpleUI.MessageBox.confirm(
                    '确定要删除这个广告向量吗？',
                    '确认删除',
                    {
                        confirmButtonText: '确定',
                        cancelButtonText: '取消',
                        type: 'warning',
                    }
                );
                
                const response = await axios.delete(API.training.adVectorById(vectorId));
                
                if (response.data.success) {
                    window.SimpleUI.Message.success('删除成功');
                } else {
                    window.SimpleUI.Message.info(response.data.message || '删除可能失败');
                }
                await this.loadVectors();
            } catch (error) {
                if (error !== 'cancel') {
                    console.error('删除失败:', error);
                    window.SimpleUI.Message.info('删除失败: ' + (error.response?.data?.message || error.message));
                }
            }
        },
        
        // 批量删除
        async deleteSelected() {
            if (!this.selectedVectors.length) return;
            
            try {
                await window.SimpleUI.MessageBox.confirm(
                    `确定要删除选中的 ${this.selectedVectors.length} 个向量吗？`,
                    '批量删除确认',
                    {
                        confirmButtonText: '确定删除',
                        cancelButtonText: '取消',
                        type: 'warning',
                    }
                );
                
                const ids = this.selectedVectors.map(v => v.id).filter(id => id);
                if (ids.length === 0) {
                    window.SimpleUI.Message.info('所选向量ID缺失，无法删除');
                    return;
                }
                await axios.delete(API.training.adVectorsBatch, { data: { vector_ids: ids } });
                
                window.SimpleUI.Message.success('批量删除成功');
                this.selectedVectors = [];
                this.selectedVectorIds = [];
                this.allSelected = false;
                await this.loadVectors();
            } catch (error) {
                if (error !== 'cancel') {
                    console.error('批量删除失败:', error);
                    window.SimpleUI.Message.error('批量删除失败: ' + (error.response?.data?.message || error.message));
                }
            }
        },
        
        // 检测重复向量
        async detectDuplicates() {
            this.duplicateLoading = true;
            try {
                const response = await axios.post(API.training.adVectorsDetectDuplicates);
                
                if (response.data.success) {
                    this.duplicateGroups = response.data.groups || [];
                    this.duplicateVectorsCount = response.data.total_duplicates || 0;
                    
                    if (this.duplicateGroups.length === 0) {
                        window.SimpleUI.Message.info('未发现重复向量');
                    } else {
                        this.duplicateDialog = true;
                    }
                } else {
                    window.SimpleUI.Message.error('检测重复向量失败: ' + response.data.message);
                }
            } catch (error) {
                console.error('检测重复向量失败:', error);
                window.SimpleUI.Message.error('检测重复向量失败');
            } finally {
                this.duplicateLoading = false;
            }
        },
        
        // 去重向量
        async deduplicateVectors(removeIds) {
            try {
                const response = await axios.post(API.training.adVectorsDeduplicate, { remove_ids: removeIds });
                
                if (response.data.success) {
                    window.SimpleUI.Message.success(response.data.message);
                    this.duplicateDialog = false;
                    await this.loadVectors();
                } else {
                    window.SimpleUI.Message.error('去重失败: ' + response.data.message);
                }
            } catch (error) {
                console.error('去重失败:', error);
                window.SimpleUI.Message.error('去重失败');
            }
        },
        
        // 测试广告检测
        async testDetection() {
            if (!this.testContent.trim()) {
                window.SimpleUI.Message.warning('请输入测试内容');
                return;
            }
            
            this.testLoading = true;
            try {
                const response = await axios.post(API.training.adVectorTestDetection, {
                    content: this.testContent
                });
                
                if (response.data.success) {
                    this.testResult = response.data;
                } else {
                    window.SimpleUI.Message.error('测试失败: ' + response.data.message);
                    this.testResult = null;
                }
            } catch (error) {
                console.error('测试检测失败:', error);
                window.SimpleUI.Message.error('测试检测失败');
                this.testResult = null;
            } finally {
                this.testLoading = false;
            }
        },
        
        // 添加向量
        async addVector() {
            if (!this.addContent.trim()) {
                window.SimpleUI.Message.warning('请输入向量内容');
                return;
            }
            
            this.addLoading = true;
            try {
                const response = await axios.post(API.training.adVectorAddFromText, {
                    content: this.addContent,
                    source: this.addSource
                });
                
                if (response.data.success) {
                    window.SimpleUI.Message.success('向量添加成功');
                    this.addDialog = false;
                    this.addContent = '';
                    await this.loadVectors();
                } else {
                    window.SimpleUI.Message.info(response.data.message);
                }
            } catch (error) {
                console.error('添加向量失败:', error);
                window.SimpleUI.Message.error('添加向量失败');
            } finally {
                this.addLoading = false;
            }
        },
        
        // 格式化大小
        formatSize(size) {
            if (size === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(size) / Math.log(k));
            return parseFloat((size / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        },
        
        // 格式化时间
        formatTime(time) {
            if (!time) return '-';
            return new Date(time).toLocaleString('zh-CN');
        },
        
        // 获取来源类型样式
        getSourceTypeClass(source) {
            const typeMap = {
                'manual': 'success',
                'auto': 'info',
                'import': 'primary',
                'user_feedback': 'warning'
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
        
        // 关闭对话框
        closeDetailDialog() {
            this.detailDialog = false;
            this.currentVector = null;
        },
        
        closeDuplicateDialog() {
            this.duplicateDialog = false;
            this.duplicateGroups = [];
            this.duplicateVectorsCount = 0;
        },
        
        closeTestDialog() {
            this.testDialog = false;
            this.testContent = '';
            this.testResult = null;
        },
        
        closeAddDialog() {
            this.addDialog = false;
            this.addContent = '';
            this.addSource = 'manual';
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
        this.loadVectors();
        
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