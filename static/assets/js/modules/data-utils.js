// 数据处理工具模块

const DataUtils = {
    // 格式化时间
    formatTime(timeStr) {
        if (!timeStr) return '';
        try {
            // 修复时区bug：明确处理UTC时间
            const utcTimeStr = timeStr.endsWith('Z') ? timeStr : timeStr + 'Z';
            const date = new Date(utcTimeStr);
            const now = new Date();
            const diffInSeconds = Math.floor((now - date) / 1000);
            
            if (diffInSeconds < 60) return `${diffInSeconds}秒前`;
            if (diffInSeconds < 3600) return `${Math.floor(diffInSeconds / 60)}分钟前`;
            if (diffInSeconds < 86400) return `${Math.floor(diffInSeconds / 3600)}小时前`;
            if (diffInSeconds < 604800) return `${Math.floor(diffInSeconds / 86400)}天前`;
            
            return date.toLocaleDateString('zh-CN', {
                month: 'numeric',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
        } catch (e) {
            return '时间格式错误';
        }
    },

    // 获取状态标签
    getStatusTag(status) {
        const statusMap = {
            'pending': { text: '待审核', type: 'warning' },
            'approved': { text: '已发布', type: 'success' },
            'rejected': { text: '已拒绝', type: 'danger' },
            'auto_forwarded': { text: '自动转发', type: 'info' }
        };
        return statusMap[status] || { text: status, type: 'default' };
    },

    // 获取频道显示名称
    getChannelDisplayName(channelData) {
        if (!channelData) return '未知频道';
        
        // 如果是字符串，尝试解析
        if (typeof channelData === 'string') {
            // 处理类似 "#-100266881691➡️ :-100266881691919" 的格式
            if (channelData.includes('➡️')) {
                const parts = channelData.split('➡️');
                if (parts.length > 1) {
                    const channelId = parts[0].replace('#', '').trim();
                    // 返回清理后的ID，或者查找真实名称
                    return this.formatChannelId(channelId);
                }
            }
            
            // 处理纯ID格式
            if (channelData.startsWith('-100')) {
                return this.formatChannelId(channelData);
            }
            
            return channelData;
        }
        
        // 如果是对象，按优先级返回
        return channelData.title || channelData.username || this.formatChannelId(channelData.id) || '未知频道';
    },
    
    // 格式化频道ID为友好显示
    formatChannelId(channelId) {
        if (!channelId) return '未知频道';
        
        // 移除-100前缀，显示简化的ID
        if (channelId.toString().startsWith('-100')) {
            const shortId = channelId.toString().replace('-100', '');
            return `频道${shortId.slice(0, 8)}...`;
        }
        
        return `频道${channelId}`;
    },

    // 获取媒体类型图标
    getMediaTypeIcon(mediaType) {
        const iconMap = {
            'photo': '📷',
            'video': '🎬',
            'document': '📄',
            'audio': '🎵',
            'sticker': '🎭',
            'animation': '🎬',
            'voice': '🗣️',
            'video_note': '🎬'
        };
        return iconMap[mediaType] || '📎';
    },

    // 处理图片加载错误
    handleImageError(message, event) {
        if (message) {
            message._mediaLoadFailed = true;
        }
        if (event && event.target) {
            event.target.style.display = 'none';
        }
    },

    // 处理媒体组图片错误
    handleGroupMediaError(media, event) {
        if (media) {
            media._loadFailed = true;
        }
        if (event && event.target) {
            event.target.style.display = 'none';
        }
    },

    // 检查媒体文件是否存在
    mediaExists(message) {
        if (!message) return false;
        
        if (message.is_combined && message.media_group_display) {
            return message.media_group_display.some(media => 
                media.display_url && media.display_url.trim() !== '' && !media._loadFailed
            );
        }
        
        return message.media_display_url && 
               message.media_display_url.trim() !== '' && 
               !message._mediaLoadFailed;
    },

    // 格式化文件大小
    formatFileSize(bytes) {
        if (!bytes || bytes === 0) return '0 B';
        
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(1024));
        const size = (bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 1);
        
        return `${size} ${sizes[i]}`;
    },

    // 截断文本
    truncateText(text, maxLength = 100) {
        if (!text || typeof text !== 'string') return '';
        if (text.length <= maxLength) return text;
        return text.substring(0, maxLength) + '...';
    },

    // 深度克隆对象
    deepClone(obj) {
        if (obj === null || typeof obj !== 'object') return obj;
        if (obj instanceof Date) return new Date(obj.getTime());
        if (obj instanceof Array) return obj.map(item => this.deepClone(item));
        if (typeof obj === 'object') {
            const clonedObj = {};
            for (const key in obj) {
                if (obj.hasOwnProperty(key)) {
                    clonedObj[key] = this.deepClone(obj[key]);
                }
            }
            return clonedObj;
        }
    },

    // 防抖函数
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    },

    // 节流函数
    throttle(func, limit) {
        let inThrottle;
        return function(...args) {
            if (!inThrottle) {
                func.apply(this, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    }
};

// 导出模块
if (typeof module !== 'undefined' && module.exports) {
    module.exports = DataUtils;
} else {
    window.DataUtils = DataUtils;
}