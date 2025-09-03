// 尾部过滤数据管理组件
const { createApp } = Vue;

const app = createApp({
    data() {
        return {
            // 表格数据
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
            
            
            // 排序相关
            sortField: 'created_at',
            sortOrder: 'desc'
        }
    },
    
    methods: {
        // 加载样本数据 - 带超时处理的优化版本
        async loadSamples() {
            this.loading = true;
            try {
                // 构建分页参数
                const params = {
                    page: this.currentPage,
                    size: this.pageSize,
                    search: this.searchText
                };
                
                // 使用带超时的Promise.all并行加载
                const [samplesResponse, statsResponse] = await (window.PromiseAllWithTimeout ? 
                    window.PromiseAllWithTimeout([
                        axios.get(API.training.tailFilterSamples, { params }),
                        axios.get(API.training.tailFilterStatistics)
                    ], 12000) : // 12秒超时
                    Promise.all([
                        axios.get(API.training.tailFilterSamples, { params }),
                        axios.get(API.training.tailFilterStatistics)
                    ])
                );
                
                // 直接使用API返回的分页数据
                this.samples = samplesResponse.data.samples || [];
                this.totalCount = samplesResponse.data.total || 0;
                
                // 按创建时间倒序排序（最新的在前）
                this.samples.sort((a, b) => {
                    const timeA = new Date(a.created_at || 0).getTime();
                    const timeB = new Date(b.created_at || 0).getTime();
                    return timeB - timeA;
                });
                
                // 使用统一的统计API数据（Linus式单一数据源）
                if (statsResponse.data.success) {
                    this.totalSamples = statsResponse.data.total_samples || this.totalCount;
                    this.validSamples = statsResponse.data.valid_samples || this.totalCount;
                    this.todayAdded = statsResponse.data.today_added || 0;
                } else {
                    // 降级到使用当前数据计算（保持向后兼容）
                    this.totalSamples = this.totalCount;
                    this.validSamples = this.totalCount;
                    this.todayAdded = 0;
                }
                
                // 清除页面加载超时检测
                if (typeof window.AxiosConfig !== 'undefined' && window.AxiosConfig.clearPageLoadTimeout) {
                    window.AxiosConfig.clearPageLoadTimeout();
                }
                
            } catch (error) {
                console.error('加载尾部过滤样本失败:', error);
                
                // 判断错误类型并给出不同提示
                let errorMessage = '加载数据失败';
                if (error.message === '并行请求超时') {
                    errorMessage = '数据加载超时，请检查网络连接';
                } else if (error.code === 'ECONNABORTED') {
                    errorMessage = '网络请求超时，请重试';
                }
                
                SimpleUI.showMessage(errorMessage, 'error');
                
                // 提供重试按钮
                this.addRetryButton();
            } finally {
                this.loading = false;
            }
        },
        
        // 添加重试按钮
        addRetryButton() {
            const existingButton = document.getElementById('data-retry-button');
            if (existingButton) return;
            
            const button = document.createElement('button');
            button.id = 'data-retry-button';
            button.innerHTML = '🔄 重新加载数据';
            button.className = 'btn btn-primary';
            button.style.cssText = `
                position: fixed;
                bottom: 20px;
                left: 50%;
                transform: translateX(-50%);
                z-index: 10002;
                padding: 10px 20px;
                background: #409eff;
                color: white;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-size: 14px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            `;
            
            button.addEventListener('click', async () => {
                button.textContent = '加载中...';
                button.disabled = true;
                
                try {
                    await this.loadSamples();
                    button.remove();
                } catch (e) {
                    button.textContent = '🔄 重新加载数据';
                    button.disabled = false;
                }
            });
            
            document.body.appendChild(button);
            
            // 5秒后自动移除按钮
            setTimeout(() => {
                if (button.parentNode) {
                    button.remove();
                }
            }, 30000);
        },
        
        
        
        // 处理样本选择变化
        handleSampleSelection(event) {
            const sample = event.target.value;
            const isChecked = event.target.checked;
            
            if (isChecked && !this.selectedSamples.includes(sample)) {
                this.selectedSamples.push(sample);
            } else if (!isChecked) {
                const index = this.selectedSamples.indexOf(sample);
                if (index > -1) {
                    this.selectedSamples.splice(index, 1);
                }
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
        
        // 处理搜索
        handleSearch() {
            // 重置到第一页
            this.currentPage = 1;
            // 重新加载数据
            this.loadSamples();
        },
        
        
        // 删除单个样本
        async deleteSample(sample) {
            let confirmed = false;
            try {
                confirmed = await SimpleUI.showConfirm(
                    '确定要删除这个尾部过滤样本吗？',
                    '确认删除'
                );
            } catch (error) {
                if (error === 'cancel') {
                    return;
                }
                // 降级到原生确认框
                confirmed = confirm('确定要删除这个尾部过滤样本吗？');
            }
            
            if (!confirmed) return;
            
            try {
                const response = await axios.delete(API.training.tailFilterSampleById(sample.id));
                
                if (response.data.success) {
                    SimpleUI.showMessage('删除成功', 'success');
                    await this.loadSamples();
                } else {
                    SimpleUI.showMessage('删除失败', 'error');
                }
            } catch (error) {
                console.error('删除失败:', error);
                SimpleUI.showMessage('删除失败', 'error');
            }
        },
        
        // 编辑样本
        editSample(sample) {
            this.editingSample = {
                id: sample.id,
                tail_part: sample.tail_part
            };
            this.editDialog = true;
        },
        
        // 保存编辑
        async saveEdit() {
            if (!this.editingSample || !this.editingSample.tail_part.trim()) {
                SimpleUI.showMessage('请输入尾部内容', 'warning');
                return;
            }
            
            this.submitting = true;
            try {
                const response = await axios.put(API.training.tailFilterSampleById(this.editingSample.id), {
                    tail_part: this.editingSample.tail_part.trim()
                });
                
                if (response.data.success) {
                    SimpleUI.showMessage('保存成功', 'success');
                    this.editDialog = false;
                    this.editingSample = null;
                    await this.loadSamples();
                } else {
                    SimpleUI.showMessage(response.data.message || '保存失败', 'error');
                }
            } catch (error) {
                console.error('保存编辑失败:', error);
                SimpleUI.showMessage('保存失败', 'error');
            } finally {
                this.submitting = false;
            }
        },
        
        // 批量删除
        async deleteSelected() {
            if (!this.selectedSamples.length) return;
            
            let confirmed = false;
            try {
                confirmed = await SimpleUI.showConfirm(
                    `确定要删除选中的 ${this.selectedSamples.length} 个样本吗？`,
                    '批量删除确认'
                );
            } catch (error) {
                if (error === 'cancel') return;
                confirmed = confirm(`确定要删除选中的 ${this.selectedSamples.length} 个样本吗？`);
            }
            
            if (!confirmed) return;
            
            try {
                const ids = this.selectedSamples.map(s => s.id);
                
                // 逐个删除（因为API可能不支持批量删除）
                let successCount = 0;
                for (const id of ids) {
                    try {
                        await axios.delete(API.training.tailFilterSampleById(id));
                        successCount++;
                    } catch (e) {
                        // 静默处理删除失败
                    }
                }
                
                SimpleUI.showMessage(`成功删除 ${successCount} 个样本`, 'success');
                await this.loadSamples();
                
            } catch (error) {
                console.error('批量删除失败:', error);
                SimpleUI.showMessage('批量删除失败', 'error');
            }
        },
        
        
        // 同步向量索引
        async syncVectors() {
            let confirmed = false;
            try {
                confirmed = await SimpleUI.showConfirm(
                    '同步向量将重建尾部样本的AI向量索引，确保AI过滤功能使用最新的训练数据。\n此操作需要几秒钟时间，确认执行吗？',
                    '同步向量索引'
                );
            } catch (error) {
                if (error === 'cancel') return;
                confirmed = confirm('同步向量将重建尾部样本的AI向量索引，确保AI过滤功能使用最新的训练数据。\n此操作需要几秒钟时间，确认执行吗？');
            }
            
            if (!confirmed) return;
            
            try {
                // 使用现有的loading状态变量（Linus式统一模式）
                this.loading = true;
                
                const response = await axios.post(API.training.tailFilterRebuildVectors);
                
                if (response.data.success) {
                    SimpleUI.showMessage(`向量同步成功！处理了 ${response.data.vectorized_samples} 个样本`, 'success');
                } else {
                    SimpleUI.showMessage('向量同步失败: ' + (response.data.message || '未知错误'), 'error');
                }
                
            } catch (error) {
                console.error('同步向量失败:', error);
                SimpleUI.showMessage('同步向量失败: ' + (error.response?.data?.message || error.message), 'error');
            } finally {
                // 确保无论成功还是失败都重置loading状态
                this.loading = false;
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
        },
        
        // 排序功能
        sortBy(field) {
            if (this.sortField === field) {
                this.sortOrder = this.sortOrder === 'asc' ? 'desc' : 'asc';
            } else {
                this.sortField = field;
                this.sortOrder = 'asc';
            }
            
            // 现在使用服务端分页，直接对当前页数据排序
            this.samples.sort((a, b) => {
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
        },
        
        // 获取排序样式
        getSortClass(field) {
            if (this.sortField !== field) return '';
            return this.sortOrder === 'asc' ? 'sort-asc' : 'sort-desc';
        },
        
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
        // 初始化权限检查
        const isAuthorized = await authManager.initPageAuth('training.view');
        if (!isAuthorized) {
            return;
        }
        
        // 初始加载数据
        await this.loadSamples();
    }
});

// 移除Element Plus，使用轻量级UI
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