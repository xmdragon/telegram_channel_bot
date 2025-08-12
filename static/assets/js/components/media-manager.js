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
                
                // 不再显示加载成功提示，避免频繁打扰用户
                // ElMessage.success(`加载了 ${this.mediaFiles.length} 个媒体文件`);
            } catch (error) {
                // console.error('加载媒体文件失败:', error);
                ElMessage({
                    message: '加载媒体文件失败',
                    type: 'error',
                    offset: 20,
                    customClass: 'bottom-right-message'
                });
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
                    // 删除成功后不显示提示，直接刷新列表
                    // ElMessage.success('文件已删除');
                    this.loadMediaFiles();
                } else {
                    ElMessage({
                        message: response.data.error || '删除失败',
                        type: 'error',
                        offset: 20,
                        customClass: 'bottom-right-message'
                    });
                }
            } catch (error) {
                if (error !== 'cancel') {
                    // console.error('删除文件失败:', error);
                    ElMessage({
                        message: '删除文件失败',
                        type: 'error',
                        offset: 20,
                        customClass: 'bottom-right-message'
                    });
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
                const imageUrl = '/media/ad_training_data/' + file.path;
                
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
                    ElMessage({
                        message: '没有未引用的文件',
                        type: 'info',
                        offset: 20,
                        customClass: 'bottom-right-message'
                    });
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
                    ElMessage({
                        message: `清理了 ${response.data.deleted} 个文件`,
                        type: 'success',
                        offset: 20,
                        customClass: 'bottom-right-message'
                    });
                    this.loadMediaFiles();
                } else {
                    ElMessage({
                        message: response.data.error || '清理失败',
                        type: 'error',
                        offset: 20,
                        customClass: 'bottom-right-message'
                    });
                }
            } catch (error) {
                if (error !== 'cancel') {
                    // console.error('清理未引用文件失败:', error);
                    ElMessage({
                        message: '清理失败',
                        type: 'error',
                        offset: 20,
                        customClass: 'bottom-right-message'
                    });
                }
            }
        },
        
        // 优化视频（转换为快照）
        async optimizeVideos() {
            try {
                const videoCount = this.mediaFiles.filter(f => f.type === 'video').length;
                
                if (videoCount === 0) {
                    ElMessage({
                        message: '没有视频文件需要优化',
                        type: 'info',
                        offset: 20,
                        customClass: 'bottom-right-message'
                    });
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
                
                // 显示进度对话框
                this.optimizing = true;
                this.optimizeProgress = {
                    visible: true,
                    current: 0,
                    total: videoCount,
                    percent: 0,
                    currentFile: '正在初始化...',
                    savedMb: 0,
                    errors: []
                };
                
                // 使用fetch接收SSE进度（需要认证）
                const response = await fetch('/api/training/optimize-storage-sse', {
                    method: 'GET',
                    credentials: 'include',
                    headers: {
                        'Accept': 'text/event-stream',
                        ...authManager.getAuthHeaders()  // 添加Bearer Token
                    }
                });
                
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';
                
                const processSSEMessage = (message) => {
                    if (message.startsWith('data: ')) {
                        const dataStr = message.substring(6);
                        try {
                            const data = JSON.parse(dataStr);
                            
                            switch(data.type) {
                                case 'init':
                                    this.optimizeProgress.currentFile = data.message;
                                    break;
                                    
                                case 'stats':
                                    this.optimizeProgress.total = data.total;
                                    ElMessage({
                                        message: `开始处理 ${data.total} 个视频文件（${data.total_size_mb} MB）`,
                                        type: 'info',
                                        offset: 20,
                                        customClass: 'bottom-right-message'
                                    });
                                    break;
                                    
                                case 'progress':
                                    this.optimizeProgress.current = data.current;
                                    this.optimizeProgress.percent = data.percent;
                                    this.optimizeProgress.currentFile = `正在处理: ${data.file}`;
                                    break;
                                    
                                case 'file_done':
                                    this.optimizeProgress.savedMb += data.saved_kb / 1024;
                                    break;
                                    
                                case 'file_error':
                                    this.optimizeProgress.errors.push(`${data.file}: ${data.error}`);
                                    break;
                                    
                                case 'complete':
                                    this.optimizing = false;
                                    this.optimizeProgress.visible = false;
                                    
                                    if (data.processed > 0) {
                                        ElMessage.success({
                                            message: `优化完成！处理了 ${data.processed}/${data.total} 个视频，节省了 ${data.saved_mb} MB 空间`,
                                            duration: 5000
                                        });
                                    }
                                    
                                    if (data.errors > 0) {
                                        ElMessage({
                                            message: `有 ${data.errors} 个文件处理失败`,
                                            type: 'warning',
                                            offset: 20,
                                            customClass: 'bottom-right-message'
                                        });
                                    }
                                    
                                    // 重新加载文件列表
                                    this.loadMediaFiles();
                                    return true; // 标记完成
                                    
                                case 'error':
                                    this.optimizing = false;
                                    this.optimizeProgress.visible = false;
                                    ElMessage({
                                        message: data.message || '优化失败',
                                        type: 'error',
                                        offset: 20,
                                        customClass: 'bottom-right-message'
                                    });
                                    return true; // 标记完成
                            }
                        } catch (e) {
                            // console.error('解析SSE消息失败:', e, dataStr);
                        }
                    }
                    return false; // 未完成
                };
                
                // 读取流
                let isCompleted = false;
                try {
                    while (true) {
                        const { done, value } = await reader.read();
                        
                        if (done) {
                            // console.log('SSE流正常结束');
                            break;
                        }
                        
                        buffer += decoder.decode(value, { stream: true });
                        const lines = buffer.split('\n');
                        
                        // 保留最后一行（可能不完整）
                        buffer = lines.pop() || '';
                        
                        // 处理完整的行
                        for (const line of lines) {
                            if (line.trim()) {
                                const shouldStop = processSSEMessage(line);
                                if (shouldStop) {
                                    // console.log('收到完成信号，停止读取');
                                    isCompleted = true;
                                    try {
                                        await reader.cancel();
                                    } catch (e) {
                                        // 忽略取消错误
                                    }
                                    return;
                                }
                            }
                        }
                    }
                    
                    // 如果没有收到complete消息就结束了，可能是异常中断
                    if (!isCompleted) {
                        // console.warn('SSE流意外结束，未收到complete消息');
                        this.optimizing = false;
                        this.optimizeProgress.visible = false;
                        // 重新加载文件列表以查看实际处理结果
                        this.loadMediaFiles();
                        ElMessage({
                            message: '处理可能已完成，请检查结果',
                            type: 'warning',
                            offset: 20,
                            customClass: 'bottom-right-message'
                        });
                    }
                } catch (error) {
                    // 如果是取消操作，不报错
                    if (error.name === 'AbortError' || isCompleted) {
                        // console.log('SSE流正常取消');
                        return;
                    }
                    
                    // console.error('读取SSE流错误:', error);
                    this.optimizing = false;
                    this.optimizeProgress.visible = false;
                    
                    // 重新加载文件列表以查看实际处理结果
                    this.loadMediaFiles();
                    ElMessage({
                        message: '连接中断，请检查处理结果',
                        type: 'warning',
                        offset: 20,
                        customClass: 'bottom-right-message'
                    });
                }
                
            } catch (error) {
                if (error !== 'cancel') {
                    // console.error('优化视频失败:', error);
                    ElMessage({
                        message: '优化失败',
                        type: 'error',
                        offset: 20,
                        customClass: 'bottom-right-message'
                    });
                    this.optimizing = false;
                    this.optimizeProgress.visible = false;
                }
            }
        },
        
        // 导出所有媒体
        async downloadAll() {
            try {
                ElMessage({
                    message: '正在准备导出，请稍候...',
                    type: 'info',
                    offset: 20,
                    customClass: 'bottom-right-message'
                });
                
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
                
                ElMessage({
                    message: '导出成功',
                    type: 'success',
                    offset: 20,
                    customClass: 'bottom-right-message'
                });
            } catch (error) {
                // console.error('导出媒体文件失败:', error);
                ElMessage({
                    message: '导出失败',
                    type: 'error',
                    offset: 20,
                    customClass: 'bottom-right-message'
                });
            }
        },
        
        // 检测重复文件
        async checkDuplicates() {
            try {
                this.loading = true;
                const response = await axios.get('/api/training/media-files/duplicates');
                
                if (response.data.success) {
                    const stats = response.data.stats;
                    const duplicates = response.data.duplicates;
                    
                    if (stats.groups === 0) {
                        ElMessage({
                            message: '没有发现重复的媒体文件',
                            type: 'info',
                            offset: 20,
                            customClass: 'bottom-right-message'
                        });
                    } else {
                        // 显示重复检测结果
                        await ElMessageBox.alert(
                            `<div>
                                <p>发现 <strong>${stats.groups}</strong> 组重复文件</p>
                                <p>总计 <strong>${stats.total_duplicates}</strong> 个重复文件</p>
                                <p>可节省空间: <strong>${this.formatSize(stats.total_saved_space)}</strong></p>
                                <br>
                                <p>使用"执行去重"按钮可以自动清理重复文件</p>
                            </div>`,
                            '重复检测结果',
                            {
                                dangerouslyUseHTMLString: true,
                                confirmButtonText: '确定',
                                type: 'info'
                            }
                        );
                    }
                } else {
                    throw new Error(response.data.error || '检测失败');
                }
            } catch (error) {
                // console.error('检测重复失败:', error);
                ElMessage({
                    message: error.message || '检测重复失败',
                    type: 'error',
                    offset: 20,
                    customClass: 'bottom-right-message'
                });
            } finally {
                this.loading = false;
            }
        },
        
        // 执行去重
        async deduplicateMedia() {
            try {
                // 先检测重复
                const checkResponse = await axios.get('/api/training/media-files/duplicates');
                if (!checkResponse.data.success || checkResponse.data.stats.groups === 0) {
                    ElMessage({
                        message: '没有需要去重的文件',
                        type: 'info',
                        offset: 20,
                        customClass: 'bottom-right-message'
                    });
                    return;
                }
                
                const stats = checkResponse.data.stats;
                
                // 确认操作
                await ElMessageBox.confirm(
                    `<div>
                        <p>将要去重 <strong>${stats.groups}</strong> 组文件</p>
                        <p>删除 <strong>${stats.total_duplicates}</strong> 个重复文件</p>
                        <p>释放空间: <strong>${this.formatSize(stats.total_saved_space)}</strong></p>
                        <br>
                        <p style="color: #e6a23c;">⚠️ 此操作不可撤销，但会自动备份元数据</p>
                    </div>`,
                    '确认去重',
                    {
                        dangerouslyUseHTMLString: true,
                        confirmButtonText: '确定去重',
                        cancelButtonText: '取消',
                        type: 'warning'
                    }
                );
                
                this.loading = true;
                const response = await axios.post('/api/training/media-files/deduplicate');
                
                if (response.data.success) {
                    ElMessage({
                        message: `去重完成：删除 ${response.data.deleted} 个文件，合并 ${response.data.merged} 个引用`,
                        type: 'success',
                        offset: 20,
                        customClass: 'bottom-right-message',
                        duration: 5000
                    });
                    
                    // 重新加载文件列表
                    this.loadMediaFiles();
                } else {
                    throw new Error(response.data.error || '去重失败');
                }
            } catch (error) {
                if (error !== 'cancel') {
                    // console.error('去重失败:', error);
                    ElMessage({
                        message: error.message || '去重失败',
                        type: 'error',
                        offset: 20,
                        customClass: 'bottom-right-message'
                    });
                }
            } finally {
                this.loading = false;
            }
        },
        
        // 重建视觉哈希
        async rebuildVisualHashes() {
            try {
                await ElMessageBox.confirm(
                    '将为所有媒体文件重建视觉哈希，这可能需要一些时间。是否继续？',
                    '重建视觉哈希',
                    {
                        confirmButtonText: '开始重建',
                        cancelButtonText: '取消',
                        type: 'info'
                    }
                );
                
                this.loading = true;
                const response = await axios.post('/api/training/media-files/rebuild-visual-hashes');
                
                if (response.data.success) {
                    ElMessage({
                        message: `重建完成：处理 ${response.data.processed} 个文件，跳过 ${response.data.skipped} 个，错误 ${response.data.errors || 0} 个`,
                        type: 'success',
                        offset: 20,
                        customClass: 'bottom-right-message',
                        duration: 5000
                    });
                } else {
                    throw new Error(response.data.error || '重建失败');
                }
            } catch (error) {
                if (error !== 'cancel') {
                    // console.error('重建视觉哈希失败:', error);
                    ElMessage({
                        message: error.message || '重建视觉哈希失败',
                        type: 'error',
                        offset: 20,
                        customClass: 'bottom-right-message'
                    });
                }
            } finally {
                this.loading = false;
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

// 注册training-nav组件
if (window.TrainingNav) {
    app.component('training-nav', window.TrainingNav);
}

app.mount('#app');