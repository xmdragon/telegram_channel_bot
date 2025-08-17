/**
 * API端点集中配置
 * 所有API端点都必须在此定义，禁止在其他文件硬编码
 * 
 * 使用方法：
 * import API from './config/api-endpoints.js';
 * const response = await axios.get(API.messages.list);
 * const response = await axios.delete(API.messages.deleteById(messageId));
 * 
 * 更新时间: 2025-08-17
 * 版本: 1.0.0
 */

const API_ENDPOINTS = {
    // 消息管理模块 - /api/messages
    messages: {
        list: '/api/messages/',                                     // GET - 获取消息列表（支持分页、搜索、过滤）
        stats: '/api/messages/stats',                               // GET - 获取消息统计信息
        statsOverview: '/api/messages/stats/overview',              // GET - 获取消息统计概览
        
        // 阈值管理端点
        thresholdsStats: '/api/messages/thresholds/stats',          // GET - 获取阈值统计
        thresholdsOptimize: '/api/messages/thresholds/optimize',    // POST - 优化阈值
        thresholdsReset: (filterName, metricName) => `/api/messages/thresholds/${filterName}/${metricName}/reset`, // POST - 重置阈值
        testMessageFeedback: '/api/messages/test-message/feedback', // POST - 测试消息反馈
        channelInfo: '/api/messages/channel-info',                 // GET - 获取频道信息
        getById: (id) => `/api/messages/${id}`,                    // GET - 根据ID获取单个消息
        updateById: (id) => `/api/messages/${id}`,                 // PUT - 更新消息内容
        deleteById: (id) => `/api/messages/${id}`,                 // DELETE - 删除单个消息
        approveById: (id) => `/api/messages/${id}/approve`,        // POST - 审核通过单个消息
        rejectById: (id) => `/api/messages/${id}/reject`,          // POST - 拒绝单个消息
        deleteReviewById: (id) => `/api/messages/${id}/review-message`, // DELETE - 删除审核消息
        resendById: (id) => `/api/messages/resend/${id}`,          // POST - 重新发送已批准消息到目标频道
        batchApprove: '/api/messages/batch-approve',               // POST - 批量审核通过消息
        batchReject: '/api/messages/batch-reject',                 // POST - 批量拒绝消息
        batchDelete: '/api/messages/batch-delete',                 // POST - 批量删除消息
        batchApproveAlt: '/api/messages/batch/approve',            // POST - 批量审核通过消息（备用端点）
        batchRejectAlt: '/api/messages/batch/reject',              // POST - 批量拒绝消息（备用端点）
        batchDeleteAlt: '/api/messages/batch/delete',              // POST - 批量删除消息（备用端点）
        reset: '/api/messages/reset',                              // POST - 重置消息
        export: '/api/messages/export'                             // GET - 导出消息数据
    },

    // 管理员认证模块 - /api/admin/auth
    adminAuth: {
        login: '/api/admin/auth/login',                             // POST - 管理员登录
        logout: '/api/admin/auth/logout',                           // POST - 管理员登出
        checkAuth: '/api/admin/auth/check-auth',                    // GET - 检查认证状态
        current: '/api/admin/auth/current',                         // GET - 获取当前管理员信息
        changePassword: '/api/admin/auth/change-password',          // POST - 修改密码
        admins: '/api/admin/auth/admins',                           // GET/POST - 获取/创建管理员列表
        adminById: (id) => `/api/admin/auth/admins/${id}`,          // PUT/DELETE - 更新/删除管理员
        permissions: '/api/admin/auth/permissions'                  // GET - 获取权限列表
    },

    // Telegram认证模块 - /api/auth
    telegramAuth: {
        init: '/api/auth/init',                                     // POST - 初始化认证
        sendCode: '/api/auth/send-code',                            // POST - 发送验证码
        verifyCode: '/api/auth/verify-code',                        // POST - 验证验证码
        verifyPassword: '/api/auth/verify-password',                // POST - 验证密码
        status: '/api/auth/status',                                 // GET - 获取认证状态
        info: '/api/auth/info',                                     // GET - 获取认证信息
        clear: '/api/auth/clear',                                   // POST - 清理认证
        disconnect: '/api/auth/disconnect',                         // POST - 断开连接
        logout: '/api/auth/logout'                                  // POST - 登出Telegram
    },

    // 训练数据模块 - /api/training-db
    training: {
        // 分隔符模式管理
        separatorPatterns: '/api/training-db/separator-patterns',   // GET/POST - 获取/保存分隔符模式

        // 广告样本管理
        adSamples: '/api/training-db/ad-samples',                   // GET - 获取广告样本列表（分页）
        adSampleById: (id) => `/api/training-db/ad-samples/${id}`,  // DELETE - 删除单个广告样本
        adSamplesBatch: '/api/training-db/ad-samples/batch',        // DELETE - 批量删除广告样本
        adSamplesDetectDuplicates: '/api/training-db/ad-samples/detect-duplicates', // POST - 检测重复广告样本
        adSamplesDeduplicate: '/api/training-db/ad-samples/deduplicate', // POST - 去重广告样本
        adStatistics: '/api/training-db/ad-statistics',             // GET - 获取广告训练统计

        // 尾部过滤样本管理
        tailFilterSamples: '/api/training-db/tail-filter-samples',  // GET/POST - 获取/添加尾部过滤样本
        tailFilterSampleById: (id) => `/api/training-db/tail-filter-samples/${id}`, // PUT/DELETE - 更新/删除尾部过滤样本
        tailFilterStatistics: '/api/training-db/tail-filter-statistics', // GET - 获取尾部过滤统计
        tailFilterHistory: '/api/training-db/tail-filter-history',  // GET - 获取尾部过滤历史
        tailFilterDetectDuplicates: '/api/training-db/tail-filter-samples/detect-duplicates', // POST - 检测重复尾部样本
        tailFilterDeduplicate: '/api/training-db/tail-filter-samples/deduplicate', // POST - 去重尾部样本

        // 媒体文件管理
        mediaFiles: '/api/training-db/media-files',                 // GET - 获取媒体文件列表
        mediaFileById: (hash) => `/api/training-db/media-files/${hash}`, // DELETE - 删除媒体文件
        mediaFileOcr: (hash) => `/api/training-db/media-files/${hash}/ocr`, // GET - 获取媒体文件OCR结果
        mediaFilesExport: '/api/training-db/media-files/export',    // GET - 导出媒体文件
        mediaFilesCleanOrphaned: '/api/training-db/media-files/clean-orphaned', // POST - 清理孤立文件
        mediaFilesDuplicates: '/api/training-db/media-files/duplicates', // GET - 检测重复媒体文件
        mediaFilesDeduplicate: '/api/training-db/media-files/deduplicate', // POST - 去重媒体文件
        mediaFilesRebuildHashes: '/api/training-db/media-files/rebuild-visual-hashes', // POST - 重建视觉哈希

        // 其他训练功能
        channels: '/api/training-db/channels',                      // GET - 获取频道列表
        stats: '/api/training-db/stats',                           // GET - 获取训练统计
        history: '/api/training-db/history',                       // GET - 获取训练历史
        submit: '/api/training-db/submit',                         // POST - 提交训练数据
        apply: '/api/training-db/apply',                           // POST - 应用训练数据
        sampleById: (id) => `/api/training-db/sample/${id}`,       // GET - 获取训练样本详情
        clearChannel: (id) => `/api/training-db/clear/${id}`,      // DELETE - 清除频道训练数据
        autoLearn: (id) => `/api/training-db/auto-learn/${id}`,    // POST - 自动学习频道模式
        exportData: '/api/training-db/export',                     // GET - 导出训练数据
        optimizeStorage: '/api/training-db/optimize-storage',      // POST - 优化存储空间
        reloadModel: '/api/training-db/reload-model',              // POST - 重新加载模型
        markAdMessage: '/api/training-db/mark-ad-message',         // POST - 标记消息为广告
        markAdTest: '/api/training-db/mark-ad-test',               // POST - 测试标记功能
        learningStats: '/api/training-db/learning-stats',         // GET - 获取学习统计
        
        // 额外的训练相关端点
        tailAdSamples: '/api/training-db/tail-ad-samples',         // GET/POST - 尾部广告样本
        promoSamples: '/api/training-db/promo-samples',            // POST - 推广样本
        previewPromoFilter: '/api/training-db/preview-promo-filter' // POST - 预览推广过滤器
    },

    // 配置管理模块 - /api/config
    config: {
        channelConfig: '/api/config/channel-config',               // GET/POST - 频道配置
        systemConfig: '/api/config/system-config',                // GET/POST - 系统配置
        filterConfig: '/api/config/filter-config',                // GET/POST - 过滤器配置
        thresholds: '/api/config/thresholds',                     // GET/POST - 阈值配置
        export: '/api/config/export',                             // GET - 导出配置
        import: '/api/config/import',                             // POST - 导入配置
        channelsBatchAdd: '/api/config/channels/batch-add'        // POST - 批量添加频道
    },

    // 系统状态模块 - /api/system
    system: {
        status: '/api/status',                                     // GET - 系统状态
        systemStatus: '/api/system/status',                        // GET - 详细系统状态
        health: '/api/health',                                     // GET - 健康检查
        logs: '/api/system/logs',                                  // GET - 系统日志
        clearCache: '/api/system/clear-cache',                    // POST - 清理缓存
        restart: '/api/system/restart',                           // POST - 重启系统
        reset: '/api/system/reset'                                // POST - 重置系统
    },

    // 管理功能模块 - /api/admin
    admin: {
        collect: '/api/admin/collect',                             // POST - 开始采集
        test: '/api/admin/test',                                   // POST - 测试功能
        stopCollection: '/api/admin/stop-collection',             // POST - 停止采集
        
        // 频道管理
        channels: '/api/admin/channels',                           // GET/POST - 获取/添加频道
        addChannel: '/api/admin/add-channel',                      // POST - 添加单个频道
        resolveChannelId: '/api/admin/resolve-channel-id',         // POST - 解析频道ID
        resolveChannelIds: '/api/admin/resolve-channel-ids',       // POST - 批量解析频道ID
        searchChannels: '/api/admin/search-channels',              // GET - 搜索频道
        resolveReviewGroup: '/api/admin/resolve-review-group',     // POST - 解析审核群组
        
        // 配置管理
        config: '/api/admin/config',                               // GET - 获取管理配置
        configForwarding: '/api/admin/config/forwarding',          // POST - 配置转发
        configBatch: '/api/admin/config/batch'                     // POST - 批量配置
    },

    // 进程锁模块 - /api/lock
    lock: {
        status: '/api/lock/status',                                // GET - 锁状态
        acquire: '/api/lock/acquire',                              // POST - 获取锁
        release: '/api/lock/release'                               // POST - 释放锁
    },

    // WebSocket端点
    websocket: {
        main: '/ws',                                               // WebSocket - 主要连接
        notifications: '/ws/notifications'                         // WebSocket - 通知连接
    },

    // 媒体和静态文件路径
    media: {
        tempMedia: '/temp_media',                                  // 临时媒体文件路径
        adTrainingData: '/media/ad_training_data',                 // 广告训练数据媒体路径
        static: '/static'                                          // 静态文件路径
    },

    // 页面路径配置
    pages: {
        index: '/static/index.html',                               // 主页
        admin: '/static/admin.html',                               // 管理页面
        config: '/static/config.html',                             // 配置页面
        auth: '/static/auth.html',                                 // 认证页面
        status: '/static/status.html',                             // 状态页面
        train: '/static/train.html',                               // 训练页面
        login: '/static/login.html'                                // 登录页面
    }
};

/**
 * 工具函数：构建带查询参数的URL
 * @param {string} baseUrl - 基础URL
 * @param {Object} params - 查询参数
 * @returns {string} 完整的URL
 */
function buildUrl(baseUrl, params = {}) {
    const url = new URL(baseUrl, window.location.origin);
    Object.entries(params).forEach(([key, value]) => {
        if (value !== null && value !== undefined && value !== '') {
            url.searchParams.append(key, value);
        }
    });
    return url.pathname + url.search;
}

/**
 * 工具函数：获取WebSocket URL
 * @param {string} path - WebSocket路径
 * @returns {string} 完整的WebSocket URL
 */
function getWebSocketUrl(path) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}${path}`;
}

// 添加工具方法到API对象
API_ENDPOINTS.utils = {
    buildUrl,
    getWebSocketUrl
};

// 冻结对象防止运行时修改
Object.freeze(API_ENDPOINTS);

// 导出为全局变量（兼容旧代码）
if (typeof window !== 'undefined') {
    window.API = API_ENDPOINTS;
}

// 兼容传统script标签引入方式，注释掉ES6导出
// export default API_ENDPOINTS;