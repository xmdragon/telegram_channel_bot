/**
 * API端点集中配置
 * 所有API端点都必须在此定义，禁止在其他文件硬编码
 * 
 * 使用方法：
 * import API from './config/api-endpoints.js';
 * const response = await axios.get(API.messages.list);
 * const response = await axios.delete(API.messages.deleteById(messageId));
 * 
 * 更新时间: 2025-09-16
 * 版本: 1.1.0
 */

const API_ENDPOINTS = {
    // 消息管理模块 - /api/messages
    messages: {
        list: '/api/messages/',                                     // GET - 获取消息列表（支持分页、搜索、过滤）
        stats: '/api/messages/stats/overview',                      // GET - 获取消息统计信息
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

        // 消息操作端点
        notAd: (id) => `/api/messages/not-ad/${id}`,               // POST - 标记消息为非广告
        filterContent: (id) => `/api/messages/filter-content/${id}`, // POST - 执行内容过滤
        publish: (id) => `/api/messages/publish/${id}`,            // POST - 发布消息（队列版本）
        publishDirect: (id) => `/api/messages/publish-direct/${id}`, // POST - 直接发布消息（新版本，不依赖采集开关）
        editPublish: (id) => `/api/messages/edit-publish/${id}`,   // POST - 编辑并发布
        trainTail: (id) => `/api/messages/train-tail/${id}`,       // POST - 训练尾部过滤
        refilter: (id) => `/api/messages/refilter/${id}`,          // POST - 重新过滤消息
        feedback: (id) => `/api/messages/feedback/${id}`,          // POST - 提交过滤反馈
        markAsAd: (id) => `/api/messages/mark-as-ad/${id}`         // POST - 标记为广告并保存关键词
    },

    // 管理员认证模块 - /api/admin/auth
    adminAuth: {
        login: '/api/admin/auth/login',                             // POST - 管理员登录
        logout: '/api/admin/auth/logout',                           // POST - 管理员登出
        checkAuth: '/api/admin/auth/check-auth',                    // GET - 检查认证状态
        current: '/api/admin/auth/current',                         // GET - 获取当前管理员信息
        changePassword: '/api/admin/auth/change-password',          // POST - 修改密码
        admins: '/api/admin/auth/admins',                           // GET/POST - 获取/创建管理员列表
        adminById: (id) => `/api/admin/auth/admins/${id}`           // PUT/DELETE - 更新/删除管理员
    },

// Telegram工具模块 - /api/telegram
    telegram: {
        messageStructure: '/api/telegram/message-structure'         // POST - 获取消息结构体
    },

    // 双Session认证模块 - /api/dual-auth
    dualAuth: {
        initSession: '/api/dual-auth/init-session',                    // POST - 初始化Session认证
        sendCode: '/api/dual-auth/send-code',                          // POST - 发送验证码
        verifyCode: '/api/dual-auth/verify-code',                      // POST - 验证验证码
        verifyPassword: '/api/dual-auth/verify-password',              // POST - 验证两步验证密码
        sessionStatus: (sessionType) => `/api/dual-auth/session-status/${sessionType}`, // GET - 获取Session状态
        clearSession: '/api/dual-auth/clear-session'                  // POST - 清除Session
    },

    // 训练数据模块 - /api/training
    training: {
        // 分隔符模式管理
        separatorPatterns: '/api/training/separator-patterns',   // GET/POST - 获取/保存分隔符模式
        testSeparator: '/api/training/test-separator',   // POST - 测试分隔符过滤

        
        // 权重关键词管理系统（新）
        adKeywords: '/api/training/ad-keywords',                  // GET - 获取所有关键词及权重
        addKeyword: '/api/training/ad-keywords',                  // POST - 添加关键词
        updateKeyword: (keyword) => `/api/training/ad-keywords/${encodeURIComponent(keyword)}`, // PUT - 更新关键词权重
        deleteKeyword: (keyword) => `/api/training/ad-keywords/${encodeURIComponent(keyword)}`, // DELETE - 删除关键词
        updateThreshold: '/api/training/ad-keywords/threshold',   // PUT - 更新检测阈值
        keywordStats: '/api/training/ad-keywords/stats',          // GET - 获取关键词检测统计

        // 尾部过滤样本管理
        tailFilterSamples: '/api/training/tail-filter-samples',  // GET/POST - 获取/添加尾部过滤样本
        tailFilterSampleById: (id) => `/api/training/tail-filter-samples/${id}`, // PUT/DELETE - 更新/删除尾部过滤样本
        tailFilterStatistics: '/api/training/tail-filter-statistics', // GET - 获取尾部过滤统计
        tailFilterHistory: '/api/training/tail-filter-history',  // GET - 获取尾部过滤历史

    },

// 统一频道管理模块 - /api/channels
    channels: {
        // 基础管理
        list: '/api/channels/',                                   // GET - 获取所有源频道
        add: '/api/channels/',                                    // POST - 添加源频道
        delete: (channel_id) => `/api/channels/${channel_id}`,    // DELETE - 删除源频道
        get: (channel_id) => `/api/channels/${channel_id}`,       // GET - 获取单个频道信息

        // 批量操作
        batchAdd: '/api/channels/batch-add',                      // POST - 批量添加源频道
        search: '/api/channels/search',                           // GET - 搜索源频道

        // 解析功能（仅源频道）
        resolve: '/api/channels/resolve',                         // POST - 解析单个源频道ID
        resolveAll: '/api/channels/resolve-all'                   // POST - 批量解析所有源频道
    },

    // 系统状态模块 - /api/system
    system: {
        // 系统健康检查（保留唯一使用的端点）
        health: '/api/health',                                     // GET - 健康检查（主要使用）
        systemStatus: '/api/system/status',                        // GET - 系统状态
        detailedStatus: '/api/system/status-detailed',             // GET - 详细系统状态

        reset: '/api/system/reset',                                // POST - 重置系统

        // 锁状态管理（保留实际使用的端点）
        lockStatus: '/api/system/lock-status',                     // GET - 获取Telegram锁状态
        clearLock: '/api/system/clear-lock',                       // POST - 清理锁
        autoClearLock: '/api/system/auto-clear-lock',              // POST - 智能清理过期锁
    },

    // 管理功能模块 - /api/admin
    admin: {
        // 配置管理
        config: '/api/admin/config',                               // GET - 获取管理配置
        configForwarding: '/api/admin/config/forwarding',          // POST - 配置转发
        configBatch: '/api/admin/config/batch'                     // POST - 批量配置
    },


    // WebSocket端点 - 统一管理：所有WebSocket连接必须使用WebSocketFactory.create()
    // 禁止直接构造WebSocket，统一使用：WebSocketFactory.create('main')
    websocket: {
        main: '/ws',                                               // WebSocket - 主要连接（通过WebSocketFactory使用）
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
        separatorConfig: '/static/separator-config.html',          // 分隔符配置页面
        telegramMessage: '/static/telegram-message.html'           // Telegram消息工具页面
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