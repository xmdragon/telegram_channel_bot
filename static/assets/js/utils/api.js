/**
 * API通用工具类
 * 统一处理API请求和响应
 */
class ApiClient {
    constructor(baseURL = '') {
        this.baseURL = baseURL;
        this.axios = axios;
    }

    // 通用GET请求
    async get(url, config = {}) {
        try {
            const response = await this.axios.get(`${this.baseURL}${url}`, config);
            return this._handleResponse(response);
        } catch (error) {
            return this._handleError(error);
        }
    }

    // 通用POST请求
    async post(url, data = {}, config = {}) {
        try {
            const response = await this.axios.post(`${this.baseURL}${url}`, data, config);
            return this._handleResponse(response);
        } catch (error) {
            return this._handleError(error);
        }
    }

    // 通用PUT请求
    async put(url, data = {}, config = {}) {
        try {
            const response = await this.axios.put(`${this.baseURL}${url}`, data, config);
            return this._handleResponse(response);
        } catch (error) {
            return this._handleError(error);
        }
    }

    // 通用DELETE请求
    async delete(url, config = {}) {
        try {
            const response = await this.axios.delete(`${this.baseURL}${url}`, config);
            return this._handleResponse(response);
        } catch (error) {
            return this._handleError(error);
        }
    }

    // 处理响应
    _handleResponse(response) {
        if (response.data.success !== false) {
            return {
                success: true,
                data: response.data
            };
        } else {
            return {
                success: false,
                message: response.data.message || '请求失败'
            };
        }
    }

    // 处理错误
    _handleError(error) {
        let message = '网络错误';
        if (error.response) {
            message = error.response.data?.message || error.response.data?.detail || `HTTP ${error.response.status}`;
        } else if (error.message) {
            message = error.message;
        }
        
        return {
            success: false,
            message: message
        };
    }
}

// 全局API客户端实例
window.apiClient = new ApiClient('/api');