/**
 * API客户端模块 - 集中管理所有API调用
 * 遵循Linus"好品味"原则：简化边界情况，统一错误处理
 */

const ApiClient = {
    // 基础请求配置
    config: {
        timeout: 30000,
        retries: 3,
        retryDelay: 1000
    },
    
    // 通用请求方法
    async request(method, url, data = null, options = {}) {
        const { timeout = this.config.timeout, retries = this.config.retries } = options;
        
        for (let attempt = 0; attempt <= retries; attempt++) {
            try {
                // 🔧 修复认证问题：保留axios默认headers，不要覆盖认证信息
                const config = {
                    method,
                    timeout,
                    ...options,
                    // 确保保留默认的认证头
                    headers: {
                        ...axios.defaults.headers.common,
                        ...options.headers
                    }
                };
                
                let response;
                if (method.toLowerCase() === 'get') {
                    response = await axios.get(url, { ...config, params: data });
                } else {
                    response = await axios[method.toLowerCase()](url, data, config);
                }
                
                return this.handleResponse(response);
                
            } catch (error) {
                if (attempt === retries) {
                    throw this.handleError(error);
                }
                
                // 指数退避重试
                await this.delay(this.config.retryDelay * Math.pow(2, attempt));
            }
        }
    },
    
    // 响应处理
    handleResponse(response) {
        if (response.data) {
            return {
                success: true,
                data: response.data,
                status: response.status
            };
        }
        
        throw new Error('空响应数据');
    },
    
    // 错误处理
    handleError(error) {
        const errorInfo = {
            success: false,
            error: error.message || '请求失败',
            status: error.response?.status || 0,
            details: error.response?.data || null
        };
        
        // 根据HTTP状态码提供友好错误信息
        if (error.response?.status) {
            switch (error.response.status) {
                case 400:
                    errorInfo.error = '请求参数错误';
                    break;
                case 401:
                    errorInfo.error = '未授权访问';
                    break;
                case 403:
                    errorInfo.error = '权限不足';
                    break;
                case 404:
                    errorInfo.error = '资源不存在';
                    break;
                case 429:
                    errorInfo.error = '请求过于频繁';
                    break;
                case 500:
                    errorInfo.error = '服务器内部错误';
                    break;
                case 502:
                    errorInfo.error = '网关错误';
                    break;
                case 503:
                    errorInfo.error = '服务暂时不可用';
                    break;
            }
        }
        
        return errorInfo;
    },
    
    // 延迟工具
    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    },
    
    // 消息相关API
    messages: {
        // 获取消息列表
        async list(params = {}) {
            // 确保API端点可用
            if (!window.API?.messages?.list) {
                throw new Error('API配置未加载');
            }
            
            // 标准化参数
            const standardParams = {
                page: params.page || 1,
                size: params.size || 20,
                ...params
            };
            
            // 过滤空值
            Object.keys(standardParams).forEach(key => {
                if (standardParams[key] === '' || standardParams[key] === null || standardParams[key] === undefined) {
                    delete standardParams[key];
                }
            });
            
            return await ApiClient.request('get', window.API.messages.list, standardParams);
        },
        
        // 审核单个消息
        async approve(messageId) {
            if (!messageId) throw new Error('消息ID不能为空');
            if (!window.API?.messages?.approveById) throw new Error('API配置未加载');
            
            return await ApiClient.request('post', window.API.messages.approveById(messageId));
        },
        
        // 拒绝单个消息
        async reject(messageId) {
            if (!messageId) throw new Error('消息ID不能为空');
            if (!window.API?.messages?.rejectById) throw new Error('API配置未加载');
            
            return await ApiClient.request('post', window.API.messages.rejectById(messageId));
        },
        
        // 批量审核
        async batchApprove(messageIds) {
            if (!Array.isArray(messageIds) || messageIds.length === 0) {
                throw new Error('请选择要审核的消息');
            }
            if (!window.API?.messages?.batchApprove) throw new Error('API配置未加载');
            
            return await ApiClient.request('post', window.API.messages.batchApprove, {
                message_ids: messageIds
            });
        },
        
        // 批量拒绝
        async batchReject(messageIds) {
            if (!Array.isArray(messageIds) || messageIds.length === 0) {
                throw new Error('请选择要拒绝的消息');
            }
            if (!window.API?.messages?.batchReject) throw new Error('API配置未加载');
            
            return await ApiClient.request('post', window.API.messages.batchReject, {
                message_ids: messageIds
            });
        },
        
        // 批量删除
        async batchDelete(messageIds) {
            if (!Array.isArray(messageIds) || messageIds.length === 0) {
                throw new Error('请选择要删除的消息');
            }
            if (!window.API?.messages?.batchDelete) throw new Error('API配置未加载');
            
            return await ApiClient.request('post', window.API.messages.batchDelete, {
                message_ids: messageIds
            });
        },
        
        // 编辑消息内容
        async updateContent(messageId, content) {
            if (!messageId) throw new Error('消息ID不能为空');
            if (!window.API?.messages?.updateById) throw new Error('API配置未加载');
            
            return await ApiClient.request('put', window.API.messages.updateById(messageId), {
                filtered_content: content
            });
        },
        
        // 重新抓取媒体
        async refetchMedia(messageId) {
            if (!messageId) throw new Error('消息ID不能为空');
            if (!window.API?.messages?.refetchMedia) throw new Error('API配置未加载');
            
            return await ApiClient.request('post', window.API.messages.refetchMedia(messageId));
        }
    },
    
    // 统计相关API
    stats: {
        async get() {
            if (!window.API?.stats?.get) throw new Error('API配置未加载');
            return await ApiClient.request('get', window.API.stats.get);
        }
    },
    
    // 配置相关API
    config: {
        async get() {
            if (!window.API?.config?.get) throw new Error('API配置未加载');
            return await ApiClient.request('get', window.API.config.get);
        },
        
        async update(configData) {
            if (!window.API?.config?.update) throw new Error('API配置未加载');
            return await ApiClient.request('post', window.API.config.update, configData);
        }
    },
    
    // 频道相关API
    channels: {
        async list() {
            if (!window.API?.channels?.list) throw new Error('API配置未加载');
            return await ApiClient.request('get', window.API.channels.list);
        }
    },
    
    // 训练数据相关API
    training: {
        async getAdSamples(limit = 100) {
            if (!window.API?.training?.adSamples) throw new Error('API配置未加载');
            return await ApiClient.request('get', window.API.training.adSamples, { limit });
        },
        
        async addAdSample(content) {
            if (!content || !content.trim()) throw new Error('训练内容不能为空');
            if (!window.API?.training?.addAdSample) throw new Error('API配置未加载');
            
            return await ApiClient.request('post', window.API.training.addAdSample, {
                content: content.trim()
            });
        }
    },
    
    // 系统相关API
    system: {
        async health() {
            if (!window.API?.system?.health) throw new Error('API配置未加载');
            return await ApiClient.request('get', window.API.system.health);
        },
        
        async status() {
            if (!window.API?.system?.status) throw new Error('API配置未加载');
            return await ApiClient.request('get', window.API.system.status);
        }
    },
    
    // 批量操作辅助
    async batchOperation(operation, items, batchSize = 10) {
        if (!Array.isArray(items) || items.length === 0) {
            return { success: true, results: [] };
        }
        
        const results = [];
        
        // 分批处理，避免过大的请求
        for (let i = 0; i < items.length; i += batchSize) {
            const batch = items.slice(i, i + batchSize);
            
            try {
                const result = await operation(batch);
                results.push(result);
            } catch (error) {
                results.push(this.handleError(error));
            }
        }
        
        return {
            success: results.every(r => r.success),
            results
        };
    },
    
    // 请求拦截器
    interceptRequest(config) {
        // 添加认证头
        if (window.authToken) {
            config.headers = config.headers || {};
            config.headers.Authorization = `Bearer ${window.authToken}`;
        }
        
        return config;
    },
    
    // 响应拦截器
    interceptResponse(response) {
        // 统一处理时间戳格式
        if (response.data && typeof response.data === 'object') {
            ApiClient.normalizeTimestamps(response.data);
        }
        
        return response;
    },
    
    // 标准化时间戳
    normalizeTimestamps(obj) {
        if (Array.isArray(obj)) {
            obj.forEach(item => ApiClient.normalizeTimestamps(item));
        } else if (obj && typeof obj === 'object') {
            Object.keys(obj).forEach(key => {
                if (key.includes('time') || key.includes('date') || key.includes('created') || key.includes('updated')) {
                    if (typeof obj[key] === 'string' && !obj[key].endsWith('Z') && obj[key].includes('T')) {
                        obj[key] = obj[key] + 'Z'; // 确保UTC时间格式
                    }
                }
                
                if (typeof obj[key] === 'object') {
                    ApiClient.normalizeTimestamps(obj[key]);
                }
            });
        }
    }
};

// 设置axios拦截器（如果axios可用）
if (typeof axios !== 'undefined') {
    axios.interceptors.request.use(config => ApiClient.interceptRequest(config));
    axios.interceptors.response.use(response => ApiClient.interceptResponse(response));
}

// 导出模块
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ApiClient;
} else {
    window.ApiClient = ApiClient;
}