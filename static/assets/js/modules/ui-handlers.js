// UI事件处理器模块

const UIHandlers = {
    // 显示成功消息
    showSuccess(message) {
        if (window.SimpleUI && window.SimpleUI.showMessage) {
            window.SimpleUI.showMessage(message, 'success');
        } else {
            console.log('✅', message);
        }
    },

    // 显示错误消息
    showError(message) {
        if (window.SimpleUI && window.SimpleUI.showMessage) {
            window.SimpleUI.showMessage(message, 'error');
        } else {
            console.error('❌', message);
        }
    },

    // 显示警告消息
    showWarning(message) {
        if (window.SimpleUI && window.SimpleUI.showMessage) {
            window.SimpleUI.showMessage(message, 'warning');
        } else {
            console.warn('⚠️', message);
        }
    },

    // 显示信息消息
    showInfo(message) {
        if (window.SimpleUI && window.SimpleUI.showMessage) {
            window.SimpleUI.showMessage(message, 'info');
        } else {
            console.info('ℹ️', message);
        }
    },

    // 确认对话框
    async confirm(message, title = '确认操作') {
        if (window.SimpleUI && window.SimpleUI.confirm) {
            try {
                return await window.SimpleUI.confirm(message);
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








    // 获取滚动信息
    getScrollInfo() {
        const windowHeight = window.innerHeight;
        const documentHeight = document.documentElement.scrollHeight;
        const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
        
        return {
            scrollTop,
            documentHeight,
            windowHeight,
            remaining: documentHeight - (scrollTop + windowHeight),
            percentage: documentHeight > windowHeight ? 
                Math.min(100, (scrollTop / (documentHeight - windowHeight)) * 100) : 0
        };
    },

    // 检查是否接近底部
    isNearBottom(threshold = 100) {
        const scrollInfo = this.getScrollInfo();
        return scrollInfo.remaining <= threshold;
    },

    // 从URL提取文件名
    extractFileName(url) {
        if (!url) return '未知文件';
        const parts = url.split('/');
        const fileName = parts[parts.length - 1];
        
        // 移除查询参数
        const cleanName = fileName.split('?')[0];
        
        // 如果文件名过长，简化显示
        if (cleanName.length > 50) {
            const ext = cleanName.split('.').pop();
            const name = cleanName.substring(0, 30);
            return `${name}...${ext ? '.' + ext : ''}`;
        }
        
        return cleanName || '未知文件';
    },

    // 检查文件类型
    getFileType(url) {
        if (!url) return 'unknown';
        
        const ext = url.toLowerCase().split('.').pop();
        
        if (['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext)) {
            return 'image';
        } else if (['mp4', 'webm', 'avi', 'mov'].includes(ext)) {
            return 'video';
        } else if (['mp3', 'wav', 'ogg', 'aac'].includes(ext)) {
            return 'audio';
        } else if (['pdf', 'doc', 'docx', 'txt'].includes(ext)) {
            return 'document';
        }
        
        return 'unknown';
    },

};

// 导出模块
if (typeof module !== 'undefined' && module.exports) {
    module.exports = UIHandlers;
} else {
    window.UIHandlers = UIHandlers;
}