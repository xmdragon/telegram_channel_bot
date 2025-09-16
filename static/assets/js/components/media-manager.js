// 媒体文件管理组件
const { createApp } = Vue;

// 原生消息和对话框工具
const showMessage = (message, type = 'info', duration = 3000) => {
    if (window.SimpleUI && window.SimpleUI.showMessage) {
        window.SimpleUI.showMessage(message, type, duration);
    } else {
        console.log(`[${type.toUpperCase()}] ${message}`);
    }
};

const showConfirm = (message, title = '确认', options = {}) => {
    return new Promise((resolve, reject) => {
        if (window.SimpleUI && window.SimpleUI.showConfirm) {
            window.SimpleUI.showConfirm(title, message, options)
                .then(() => resolve(true))
                .catch(() => reject('cancel'));
        } else {
            const confirmed = confirm(`${title}\n\n${message}`);
            if (confirmed) {
                resolve(true);
            } else {
                reject('cancel');
            }
        }
    });
};

const showAlert = (message, title = '提示', options = {}) => {
    return new Promise((resolve) => {
        if (window.SimpleUI && window.SimpleUI.alert) {
            window.SimpleUI.alert(message, title, options)
                .then(() => resolve());
        } else {
            alert(`${title}\n\n${message}`);
            resolve();
        }
    });
};

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
            currentFile: null,
            
            // 优化进度
            optimizing: false,
            optimizeProgress: {
                visible: false,
                current: 0,
                total: 0,
                percent: 0,
                currentFile: '',
                savedMb: 0,
                errors: []
            }
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
                    files = files.filter(f => f.messageIds && f.messageIds.length > 0);
                    break;
                case 'orphaned':
                    files = files.filter(f => !f.messageIds || f.messageIds.length === 0);
                    break;
            }
            
            return files;
        },
        
        // 分页后的文件列表
        paginatedFiles() {
            const start = (this.currentPage - 1) * this.pageSize;
            const end = start + this.pageSize;
            return this.filteredFiles.slice(start, end);
        },
        
        // 总页数
        totalPages() {
            return Math.ceil(this.filteredFiles.length / this.pageSize);
        }
    },
    
    methods: {
        // 获取媒体文件URL - 直接使用nginx静态文件路径
        getMediaUrl(filePath) {
            // 训练媒体文件直接通过nginx访问，无需FastAPI权限验证
            // Docker配置: ./data/training/ad -> /usr/share/nginx/html/media
            return `/media/${filePath}`;
        },
        
        // 加载媒体文件列表
        async loadMediaFiles() {
            this.loading = true;
            try {
                const response = await axios.get(API.training.mediaFiles);
                this.mediaFiles = response.data.files || [];
                this.stats = response.data.stats || this.stats;
                
                // 按加入训练样本的时间倒序排序（最新的在前）
                this.mediaFiles.sort((a, b) => {
                    // 优先使用 saved_at (加入训练的时间)，然后是 createdAt
                    const timeA = new Date(a.createdAt || 0).getTime();
                    const timeB = new Date(b.createdAt || 0).getTime();
                    return timeB - timeA;
                });
                
                // 不再显示加载成功提示，避免频繁打扰用户
                // showMessage(`加载了 ${this.mediaFiles.length} 个媒体文件`, 'success');
            } catch (error) {
                showMessage('加载媒体文件失败', 'error');
            } finally {
                this.loading = false;
            }
        },
        
        // 查看文件详情
        viewDetails(file) {
            this.currentFile = {
                ...file
            };
            this.detailDialog = true;
        },
        
        // 获取广告分数类型（用于标签颜色）
        getAdScoreType(score) {
            if (score >= 70) return 'danger';
            if (score >= 50) return 'warning';
            if (score >= 30) return 'info';
            return 'success';
        },
        
        // 获取广告分数CSS类
        getAdScoreClass(score) {
            if (score >= 70) return 'tag-high-score';
            if (score >= 50) return 'tag-medium-score';
            return 'tag-low-score';
        },
        
        // 关闭详情对话框
        closeDetailDialog() {
            this.detailDialog = false;
            this.currentFile = null;
        },
        
        // 删除文件
        async deleteFile(file) {
            try {
                await showConfirm(
                    `确定要删除文件 ${file.name} 吗？`,
                    '删除确认',
                    { type: 'warning' }
                );
                
                const response = await axios.delete(API.training.mediaFileById(file.hash));
                
                if (response.data.success) {
                    // 删除成功后不显示提示，直接刷新列表
                    // showMessage('文件已删除', 'success');
                    this.loadMediaFiles();
                } else {
                    showMessage(response.data.error || '删除失败', 'error');
                }
            } catch (error) {
                if (error !== 'cancel') {
                    showMessage('删除文件失败', 'error');
                }
            }
        },
        
        // 处理图片加载错误
        handleImageError(event) {
            // 替换为默认图片占位符
            event.target.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="200" height="200" viewBox="0 0 200 200"%3E%3Crect width="200" height="200" fill="%23f5f5f5"/%3E%3Ctext x="50%25" y="50%25" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-size="20" fill="%23999"%3E加载失败%3C/text%3E%3C/svg%3E';
            event.target.style.cursor = 'default';
            event.target.onclick = null;
        },
        
        // 预览图片
        previewImage(file, event) {
            // 阻止事件冒泡和默认行为
            if (event) {
                event.stopPropagation();
                event.preventDefault();
            }
            
            if (file.type === 'image') {
                const imageUrl = '/media/' + file.path;
                
                // 创建一个临时的预览器实例
                this.$nextTick(() => {
                    // 创建全屏预览容器
                    const previewEl = document.createElement('div');
                    previewEl.style.cssText = `
                        position: fixed;
                        top: 0;
                        left: 0;
                        right: 0;
                        bottom: 0;
                        background: rgba(0, 0, 0, 0.95);
                        z-index: 9999;
                        display: flex;
                        flex-direction: column;
                        align-items: center;
                        justify-content: center;
                        cursor: zoom-out;
                    `;
                    
                    // 创建图片元素
                    const img = document.createElement('img');
                    img.src = imageUrl;
                    img.style.cssText = `
                        max-width: 90%;
                        max-height: 85%;
                        object-fit: contain;
                        box-shadow: 0 0 30px rgba(0,0,0,0.5);
                    `;
                    
                    // 创建文件名显示
                    const nameEl = document.createElement('div');
                    nameEl.textContent = file.name;
                    nameEl.style.cssText = `
                        color: white;
                        margin-top: 20px;
                        font-size: 14px;
                        opacity: 0.8;
                    `;
                    
                    // 创建关闭提示
                    const tipEl = document.createElement('div');
                    tipEl.textContent = '点击任意位置或按ESC关闭';
                    tipEl.style.cssText = `
                        position: absolute;
                        top: 20px;
                        right: 20px;
                        color: white;
                        font-size: 12px;
                        opacity: 0.6;
                    `;
                    
                    previewEl.appendChild(img);
                    previewEl.appendChild(nameEl);
                    previewEl.appendChild(tipEl);
                    
                    // 关闭预览的函数
                    const closePreview = () => {
                        if (document.body.contains(previewEl)) {
                            // 淡出动画
                            previewEl.style.opacity = '0';
                            setTimeout(() => {
                                if (document.body.contains(previewEl)) {
                                    document.body.removeChild(previewEl);
                                }
                            }, 300);
                            // 移除事件监听器
                            document.removeEventListener('keydown', handleEsc);
                        }
                    };
                    
                    // 点击关闭
                    previewEl.addEventListener('click', (e) => {
                        if (e.target === previewEl || e.target === img) {
                            closePreview();
                        }
                    });
                    
                    // ESC键关闭
                    const handleEsc = (e) => {
                        if (e.key === 'Escape') {
                            closePreview();
                        }
                    };
                    document.addEventListener('keydown', handleEsc);
                    
                    // 添加淡入动画
                    previewEl.style.opacity = '0';
                    document.body.appendChild(previewEl);
                    setTimeout(() => {
                        previewEl.style.transition = 'opacity 0.3s';
                        previewEl.style.opacity = '1';
                    }, 10);
                });
            }
        },
        
        // 清理未引用的文件
        async cleanOrphaned() {
            try {
                const orphanedCount = this.mediaFiles.filter(f => f.messageIds.length === 0).length;
                
                if (orphanedCount === 0) {
                    showMessage('没有未引用的文件', 'info');
                    return;
                }
                
                await showConfirm(
                    `发现 ${orphanedCount} 个未引用的文件，是否清理？`,
                    '清理确认',
                    { type: 'warning' }
                );
                
                const response = await axios.post(API.training.mediaFilesCleanOrphaned);
                
                if (response.data.success) {
                    showMessage(`清理了 ${response.data.deleted} 个文件`, 'success');
                    this.loadMediaFiles();
                } else {
                    showMessage(response.data.error || '清理失败', 'error');
                }
            } catch (error) {
                if (error !== 'cancel') {
                    showMessage('清理失败', 'error');
                }
            }
        },
        
        // 优化视频（转换为快照）
        async optimizeVideos() {
            try {
                const videoCount = this.mediaFiles.filter(f => f.type === 'video').length;
                
                if (videoCount === 0) {
                    showMessage('没有视频文件需要优化', 'info');
                    return;
                }
                
                await showConfirm(
                    `发现 ${videoCount} 个视频文件，转换为快照可节省约95%空间，是否继续？`,
                    '优化确认',
                    { type: 'warning' }
                );
                
                // 显示进度对话框
                this.optimizing = true;
                this.optimizeProgress = {
                    visible: true,
                    current: 0,
                    total: videoCount,
                    percent: 0,
                    currentFile: '正在优化...',
                    savedMb: 0,
                    errors: []
                };
                
                // 调用优化存储API
                const response = await axios.post(API.training.optimizeStorage);
                
                if (response.data.success) {
                    this.optimizeProgress.current = this.optimizeProgress.total;
                    this.optimizeProgress.percent = 100;
                    this.optimizeProgress.currentFile = '优化完成';
                    this.optimizeProgress.savedMb = (response.data.saved_space || 0) / (1024 * 1024);
                    
                    // 重新加载文件列表
                    this.loadMediaFiles();
                    
                    showMessage(`优化完成：处理了 ${response.data.processed_videos || 0} 个视频，清理了 ${response.data.cleaned_files || 0} 个文件，节省空间 ${this.optimizeProgress.savedMb.toFixed(2)} MB`, 'success', 5000);
                } else {
                    throw new Error(response.data.error || '优化失败');
                }
                
            } catch (error) {
                if (error !== 'cancel') {
                    showMessage(error.message || '优化失败', 'error');
                }
            } finally {
                this.optimizing = false;
                this.optimizeProgress.visible = false;
            }
        },
        
        // 导出所有媒体
        async downloadAll() {
            try {
                showMessage('正在准备导出，请稍候...', 'info');
                
                const response = await axios.get(API.training.mediaFilesExport, {
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
                
                showMessage('导出成功', 'success');
            } catch (error) {
                showMessage('导出失败', 'error');
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
        const isAuthorized = await authManager.initPageAuth();
        if (!isAuthorized) {
            return;
        }
        
        // 加载数据
        this.loadMediaFiles();
    }
});


// 确保组件加载navbar
if (window.NavBar) {
    app.component('nav-bar', window.NavBar);
}

// 注册training-nav组件
if (window.TrainingNav) {
    app.component('training-nav', window.TrainingNav);
}

app.mount('#app');