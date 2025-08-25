// 数据处理工具模块

const DataUtils = {
    // 格式化时间
    formatTime(timeStr) {
        if (!timeStr) return '';
        try {
            // 🕐 修复时区bug：明确处理UTC时间
            // 后端存储的是UTC时间但没有时区标识，需要手动添加'Z'
            const utcTimeStr = timeStr.endsWith('Z') ? timeStr : timeStr + 'Z';
            const date = new Date(utcTimeStr);
            const now = new Date();
            const diffInSeconds = Math.floor((now - date) / 1000);
            
            if (diffInSeconds < 60) return `${diffInSeconds}秒前`;
            if (diffInSeconds < 3600) return `${Math.floor(diffInSeconds / 60)}分钟前`;
            if (diffInSeconds < 86400) return `${Math.floor(diffInSeconds / 3600)}小时前`;
            
            // 超过一天显示具体时间
            return date.toLocaleString('zh-CN', {
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
        } catch (error) {
            return timeStr;
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
        
        // 如果是对象，构建 "频道标题 [用户名]" 格式
        if (typeof channelData === 'object') {
            let displayName = '';
            
            // 优先使用频道标题
            if (channelData.title) {
                displayName = channelData.title;
                
                // 如果有用户名，添加 [用户名] 后缀
                if (channelData.username) {
                    displayName += ` [${channelData.username}]`;
                }
                
                return displayName;
            }
            
            // 如果没有标题但有用户名
            if (channelData.username) {
                return `@${channelData.username}`;
            }
            
            // 最后降级到ID
            return this.formatChannelId(channelData.id) || '未知频道';
        }
        
        return '未知频道';
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
    },

    // 获取状态类型（用于CSS类）
    getStatusType(status) {
        const statusMap = {
            'pending': '',
            'approved': 'success',
            'rejected': 'danger',
            'auto_forwarded': 'info'
        };
        return statusMap[status] || '';
    },

    // 获取状态文本
    getStatusText(status) {
        const statusMap = {
            'pending': '待审核',
            'approved': '已发布',
            'rejected': '已拒绝',
            'auto_forwarded': '自动转发'
        };
        return statusMap[status] || status;
    },

    // 格式化文件大小
    formatFileSize(bytes) {
        if (!bytes || bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    },

    // 获取原消息链接
    getOriginalMessageLink(message) {
        if (!message.id) {
            return '#';
        }
        
        // 如果有 forward_from_chat 信息，优先使用
        if (message.forward_from_chat && message.forward_from_message_id) {
            const chatId = message.forward_from_chat.id || message.forward_from_chat;
            const messageId = message.forward_from_message_id;
            
            // 转换为正数（Telegram链接使用正数）
            const linkChatId = Math.abs(chatId);
            return `https://t.me/c/${linkChatId}/${messageId}`;
        }
        
        // 降级处理：使用当前消息信息
        if (message.source_channel_id && message.message_id) {
            const linkChatId = Math.abs(message.source_channel_id);
            return `https://t.me/c/${linkChatId}/${message.message_id}`;
        }
        
        return '#';
    },

    // 获取统计标签
    getStatLabel(statKey) {
        const statLabels = {
            'pending': '待审核',
            'approved': '已发布',
            'rejected': '已拒绝'
        };
        return statLabels[statKey] || statKey;
    },

    // 获取频道名称
    getChannelName(channel_id, channelInfo = {}) {
        if (channelInfo[channel_id]) {
            return channelInfo[channel_id].title || channelInfo[channel_id].name || channel_id;
        }
        return channel_id;
    },

    // 获取频道显示名称（用于下拉框）
    getChannelDisplayName(channel) {
        if (!channel) return '未知频道';
        
        // 优先使用title，其次name
        let displayName = channel.title || channel.name || '未知频道';
        
        // 添加[@用户名]标识
        const username = channel.username;
        if (username) {
            // 确保username以@开头
            const formattedUsername = username.startsWith('@') ? username : '@' + username;
            displayName += ` [${formattedUsername}]`;
        }
        
        // 如果名称太长，截取前50个字符（增加长度以容纳用户名）
        if (displayName.length > 50) {
            return displayName.substring(0, 50) + '...';
        }
        
        return displayName;
    },

    // 获取媒体类型图标（更新版本）
    getMediaTypeIcon(mediaType) {
        const iconMap = {
            'photo': '🖼️',
            'video': '🎥',
            'document': '📄',
            'animation': '🎬',
            'audio': '🎧',
            'sticker': '🎭',
            'voice': '🗣️',
            'video_note': '🎬'
        };
        return iconMap[mediaType] || '📎';
    },

    // 处理图片加载错误（增强版本）
    handleImageError(message, event) {
        // 静默处理，不输出日志避免控制台噪音
        // 标记媒体为不存在，触发补抓按钮显示
        if (message && !message._mediaLoadFailed) {
            message._mediaLoadFailed = true;
        }
        
        // 阻止错误冒泡到控制台
        if (event) {
            event.preventDefault();
        }
    }
};

// 导出模块
if (typeof module !== 'undefined' && module.exports) {
    module.exports = DataUtils;
} else {
    window.DataUtils = DataUtils;
}