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
        // 基础查询
        list: '/api/messages/',                                     // GET - 获取消息列表
        channelInfo: '/api/messages/channel-info',                 // GET - 获取频道信息
        getById: (id) => `/api/messages/detail/${id}`,             // GET - 获取单个消息

        // 核心操作
        approveById: (id) => `/api/messages/approve/${id}`,        // POST - 审核通过
        rejectById: (id) => `/api/messages/reject/${id}`,          // POST - 拒绝
        restoreById: (id) => `/api/messages/restore/${id}`,        // POST - 恢复
        deleteById: (id) => `/api/messages/delete/${id}`,          // DELETE - 删除
        updateById: (id) => `/api/messages/update/${id}`,          // PUT - 更新

        // 过滤器操作
        filterContent: (id) => `/api/messages/filter-content/${id}`, // POST - 执行内容过滤
        markAsAd: (id) => `/api/messages/mark-as-ad/${id}`,        // POST - 标记为广告
        notAd: (id) => `/api/messages/not-ad/${id}`,               // POST - 标记非广告
        deleteReviewById: (id) => `/api/messages/delete-review/${id}`, // DELETE - 删除审核
        trainTail: (id) => `/api/messages/train-tail/${id}`,       // POST - 训练尾部过滤
        feedback: (id) => `/api/messages/feedback/${id}`,          // POST - 提交反馈
        refilter: (id) => `/api/messages/refilter/${id}`,          // POST - 重新过滤

        // 批量操作
        batchApprove: '/api/messages/batch/approve',               // POST - 批量审核通过
        batchReject: '/api/messages/batch/reject',                 // POST - 批量拒绝
        batchDelete: '/api/messages/batch/delete',                 // POST - 批量删除

        // 重置操作
        resetFailed: '/api/messages/reset-failed',                 // POST - 重置发送失败的消息

        // 统计相关
        stats: '/api/messages/stats/overview'                      // GET - 获取统计概览
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
        sessionStatus: (sessionType) => `/api/dual-auth/session-status/${sessionType}` // GET - 获取Session状态
    },

    // Telegram配置模块 - /api/telegram-config
    telegramConfig: {
        get: '/api/telegram-config',                                    // GET - 获取Telegram配置
        update: '/api/telegram-config'                                  // POST - 更新Telegram配置
    },

    // 训练数据模块 - /api/training
    training: {
        // 分隔符模式管理
        separatorPatterns: '/api/training/separator-patterns',   // GET/POST - 获取/保存分隔符模式
        testSeparator: '/api/training/test-separator',   // POST - 测试分隔符过滤

        // 文本过滤管理
        textFilters: '/api/training/text-filters',               // GET/POST - 获取/添加文本过滤器
        deleteTextFilter: (keyword) => `/api/training/text-filters/${encodeURIComponent(keyword)}`, // DELETE - 删除文本过滤器
        clearTextFilters: '/api/training/text-filters/clear',    // DELETE - 清除所有文本过滤器
        testTextFilter: '/api/training/test-text-filter',        // POST - 测试文本过滤

        // 权重关键词管理系统（新）
        adKeywords: '/api/training/ad-keywords',                  // GET - 获取所有关键词及权重
        addKeyword: '/api/training/ad-keywords',                  // POST - 添加关键词
        updateKeyword: (keyword) => `/api/training/ad-keywords/${encodeURIComponent(keyword)}`, // PUT - 更新关键词权重
        deleteKeyword: (keyword) => `/api/training/ad-keywords/${encodeURIComponent(keyword)}`, // DELETE - 删除关键词
        updateThreshold: '/api/training/ad-keywords/threshold',   // PUT - 更新检测阈值
        keywordStats: '/api/training/ad-keywords/stats',          // GET - 获取关键词统计

        // 广告样本管理（向量）
        adSamples: '/api/training/ad-vectors',                    // GET - 获取广告样本
        addAdSample: '/api/training/ad-vectors',                  // POST - 添加广告样本

        // 尾部过滤样本管理
        tailFilterSamples: '/api/training/tail-filter-samples',  // GET/POST - 获取/添加尾部过滤样本
        tailFilterSampleById: (id) => `/api/training/tail-filter-samples/${id}`, // PUT/DELETE - 更新/删除尾部过滤样本
        tailFilterStatistics: '/api/training/tail-filter-statistics', // GET - 获取尾部过滤统计
        tailFilterHistory: '/api/training/tail-filter-history'    // GET - 获取尾部过滤历史

    },

    // 频道管理模块 - /api/channels
    channels: {
        // 基础管理
        list: '/api/channels/',                                   // GET - 获取所有源频道
        add: '/api/channels/',                                    // POST - 添加源频道
        get: (channel_id) => `/api/channels/${channel_id}`,       // GET - 获取单个频道
        delete: (channel_id) => `/api/channels/${channel_id}`,    // DELETE - 删除源频道

        // 批量操作
        batchAdd: '/api/channels/batch-add',                      // POST - 批量添加源频道

        // 搜索功能
        search: '/api/channels/search',                           // GET - 搜索频道

        // 解析功能
        resolve: '/api/channels/resolve'                          // POST - 解析单个源频道ID
    },

    // 系统状态模块 - /api/system
    system: {
        // 系统健康检查（保留唯一使用的端点）
        health: '/api/health',                                     // GET - 健康检查（主要使用）
        detailedStatus: '/api/system/status-detailed',             // GET - 详细系统状态
        reset: '/api/system/reset'                                 // POST - 重置系统数据
    },

    // 管理功能模块 - /api/admin
    admin: {
        // 配置管理
        config: '/api/admin/config',                               // GET - 获取管理配置
        configForwarding: '/api/admin/config/forwarding',          // POST - 配置转发
        configBatch: '/api/admin/config/batch',                    // POST - 批量配置
        searchChannels: '/api/admin/search-channels'               // GET - 搜索频道（管理功能）
    },

    // 配置管理模块 - /api/config
    config: {
        get: '/api/config',                                        // GET - 获取系统配置
        update: '/api/config'                                      // POST - 更新系统配置
    },

    // 统计模块 - /api/stats
    stats: {
        get: '/api/stats'                                          // GET - 获取统计数据
    },


    // 服务管理模块 - /api/services
    services: {
        status: '/api/services/status',                            // GET - 获取所有服务状态
        statusById: (name) => `/api/services/status/${name}`,      // GET - 获取单个服务状态
        start: (name) => `/api/services/start/${name}`,            // POST - 启动服务
        stop: (name) => `/api/services/stop/${name}`,              // POST - 停止服务
        restart: (name) => `/api/services/restart/${name}`,        // POST - 重启服务
        logs: (name) => `/api/services/logs/${name}`,              // GET - 获取服务日志
        reloadConfig: '/api/services/reload-config',               // POST - 重载配置
        info: '/api/services/info'                                 // GET - 获取Supervisor信息
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
        separatorConfig: '/static/separator-config.html',          // 分隔符配置页面
        textFilter: '/static/text-filter.html',                    // 文本过滤页面
        adVectorManager: '/static/ad-training-samples.html',       // 关键词管理页面
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