/**
 * 工具函数模块
 */

const Utils = {
    // 格式化时间
    formatTime(dateString) {
        if (!dateString) return '';
        
        try {
            const date = new Date(dateString);
            const now = new Date();
            const diff = now - date;
            
            if (diff < 60000) return '刚刚';
            if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`;
            if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`;
            if (diff < 604800000) return `${Math.floor(diff / 86400000)}天前`;
            
            return date.toLocaleDateString('zh-CN', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit'
            });
        } catch (error) {
            return dateString;
        }
    },
    
    // 获取状态标签
    getStatusTag(status) {
        const statusMap = {
            'pending': { text: '待审核', type: 'warning' },
            'approved': { text: '已批准', type: 'success' },
            'rejected': { text: '已拒绝', type: 'danger' },
            'auto_forwarded': { text: '自动转发', type: 'info' }
        };
        return statusMap[status] || { text: status, type: 'default' };
    }
};

window.Utils = Utils;