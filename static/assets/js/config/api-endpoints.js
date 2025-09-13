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
        stats: '/api/messages/stats/overview',                      // GET - 获取消息统计信息（修复：使用正确的端点）
        statsOverview: '/api/messages/stats/overview',              // GET - 获取消息统计概览
        linusStatsOverview: '/api/stats/linus-overview',            // GET - Linus式统计概览（新增）
        testMessageFeedback: '/api/messages/test-message/feedback', // POST - 测试消息反馈
        channelInfo: '/api/messages/channel-info',                 // GET - 获取频道信息
        getById: (id) => `/api/messages/detail/${id}`,             // GET - 根据ID获取单个消息
        updateById: (id) => `/api/messages/update/${id}`,          // PUT - 更新消息内容
        deleteById: (id) => `/api/messages/delete/${id}`,          // DELETE - 删除单个消息
        approveById: (id) => `/api/messages/approve/${id}`,        // POST - 审核通过单个消息
        rejectById: (id) => `/api/messages/reject/${id}`,          // POST - 拒绝单个消息
        restoreById: (id) => `/api/messages/restore/${id}`,        // POST - 恢复被拒绝的消息到未审核状态
        deleteReviewById: (id) => `/api/messages/delete-review/${id}`, // DELETE - 删除审核消息
        resendById: (id) => `/api/messages/resend/${id}`,          // POST - 重新发布已发布消息到目标频道
        batchApprove: '/api/messages/batch/approve',               // POST - 批量审核通过消息
        batchReject: '/api/messages/batch/reject',                 // POST - 批量拒绝消息
        batchDelete: '/api/messages/batch/delete',                 // POST - 批量删除消息
        reset: '/api/messages/reset',                              // POST - 重置消息
        
        // 消息操作端点
        notAd: (id) => `/api/messages/not-ad/${id}`,               // POST - 标记消息为非广告
        filterContent: (id) => `/api/messages/filter-content/${id}`, // POST - 执行内容过滤
        publish: (id) => `/api/messages/publish/${id}`,            // POST - 发布消息（队列版本）
        publishDirect: (id) => `/api/messages/publish-direct/${id}`, // POST - 直接发布消息（新版本，不依赖采集开关）
        editPublish: (id) => `/api/messages/edit-publish/${id}`,   // POST - 编辑并发布
        refetchMedia: (id) => `/api/messages/refetch-media/${id}`, // POST - 重新获取媒体
        trainTail: (id) => `/api/messages/train-tail/${id}`,       // POST - 训练尾部过滤
        refilter: (id) => `/api/messages/refilter/${id}`,          // POST - 重新过滤消息
        feedback: (id) => `/api/messages/feedback/${id}`,          // POST - 提交过滤反馈
        refetchTask: (taskId) => `/api/refetch-task/${taskId}`     // GET - 查询媒体补抓任务状态
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

    // Telegram认证模块 - /api/telegram-auth
    telegramAuth: {
        init: '/api/telegram-auth/init',                            // POST - 初始化认证
        sendCode: '/api/telegram-auth/send-code',                   // POST - 发送验证码
        verifyCode: '/api/telegram-auth/verify-code',               // POST - 验证验证码
        verifyPassword: '/api/telegram-auth/verify-password',       // POST - 验证密码
        status: '/api/telegram-auth/status',                        // GET - 获取认证状态
        info: '/api/telegram-auth/info',                            // GET - 获取认证信息
        clear: '/api/telegram-auth/clear',                          // POST - 清理认证
        disconnect: '/api/telegram-auth/disconnect',                // POST - 断开连接
        logout: '/api/telegram-auth/logout'                         // POST - 登出Telegram
    },

    // Telegram工具模块 - /api/telegram
    telegram: {
        messageStructure: '/api/telegram/message-structure'         // POST - 获取消息结构体
    },

    // 双Session认证模块 - /api/dual-auth
    dualAuth: {
        sharedApiConfig: '/api/dual-auth/shared-api-config',           // POST - 设置共享API配置
        initSession: '/api/dual-auth/init-session',                    // POST - 初始化Session认证
        sendCode: '/api/dual-auth/send-code',                          // POST - 发送验证码
        verifyCode: '/api/dual-auth/verify-code',                      // POST - 验证验证码
        verifyPassword: '/api/dual-auth/verify-password',              // POST - 验证两步验证密码
        sessionStatus: (sessionType) => `/api/dual-auth/session-status/${sessionType}`, // GET - 获取Session状态
        dualSessionStatus: '/api/dual-auth/dual-session-status',       // GET - 获取双Session状态
        clearSession: '/api/dual-auth/clear-session',                  // POST - 清除Session
        migrateConfig: '/api/dual-auth/migrate-config',                // POST - 迁移配置
        disconnectAll: '/api/dual-auth/disconnect-all'                 // POST - 断开所有连接
    },

    // 训练数据模块 - /api/training
    training: {
        // 分隔符模式管理
        separatorPatterns: '/api/training/separator-patterns',   // GET/POST - 获取/保存分隔符模式

        // 关键词管理 (原广告向量管理)
        adVectors: '/api/training/ad-vectors',                   // GET - 获取关键词规则列表（分页）
        adVectorById: (id) => `/api/training/ad-vectors/${id}`,  // DELETE - 删除单个关键词规则
        adVectorsBatch: '/api/training/ad-vectors/batch',        // DELETE - 批量删除关键词规则
        adVectorStatistics: '/api/training/ad-vector-statistics', // GET - 获取关键词规则统计
        adVectorTestDetection: '/api/training/ad-vectors/test-detection', // POST - 测试关键词检测
        adVectorAddFromText: '/api/training/ad-vectors/add-from-text', // POST - 从文本添加关键词
        adVectorStats: '/api/training/ad-vector-stats',          // GET - 获取关键词统计

        // 尾部过滤样本管理
        tailFilterSamples: '/api/training/tail-filter-samples',  // GET/POST - 获取/添加尾部过滤样本
        tailFilterSampleById: (id) => `/api/training/tail-filter-samples/${id}`, // PUT/DELETE - 更新/删除尾部过滤样本
        tailFilterStatistics: '/api/training/tail-filter-statistics', // GET - 获取尾部过滤统计
        tailFilterHistory: '/api/training/tail-filter-history',  // GET - 获取尾部过滤历史
        tailFilterRebuildVectors: '/api/training/tail-filter-rebuild-vectors', // POST - 重建尾部过滤向量索引

        // 媒体文件管理
        mediaFiles: '/api/training/media-files',                 // GET - 获取媒体文件列表
        mediaFileById: (hash) => `/api/training/media-files/${hash}`, // DELETE - 删除媒体文件
        // OCR功能已移除
        mediaFilesExport: '/api/training/media-files/export',    // GET - 导出媒体文件
        mediaFilesCleanOrphaned: '/api/training/media-files/clean-orphaned', // POST - 清理孤立文件
        mediaFilesRebuildHashes: '/api/training/media-files/rebuild-visual-hashes', // POST - 重建视觉哈希

        // 其他训练功能
        channels: '/api/training/channels',                      // GET - 获取频道列表
        stats: '/api/training/stats',                           // GET - 获取训练统计
        history: '/api/training/history',                       // GET - 获取训练历史
        submit: '/api/training/submit',                         // POST - 提交训练数据
        apply: '/api/training/apply',                           // POST - 应用训练数据
        sampleById: (id) => `/api/training/sample/${id}`,       // GET - 获取训练样本详情
        clearChannel: (id) => `/api/training/clear/${id}`,      // DELETE - 清除频道训练数据
        autoLearn: (id) => `/api/training/auto-learn/${id}`,    // POST - 自动学习频道模式
        exportData: '/api/training/export',                     // GET - 导出训练数据
        optimizeStorage: '/api/training/optimize-storage',      // POST - 优化存储空间
        reloadModel: '/api/training/reload-model',              // POST - 重新加载模型
        markAdMessage: '/api/training/mark-ad-message',         // POST - 标记消息为广告
        markAdTest: '/api/training/mark-ad-test',               // POST - 测试标记功能
        learningStats: '/api/training/learning-stats',         // GET - 获取学习统计
        
        // 额外的训练相关端点
        tailAdSamples: '/api/training/tail-ad-samples',         // GET/POST - 尾部广告样本
        promoSamples: '/api/training/promo-samples',            // GET/POST - 推广样本
        promoSampleById: (id) => `/api/training/promo-samples/${id}`, // PUT/DELETE - 更新/删除推广样本
        previewPromoFilter: '/api/training/preview-promo-filter', // POST - 预览推广过滤器
        
        // 阈值管理
    },

    // 配置管理模块 - /api/config
    config: {
        list: '/api/config/',                                     // GET - 获取所有配置
        channelConfig: '/api/config/channel-config',               // GET/POST - 频道配置
        systemConfig: '/api/config/system-config',                // GET/POST - 系统配置
        filterConfig: '/api/config/filter-config',                // GET/POST - 过滤器配置
        export: '/api/config/export',                             // GET - 导出配置
        import: '/api/config/import',                             // POST - 导入配置
        channelsBatchAdd: '/api/config/channels/batch-add',       // POST - 批量添加频道
        channelsById: (channel_id) => `/api/config/channels/${channel_id}` // GET/DELETE - 获取/删除频道
    },

    // 系统状态模块 - /api/system
    system: {
        // 系统健康检查
        status: '/api/status',                                     // GET - 系统基本状态
        systemStatus: '/api/system/status',                        // GET - 系统详细状态
        statusDetailed: '/api/system/status/detailed',             // GET - 系统详细状态信息
        health: '/api/health',                                     // GET - 简单健康检查
        systemHealth: '/api/system/health',                        // GET - 详细健康检查
        
        // 系统日志管理
        logs: '/api/system/logs',                                  // GET - 系统日志
        logsRealtime: '/api/system/logs/realtime',                 // GET - 实时日志更新
        
        
        // 系统维护操作
        restart: '/api/system/restart',                            // POST - 重启系统服务
        reset: '/api/system/reset',                                // POST - 重置系统数据
        
        // 服务管理
        services: '/api/system/services',                          // GET - 获取所有服务状态
        serviceStatus: (serviceName) => `/api/system/services/${serviceName}/status`,   // GET - 获取单个服务状态
        serviceStart: (serviceName) => `/api/system/services/${serviceName}/start`,     // POST - 启动服务
        serviceStop: (serviceName) => `/api/system/services/${serviceName}/stop`,       // POST - 停止服务
        serviceRestart: (serviceName) => `/api/system/services/${serviceName}/restart`, // POST - 重启服务
        
        // 锁状态管理
        lockStatus: '/api/system/lock-status',                     // GET - 获取Telegram锁状态
        clearLock: '/api/system/clear-lock',                       // POST - 清理锁
        autoClearLock: '/api/system/auto-clear-lock',              // POST - 智能清理过期锁
        
        // 已废弃或重复的端点（保留向后兼容）
        clearCache: '/api/system/clear-cache',                     // POST - 清理缓存（已废弃）
    },

    // 管理功能模块 - /api/admin
    admin: {
        collect: '/api/admin/collect',                             // POST - 开始采集
        test: '/api/admin/test',                                   // POST - 测试功能
        stopCollection: '/api/admin/stop-collection',             // POST - 停止采集
        
        // 频道管理
        channels: '/api/admin/channels',                           // GET/POST - 获取/添加频道
        resolveChannelId: '/api/admin/resolve-channel-id',         // POST - 解析频道ID
        resolveChannelIds: '/api/admin/resolve-channel-ids',       // POST - 批量解析频道ID
        searchChannels: '/api/admin/search-channels',              // GET - 搜索频道
        resolveReviewGroup: '/api/admin/resolve-review-group',     // POST - 解析审核群组
        
        // 配置管理
        config: '/api/admin/config',                               // GET - 获取管理配置
        configForwarding: '/api/admin/config/forwarding',          // POST - 配置转发
        configBatch: '/api/admin/config/batch',                    // POST - 批量配置
        
        // 过滤器管理
        reloadFilters: '/api/admin/reload-filters'                 // POST - 重新加载过滤器配置
    },


    // WebSocket端点 - Linus式统一管理：所有WebSocket连接必须使用WebSocketFactory.create()
    // 禁止直接构造WebSocket，统一使用：WebSocketFactory.create('main')
    websocket: {
        main: '/ws',                                               // WebSocket - 主要连接（通过WebSocketFactory使用）
    },

    // AI配置模块 - /api/ai-config
    aiConfig: {
        status: '/api/ai-config/status',                           // GET - 获取AI功能状态
        globalConfig: '/api/ai-config/global-config',              // POST - 更新全局AI配置
        moduleConfig: '/api/ai-config/module-config',              // POST - 更新单个模块配置
        cacheClear: '/api/ai-config/cache/clear',                  // POST - 清理模型缓存
        lightweightTrain: '/api/ai-config/lightweight/train',      // POST - 训练轻量级模型
        recommendations: '/api/ai-config/recommendations'          // GET - 获取AI配置建议
    },

    // 媒体和静态文件路径
    media: {
        tempMedia: '/temp_media',                                  // 临时媒体文件路径
        adTrainingData: '/media',                                  // 广告训练数据媒体路径（Nginx直接映射）
        static: '/static'                                          // 静态文件路径
    },

    // 页面路径配置
    pages: {
        index: '/static/index.html',                               // 主页
        admin: '/static/admin.html',                               // 管理页面
        config: '/static/config.html',                             // 配置页面
        auth: '/static/telegram-auth.html',                        // Telegram认证页面
        status: '/static/status.html',                             // 状态页面
        login: '/static/login.html',                               // 登录页面
        
        // 训练模块页面
        tailFilterManager: '/static/tail-filter-manager.html',     // 尾部过滤训练管理页面
        tailFilterTraining: '/static/tail-filter-training.html',   // 尾部过滤训练独立页面
        adVectorManager: '/static/ad-training-samples.html',       // 关键词管理页面
        promoManager: '/static/promo-manager.html',                // 推广链接数据管理页面
        promoTraining: '/static/promo-training.html',              // 推广链接训练页面
        separatorConfig: '/static/separator-config.html',          // 分隔符配置页面
        mediaManager: '/static/media-manager.html',                // 媒体文件管理页面
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