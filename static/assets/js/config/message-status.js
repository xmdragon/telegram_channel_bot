// 消息状态定义 - 与后端保持一致

window.MessageStatus = {
    // 7种细分状态
    PENDING: 'pending',               // 待审核 - 未发送失败过
    SEND_FAILED: 'send_failed',       // 发送失败
    AUTO_APPROVED: 'auto_approved',   // 自动发布
    MANUAL_APPROVED: 'manual_approved',// 手动发布
    AD_REJECTED: 'ad_rejected',       // 广告拒绝
    DUP_REJECTED: 'dup_rejected',     // 重复拒绝
    MANUAL_REJECTED: 'manual_rejected',// 手动拒绝

    // 兼容旧3状态系统
    LEGACY_PENDING: 'pending',
    LEGACY_APPROVED: 'approved',
    LEGACY_REJECTED: 'rejected',

    // 状态显示信息
    getStatusInfo(status) {
        const statusInfo = {
            // 新状态
            'pending': {
                label: '待审核',
                color: '#409EFF',
                bgColor: 'rgba(64, 158, 255, 0.1)',
                icon: 'clock',
                description: '等待审核的消息'
            },
            'send_failed': {
                label: '发送失败',
                color: '#F56C6C',
                bgColor: 'rgba(245, 108, 108, 0.1)',
                icon: 'exclamation-triangle',
                description: '发送失败需要重试'
            },
            'auto_approved': {
                label: '自动发布',
                color: '#67C23A',
                bgColor: 'rgba(103, 194, 58, 0.1)',
                icon: 'check-circle',
                description: '系统自动发布'
            },
            'manual_approved': {
                label: '手动发布',
                color: '#19A77B',
                bgColor: 'rgba(25, 167, 123, 0.1)',
                icon: 'user-check',
                description: '人工审核发布'
            },
            'ad_rejected': {
                label: '广告拒绝',
                color: '#E6A23C',
                bgColor: 'rgba(230, 162, 60, 0.1)',
                icon: 'ban',
                description: '检测为广告拒绝'
            },
            'dup_rejected': {
                label: '重复拒绝',
                color: '#909399',
                bgColor: 'rgba(144, 147, 153, 0.1)',
                icon: 'copy',
                description: '检测为重复拒绝'
            },
            'manual_rejected': {
                label: '手动拒绝',
                color: '#F56C6C',
                bgColor: 'rgba(245, 108, 108, 0.1)',
                icon: 'times-circle',
                description: '人工审核拒绝'
            },
            // 兼容旧状态
            'approved': {
                label: '已发布',
                color: '#67C23A',
                bgColor: 'rgba(103, 194, 58, 0.1)',
                icon: 'check-circle',
                description: '消息已发布'
            },
            'rejected': {
                label: '已拒绝',
                color: '#F56C6C',
                bgColor: 'rgba(245, 108, 108, 0.1)',
                icon: 'times-circle',
                description: '消息已拒绝'
            }
        };

        return statusInfo[status] || {
            label: status,
            color: '#909399',
            bgColor: 'rgba(144, 147, 153, 0.1)',
            icon: 'question-circle',
            description: '未知状态'
        };
    },

    // 判断是否为已发布状态
    isApproved(status) {
        return [this.AUTO_APPROVED, this.MANUAL_APPROVED, this.LEGACY_APPROVED].includes(status);
    },

    // 判断是否为已拒绝状态
    isRejected(status) {
        return [this.AD_REJECTED, this.DUP_REJECTED, this.MANUAL_REJECTED, this.LEGACY_REJECTED].includes(status);
    },

    // 判断是否为待处理状态
    isPending(status) {
        return [this.PENDING, this.SEND_FAILED].includes(status);
    },

    // 获取旧状态（向后兼容）
    getLegacyStatus(status) {
        if (this.isPending(status)) {
            return this.LEGACY_PENDING;
        } else if (this.isApproved(status)) {
            return this.LEGACY_APPROVED;
        } else if (this.isRejected(status)) {
            return this.LEGACY_REJECTED;
        }
        return status;
    }
};