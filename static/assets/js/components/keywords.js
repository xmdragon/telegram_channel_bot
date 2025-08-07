const { createApp } = Vue;
const { ElMessage, ElMessageBox } = ElementPlus;

// 使用全局MessageManager

const keywordsApp = {
    data() {
        return {
            // 数据状态
            keywords: [],
            filteredKeywords: [],
            selectedKeywords: [],
            loading: false,
            saving: false,
            batchImporting: false,
            
            // 分页
            currentPage: 1,
            pageSize: 50,
            totalKeywords: 0,
            
            // 筛选
            searchKeyword: '',
            filterType: '',
            filterStatus: '',
            
            // 对话框
            dialogVisible: false,
            dialogMode: 'add', // add 或 edit
            batchImportVisible: false,
            
            // 页面状态
            activeTab: 'list',
            
            // 表单数据
            keywordForm: {
                id: null,
                keyword: '',
                keyword_type: 'text',
                description: '',
                is_active: true
            },
            
            batchForm: {
                keyword_type: 'text',
                keywords: ''
            },
            
            // 表单验证规则
            keywordRules: {
                keyword: [
                    { required: true, message: '请输入关键词', trigger: 'blur' },
                    { min: 1, max: 100, message: '关键词长度在1-100个字符', trigger: 'blur' }
                ],
                keyword_type: [
                    { required: true, message: '请选择关键词类型', trigger: 'change' }
                ]
            }
        }
    },
    
    computed: {
        // 当前页显示的关键词
        paginatedKeywords() {
            const start = (this.currentPage - 1) * this.pageSize;
            const end = start + this.pageSize;
            return this.filteredKeywords.slice(start, end);
        },
        
        // 统计信息
        stats() {
            const total = this.keywords.length;
            const textKeywords = this.keywords.filter(k => k.keyword_type === 'text').length;
            const lineKeywords = this.keywords.filter(k => k.keyword_type === 'line').length;
            const activeKeywords = this.keywords.filter(k => k.is_active).length;
            
            return {
                total,
                textKeywords,
                lineKeywords,
                activeKeywords
            };
        }
    },
    
    mounted() {
        this.loadKeywords();
    },
    
    methods: {
        // 加载关键词列表
        async loadKeywords() {
            this.loading = true;
            try {
                const response = await axios.get('/api/keywords/');
                this.keywords = response.data || [];
                this.filterKeywords();
//                 console.log('加载关键词:', this.keywords.length, '个');
            } catch (error) {
                console.error('加载关键词失败:', error);
                ElMessage.error('加载关键词列表失败');
            } finally {
                this.loading = false;
            }
        },
        
        // 筛选关键词
        filterKeywords() {
            let filtered = [...this.keywords];
            
            // 关键词搜索
            if (this.searchKeyword) {
                const search = this.searchKeyword.toLowerCase();
                filtered = filtered.filter(keyword => 
                    keyword.keyword.toLowerCase().includes(search) ||
                    (keyword.description && keyword.description.toLowerCase().includes(search))
                );
            }
            
            // 类型筛选
            if (this.filterType) {
                filtered = filtered.filter(keyword => keyword.keyword_type === this.filterType);
            }
            
            // 状态筛选
            if (this.filterStatus !== '') {
                const isActive = this.filterStatus === 'true';
                filtered = filtered.filter(keyword => keyword.is_active === isActive);
            }
            
            this.filteredKeywords = filtered;
            this.totalKeywords = filtered.length;
            this.currentPage = 1; // 重置到第一页
        },
        
        // 显示添加对话框
        showAddDialog() {
            this.dialogMode = 'add';
            this.resetForm();
            this.dialogVisible = true;
        },
        
        // 显示批量导入对话框
        showBatchImportDialog() {
            this.batchImportVisible = true;
            this.resetBatchForm();
        },
        
        // 编辑关键词
        editKeyword(keyword) {
            this.dialogMode = 'edit';
            this.keywordForm = {
                id: keyword.id,
                keyword: keyword.keyword,
                keyword_type: keyword.keyword_type,
                description: keyword.description || '',
                is_active: keyword.is_active
            };
            this.dialogVisible = true;
        },
        
        // 保存关键词
        async saveKeyword() {
            try {
                await this.$refs.keywordFormRef.validate();
            } catch (error) {
                return;
            }
            
            this.saving = true;
            try {
                if (this.dialogMode === 'add') {
                    await axios.post('/api/keywords/', {
                        keyword: this.keywordForm.keyword,
                        keyword_type: this.keywordForm.keyword_type,
                        description: this.keywordForm.description || null
                    });
                    MessageManager.show('success', '关键词添加成功');
                } else {
                    await axios.put(`/api/keywords/${this.keywordForm.id}`, {
                        keyword: this.keywordForm.keyword,
                        keyword_type: this.keywordForm.keyword_type,
                        description: this.keywordForm.description || null
                    });
                    MessageManager.show('success', '关键词更新成功');
                }
                
                this.dialogVisible = false;
                this.loadKeywords();
            } catch (error) {
                console.error('保存关键词失败:', error);
                const message = error.response?.data?.detail || '保存关键词失败';
                ElMessage.error(message);
            } finally {
                this.saving = false;
            }
        },
        
        // 删除关键词
        async deleteKeyword(keyword) {
            try {
                await ElMessageBox.confirm(
                    `确定要删除关键词 "${keyword.keyword}" 吗？`,
                    '确认删除',
                    {
                        confirmButtonText: '确定',
                        cancelButtonText: '取消',
                        type: 'warning'
                    }
                );
                
                await axios.delete(`/api/keywords/${keyword.id}`);
                MessageManager.show('success', '关键词删除成功');
                this.loadKeywords();
            } catch (error) {
                if (error !== 'cancel') {
                    console.error('删除关键词失败:', error);
                    ElMessage.error('删除关键词失败');
                }
            }
        },
        
        // 批量删除
        async batchDelete() {
            if (this.selectedKeywords.length === 0) {
                ElMessage.warning('请选择要删除的关键词');
                return;
            }
            
            try {
                await ElMessageBox.confirm(
                    `确定要删除选中的 ${this.selectedKeywords.length} 个关键词吗？`,
                    '确认批量删除',
                    {
                        confirmButtonText: '确定',
                        cancelButtonText: '取消',
                        type: 'warning'
                    }
                );
                
                const keywordIds = this.selectedKeywords.map(k => k.id);
                await axios.delete('/api/keywords/batch', {
                    data: keywordIds
                });
                
                MessageManager.show('success', `成功删除 ${this.selectedKeywords.length} 个关键词`);
                this.selectedKeywords = [];
                this.loadKeywords();
            } catch (error) {
                if (error !== 'cancel') {
                    console.error('批量删除失败:', error);
                    ElMessage.error('批量删除失败');
                }
            }
        },
        
        // 批量导入
        async batchImport() {
            if (!this.batchForm.keywords.trim()) {
                ElMessage.warning('请输入要导入的关键词');
                return;
            }
            
            this.batchImporting = true;
            try {
                // 解析关键词列表
                const keywordLines = this.batchForm.keywords
                    .split('\n')
                    .map(line => line.trim())
                    .filter(line => line.length > 0);
                
                if (keywordLines.length === 0) {
                    ElMessage.warning('没有有效的关键词');
                    return;
                }
                
                // 构建批量创建请求
                const keywordsData = keywordLines.map(keyword => ({
                    keyword: keyword,
                    keyword_type: this.batchForm.keyword_type,
                    description: `批量导入的${this.batchForm.keyword_type === 'text' ? '文中' : '行过滤'}关键词`
                }));
                
                const response = await axios.post('/api/keywords/batch', keywordsData);
                MessageManager.show('success', response.data.message);
                
                this.batchImportVisible = false;
                this.loadKeywords();
            } catch (error) {
                console.error('批量导入失败:', error);
                const message = error.response?.data?.detail || '批量导入失败';
                ElMessage.error(message);
            } finally {
                this.batchImporting = false;
            }
        },
        
        // 切换关键词状态
        async toggleKeywordStatus(keyword) {
            try {
                await axios.put(`/api/keywords/${keyword.id}`, {
                    is_active: keyword.is_active
                });
                
                const status = keyword.is_active ? '启用' : '禁用';
                MessageManager.show('success', `关键词已${status}`);
            } catch (error) {
                console.error('更新关键词状态失败:', error);
                // 恢复原状态
                keyword.is_active = !keyword.is_active;
                ElMessage.error('更新关键词状态失败');
            }
        },
        
        // 表格选择变化
        handleSelectionChange(selection) {
            this.selectedKeywords = selection;
        },
        
        // 分页处理
        handleSizeChange(newSize) {
            this.pageSize = newSize;
            this.currentPage = 1;
        },
        
        handleCurrentChange(newPage) {
            this.currentPage = newPage;
        },
        
        // 重置表单
        resetForm() {
            this.keywordForm = {
                id: null,
                keyword: '',
                keyword_type: 'text',
                description: '',
                is_active: true
            };
            
            if (this.$refs.keywordFormRef) {
                this.$refs.keywordFormRef.resetFields();
            }
        },
        
        // 重置批量导入表单
        resetBatchForm() {
            this.batchForm = {
                keyword_type: 'text',
                keywords: ''
            };
        },
        
        // 返回首页
        goHome() {
            window.location.href = '/';
        }
    }
};

// 创建应用并注册组件
const app = createApp(keywordsApp);
app.use(ElementPlus);
// 注册导航栏组件
if (window.NavBar) {
    app.component('nav-bar', window.NavBar);
}
app.mount('#app');