/**
 * 时间格式化工具函数
 * 用于将时间戳转换为友好的相对时间显示
 */

/**
 * 将ISO时间字符串格式化为友好的相对时间
 * @param {string} isoTimeString - ISO格式的时间字符串
 * @returns {string} 格式化后的时间字符串，如"1分钟前"、"2小时前"、"3天前"
 */
function formatTimeAgo(isoTimeString) {
    // 处理空值
    if (!isoTimeString) {
        return '未同步';
    }

    try {
        const now = new Date();
        const time = new Date(isoTimeString);

        // 检查时间是否有效
        if (isNaN(time.getTime())) {
            return '时间无效';
        }

        const diffMs = now.getTime() - time.getTime();

        // 如果是未来时间，显示"刚刚"
        if (diffMs < 0) {
            return '刚刚';
        }

        const diffSeconds = Math.floor(diffMs / 1000);
        const diffMinutes = Math.floor(diffSeconds / 60);
        const diffHours = Math.floor(diffMinutes / 60);
        const diffDays = Math.floor(diffHours / 24);
        const diffWeeks = Math.floor(diffDays / 7);
        const diffMonths = Math.floor(diffDays / 30);

        // 根据时间差返回不同的格式
        if (diffSeconds < 60) {
            return '刚刚';
        } else if (diffMinutes < 60) {
            return `${diffMinutes}分钟前`;
        } else if (diffHours < 24) {
            return `${diffHours}小时前`;
        } else if (diffDays < 7) {
            return `${diffDays}天前`;
        } else if (diffWeeks < 4) {
            return `${diffWeeks}周前`;
        } else if (diffMonths < 12) {
            return `${diffMonths}个月前`;
        } else {
            const diffYears = Math.floor(diffMonths / 12);
            return `${diffYears}年前`;
        }
    } catch (error) {
        console.error('时间格式化错误:', error);
        return '时间错误';
    }
}

/**
 * 根据时间间隔返回CSS类名，用于不同的颜色提醒
 * @param {string} isoTimeString - ISO格式的时间字符串
 * @returns {string} CSS类名
 */
function getTimeAgoClass(isoTimeString) {
    if (!isoTimeString) {
        return 'never-synced';
    }

    try {
        const now = new Date();
        const time = new Date(isoTimeString);
        const diffMs = now.getTime() - time.getTime();
        const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

        if (diffDays >= 7) {
            return 'long-time-ago'; // 超过一周，红色警告
        } else if (diffDays >= 3) {
            return 'some-time-ago'; // 超过3天，橙色提醒
        } else {
            return 'recent'; // 最近，正常颜色
        }
    } catch (error) {
        return 'time-error';
    }
}

/**
 * 获取完整的时间显示信息
 * @param {string} isoTimeString - ISO格式的时间字符串
 * @returns {object} 包含文本和CSS类的对象
 */
function getTimeDisplayInfo(isoTimeString) {
    return {
        text: formatTimeAgo(isoTimeString),
        cssClass: getTimeAgoClass(isoTimeString),
        timestamp: isoTimeString
    };
}

// 导出函数供其他模块使用
window.TimeUtils = {
    formatTimeAgo,
    getTimeAgoClass,
    getTimeDisplayInfo
};