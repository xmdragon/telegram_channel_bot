// UI事件处理器模块

const UIHandlers = {
    // 显示成功消息
    showSuccess(message) {
        if (window.ElMessage) {
            window.ElMessage.success(message);
        } else {
            console.log('✅', message);
        }
    },

    // 显示错误消息
    showError(message) {
        if (window.ElMessage) {
            window.ElMessage.error(message);
        } else {
            console.error('❌', message);
        }
    },

    // 显示警告消息
    showWarning(message) {
        if (window.ElMessage) {
            window.ElMessage.warning(message);
        } else {
            console.warn('⚠️', message);
        }
    },

    // 显示信息消息
    showInfo(message) {
        if (window.ElMessage) {
            window.ElMessage.info(message);
        } else {
            console.info('ℹ️', message);
        }
    },

    // 确认对话框
    async confirm(message, title = '确认操作') {
        if (window.ElMessageBox) {
            try {
                await window.ElMessageBox.confirm(message, title, {
                    confirmButtonText: '确定',
                    cancelButtonText: '取消',
                    type: 'warning'
                });
                return true;
            } catch {
                return false;
            }
        } else {
            return window.confirm(`${title}\n\n${message}`);
        }
    },

    // 打开媒体预览
    openMediaPreview(url) {
        if (!url) return;
        
        // 创建预览模态框
        const modal = document.createElement('div');
        modal.className = 'media-preview-modal';
        modal.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.8);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 9999;
            cursor: pointer;
        `;

        // 判断媒体类型
        const isVideo = url.includes('.mp4') || url.includes('.webm') || url.includes('video');
        
        let mediaElement;
        if (isVideo) {
            mediaElement = document.createElement('video');
            mediaElement.controls = true;
            mediaElement.style.maxWidth = '90%';
            mediaElement.style.maxHeight = '90%';
        } else {
            mediaElement = document.createElement('img');
            mediaElement.style.maxWidth = '90%';
            mediaElement.style.maxHeight = '90%';
            mediaElement.style.objectFit = 'contain';
        }

        mediaElement.src = url;
        modal.appendChild(mediaElement);

        // 点击关闭
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                document.body.removeChild(modal);
            }
        });

        // ESC键关闭
        const handleKeydown = (e) => {
            if (e.key === 'Escape') {
                document.body.removeChild(modal);
                document.removeEventListener('keydown', handleKeydown);
            }
        };
        document.addEventListener('keydown', handleKeydown);

        document.body.appendChild(modal);
    },

    // 复制到剪贴板
    async copyToClipboard(text) {
        try {
            if (navigator.clipboard) {
                await navigator.clipboard.writeText(text);
                this.showSuccess('已复制到剪贴板');
            } else {
                // 降级方案
                const textArea = document.createElement('textarea');
                textArea.value = text;
                document.body.appendChild(textArea);
                textArea.select();
                document.execCommand('copy');
                document.body.removeChild(textArea);
                this.showSuccess('已复制到剪贴板');
            }
        } catch (error) {
            console.error('复制失败:', error);
            this.showError('复制失败');
        }
    },

    // 下载文件
    downloadFile(url, filename) {
        try {
            const link = document.createElement('a');
            link.href = url;
            link.download = filename || 'download';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        } catch (error) {
            console.error('下载失败:', error);
            this.showError('下载失败');
        }
    },

    // 滚动到顶部
    scrollToTop(smooth = true) {
        window.scrollTo({
            top: 0,
            behavior: smooth ? 'smooth' : 'auto'
        });
    },

    // 滚动到底部
    scrollToBottom(smooth = true) {
        window.scrollTo({
            top: document.body.scrollHeight,
            behavior: smooth ? 'smooth' : 'auto'
        });
    },

    // 检查元素是否在视口中
    isElementInViewport(element) {
        const rect = element.getBoundingClientRect();
        return (
            rect.top >= 0 &&
            rect.left >= 0 &&
            rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
            rect.right <= (window.innerWidth || document.documentElement.clientWidth)
        );
    },

    // 平滑滚动到元素
    scrollToElement(element, offset = 0) {
        if (!element) return;
        
        const elementPosition = element.getBoundingClientRect().top;
        const offsetPosition = elementPosition + window.pageYOffset - offset;

        window.scrollTo({
            top: offsetPosition,
            behavior: 'smooth'
        });
    },

    // 设置页面标题
    setPageTitle(title) {
        document.title = title;
    },

    // 更新浏览器历史
    updateUrl(path, title = null) {
        if (title) {
            this.setPageTitle(title);
        }
        window.history.pushState(null, title, path);
    },

    // 防抖处理的搜索输入
    createDebouncedSearch(callback, delay = 300) {
        let timeoutId;
        return function(searchTerm) {
            clearTimeout(timeoutId);
            timeoutId = setTimeout(() => {
                callback(searchTerm);
            }, delay);
        };
    },

    // 处理表单验证错误
    handleValidationErrors(errors) {
        if (Array.isArray(errors)) {
            errors.forEach(error => this.showError(error));
        } else if (typeof errors === 'object') {
            Object.values(errors).forEach(error => {
                if (Array.isArray(error)) {
                    error.forEach(msg => this.showError(msg));
                } else {
                    this.showError(error);
                }
            });
        } else {
            this.showError(errors || '表单验证失败');
        }
    },

    // 格式化数字显示
    formatNumber(number) {
        if (number >= 1000000) {
            return (number / 1000000).toFixed(1) + 'M';
        } else if (number >= 1000) {
            return (number / 1000).toFixed(1) + 'K';
        }
        return number.toString();
    },

    // 创建加载指示器
    createLoadingIndicator(container, text = '加载中...') {
        const loading = document.createElement('div');
        loading.className = 'loading-indicator';
        loading.innerHTML = `
            <div class="spinner"></div>
            <span>${text}</span>
        `;
        loading.style.cssText = `
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
            color: #666;
        `;
        
        if (container) {
            container.appendChild(loading);
        }
        
        return loading;
    },

    // 移除加载指示器
    removeLoadingIndicator(container) {
        if (!container) return;
        const loading = container.querySelector('.loading-indicator');
        if (loading) {
            container.removeChild(loading);
        }
    }
};

// 导出模块
if (typeof module !== 'undefined' && module.exports) {
    module.exports = UIHandlers;
} else {
    window.UIHandlers = UIHandlers;
}