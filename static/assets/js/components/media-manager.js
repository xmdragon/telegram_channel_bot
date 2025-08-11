// 媒体文件管理组件
const { createApp } = Vue;
const { ElMessage, ElMessageBox } = ElementPlus;

const app = createApp({
    data() {
        return {
            // 统计数据
            stats: {
                totalFiles: 0,
                imageCount: 0,
                videoCount: 0,
                totalSize: 0,
                referencedCount: 0,
                orphanedCount: 0
            },
            
            // 媒体文件列表
            mediaFiles: [],
            loading: false,
            
            // 搜索和筛选
            searchKeyword: '',
            filterType: 'all',
            
            // 分页
            currentPage: 1,
            pageSize: 20,
            
            // 详情对话框
            detailDialog: false,
            currentFile: null
        }
    },
    
    computed: {
        // 过滤后的文件列表
        filteredFiles() {
            let files = this.mediaFiles;
            
            // 按关键词搜索
            if (this.searchKeyword) {
                const keyword = this.searchKeyword.toLowerCase();
                files = files.filter(f => f.name.toLowerCase().includes(keyword));
            }
            
            // 按类型筛选
            switch (this.filterType) {
                case 'image':
                    files = files.filter(f => f.type === 'image');
                    break;
                case 'video':
                    files = files.filter(f => f.type === 'video');
                    break;
                case 'referenced':
                    files = files.filter(f => f.messageIds.length > 0);
                    break;
                case 'orphaned':
                    files = files.filter(f => f.messageIds.length === 0);
                    break;
            }
            
            return files;
        },
        
        // 分页后的文件列表
        paginatedFiles() {
            const start = (this.currentPage - 1) * this.pageSize;
            const end = start + this.pageSize;
            return this.filteredFiles.slice(start, end);
        }
    },
    
    methods: {
        // 加载媒体文件列表
        async loadMediaFiles() {
            this.loading = true;
            try {
                const response = await axios.get('/api/training/media-files');
                this.mediaFiles = response.data.files || [];
                this.stats = response.data.stats || this.stats;
                
                ElMessage.success(`加载了 ${this.mediaFiles.length} 个媒体文件`);
            } catch (error) {
                console.error('加载媒体文件失败:', error);
                ElMessage.error('加载媒体文件失败');
            } finally {
                this.loading = false;
            }
        },
        
        // 查看文件详情
        viewDetails(file) {
            this.currentFile = file;
            this.detailDialog = true;
        },
        
        // 删除文件
        async deleteFile(file) {
            try {
                await ElMessageBox.confirm(
                    `确定要删除文件 ${file.name} 吗？`,
                    '删除确认',
                    {
                        confirmButtonText: '确定',
                        cancelButtonText: '取消',
                        type: 'warning',
                    }
                );
                
                const response = await axios.delete(`/api/training/media-files/${file.hash}`);
                
                if (response.data.success) {
                    ElMessage.success('文件已删除');
                    this.loadMediaFiles();
                } else {
                    ElMessage.error(response.data.error || '删除失败');
                }
            } catch (error) {
                if (error !== 'cancel') {
                    console.error('删除文件失败:', error);
                    ElMessage.error('删除文件失败');
                }
            }
        },
        
        // 清理未引用的文件
        async cleanOrphaned() {
            try {
                const orphanedCount = this.mediaFiles.filter(f => f.messageIds.length === 0).length;
                
                if (orphanedCount === 0) {
                    ElMessage.info('没有未引用的文件');
                    return;
                }
                
                await ElMessageBox.confirm(
                    `发现 ${orphanedCount} 个未引用的文件，是否清理？`,
                    '清理确认',
                    {
                        confirmButtonText: '确定',
                        cancelButtonText: '取消',
                        type: 'warning',
                    }
                );
                
                const response = await axios.post('/api/training/media-files/clean-orphaned');
                
                if (response.data.success) {
                    ElMessage.success(`清理了 ${response.data.deleted} 个文件`);
                    this.loadMediaFiles();
                } else {
                    ElMessage.error(response.data.error || '清理失败');
                }
            } catch (error) {
                if (error !== 'cancel') {
                    console.error('清理未引用文件失败:', error);
                    ElMessage.error('清理失败');
                }
            }
        },
        
        // 优化视频（转换为快照）
        async optimizeVideos() {
            try {
                const videoCount = this.mediaFiles.filter(f => f.type === 'video').length;
                
                if (videoCount === 0) {
                    ElMessage.info('没有视频文件需要优化');
                    return;
                }
                
                await ElMessageBox.confirm(
                    `发现 ${videoCount} 个视频文件，转换为快照可节省约95%空间，是否继续？`,
                    '优化确认',
                    {
                        confirmButtonText: '确定',
                        cancelButtonText: '取消',
                        type: 'warning',
                    }
                );
                
                ElMessage.info('正在优化视频文件，请稍候...');
                
                const response = await axios.post('/api/training/optimize-storage');
                
                if (response.data.success) {
                    ElMessage.success(`优化完成！节省了 ${this.formatSize(response.data.saved_space)}`);
                    this.loadMediaFiles();
                } else {
                    ElMessage.error(response.data.error || '优化失败');
                }
            } catch (error) {
                if (error !== 'cancel') {
                    console.error('优化视频失败:', error);
                    ElMessage.error('优化失败');
                }
            }
        },
        
        // 导出所有媒体
        async downloadAll() {
            try {
                ElMessage.info('正在准备导出，请稍候...');
                
                const response = await axios.get('/api/training/media-files/export', {
                    responseType: 'blob'
                });
                
                // 创建下载链接
                const url = window.URL.createObjectURL(new Blob([response.data]));
                const link = document.createElement('a');
                link.href = url;
                link.setAttribute('download', `media_files_${new Date().toISOString().split('T')[0]}.zip`);
                document.body.appendChild(link);
                link.click();
                link.remove();
                
                ElMessage.success('导出成功');
            } catch (error) {
                console.error('导出媒体文件失败:', error);
                ElMessage.error('导出失败');
            }
        },
        
        // 格式化文件大小
        formatSize(bytes) {
            if (bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }
    },
    
    async mounted() {
        // 初始化权限检查
        const isAuthorized = await authManager.initPageAuth('training.manage');
        if (!isAuthorized) {
            return;
        }
        
        // 加载数据
        this.loadMediaFiles();
    }
});

app.use(ElementPlus);

// 确保组件加载navbar
if (window.NavBar) {
    app.component('nav-bar', window.NavBar);
}

app.mount('#app');