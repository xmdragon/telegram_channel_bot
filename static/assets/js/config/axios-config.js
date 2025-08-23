/**
 * Axios全局配置 - 解决页面卡住问题
 * "好代码没有特殊情况" - Linus Torvalds
 * 
 * 核心功能：
 * - 统一超时设置（10秒）
 * - 请求/响应拦截器
 * - 网络错误处理
 * - 加载状态管理
 */

(function() {
    'use strict';
    
    // 等待axios加载完成
    if (typeof axios === 'undefined') {
        console.error('Axios配置错误: axios未加载');
        return;
    }
    
    // ============= 全局默认配置 =============
    axios.defaults.timeout = 10000; // 10秒超时
    axios.defaults.headers.common['Content-Type'] = 'application/json';
    axios.defaults.headers.common['Accept'] = 'application/json';
    
    // 全局加载状态管理
    let activeRequests = 0;
    let loadingTimeout = null;
    
    // ============= 请求拦截器 =============
    axios.interceptors.request.use(
        function(config) {
            activeRequests++;
            
            // 显示全局加载状态（超过500ms的请求）
            if (activeRequests === 1) {
                loadingTimeout = setTimeout(() => {
                    document.body.classList.add('loading');
                }, 500);
            }
            
            return config;
        },
        function(error) {
            activeRequests = Math.max(0, activeRequests - 1);
            hideLoadingIfDone();
            return Promise.reject(error);
        }
    );
    
    // ============= 响应拦截器 =============
    axios.interceptors.response.use(
        function(response) {
            activeRequests = Math.max(0, activeRequests - 1);
            hideLoadingIfDone();
            return response;
        },
        function(error) {
            activeRequests = Math.max(0, activeRequests - 1);
            hideLoadingIfDone();
            
            // 统一错误处理
            handleAxiosError(error);
            return Promise.reject(error);
        }
    );
    
    // ============= 辅助函数 =============
    
    function hideLoadingIfDone() {
        if (activeRequests === 0) {
            if (loadingTimeout) {
                clearTimeout(loadingTimeout);
                loadingTimeout = null;
            }
            document.body.classList.remove('loading');
        }
    }
    
    function handleAxiosError(error) {
        let errorMessage = '网络请求失败';
        
        if (error.code === 'ECONNABORTED' || error.message.includes('timeout')) {
            errorMessage = '请求超时，请检查网络连接';
        } else if (error.response) {
            // 服务器响应错误
            if (error.response.status >= 500) {
                errorMessage = '服务器内部错误';
            } else if (error.response.status === 404) {
                errorMessage = '请求的资源不存在';
            } else if (error.response.status === 403) {
                errorMessage = '没有权限访问';
            } else if (error.response.status === 401) {
                errorMessage = '身份验证失败';
            }
        } else if (error.request) {
            // 网络错误
            errorMessage = '网络连接失败，请检查网络设置';
        }
        
        // 显示错误消息（如果有SimpleUI）
        if (typeof window.SimpleUI !== 'undefined' && window.SimpleUI.showMessage) {
            window.SimpleUI.showMessage(errorMessage, 'error', 5000);
        } else {
            console.error('网络错误:', errorMessage, error);
        }
    }
    
    // ============= 带超时的Promise.all =============
    window.PromiseAllWithTimeout = function(promises, timeout = 15000) {
        return Promise.race([
            Promise.all(promises),
            new Promise((_, reject) => {
                setTimeout(() => reject(new Error('并行请求超时')), timeout);
            })
        ]);
    };
    
    // ============= 页面加载超时检测 =============
    let pageLoadTimeout = null;
    
    function startPageLoadTimeout() {
        pageLoadTimeout = setTimeout(() => {
            if (typeof window.SimpleUI !== 'undefined' && window.SimpleUI.showMessage) {
                window.SimpleUI.showMessage(
                    '页面加载超时，请刷新页面重试', 
                    'error', 
                    10000
                );
            }
            
            // 添加刷新按钮
            addRefreshButton();
        }, 15000); // 15秒后超时
    }
    
    function clearPageLoadTimeout() {
        if (pageLoadTimeout) {
            clearTimeout(pageLoadTimeout);
            pageLoadTimeout = null;
        }
    }
    
    function addRefreshButton() {
        const existingButton = document.getElementById('refresh-button');
        if (existingButton) return;
        
        const button = document.createElement('button');
        button.id = 'refresh-button';
        button.innerHTML = '🔄 刷新页面';
        button.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 10000;
            padding: 10px 20px;
            background: #409eff;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        `;
        
        button.addEventListener('click', () => {
            window.location.reload();
        });
        
        document.body.appendChild(button);
    }
    
    // 暴露全局方法
    window.AxiosConfig = {
        startPageLoadTimeout,
        clearPageLoadTimeout,
        getActiveRequests: () => activeRequests
    };
    
    // 注入CSS样式
    const style = document.createElement('style');
    style.textContent = `
        /* 全局加载状态样式 */
        body.loading {
            cursor: progress !important;
        }
        
        body.loading * {
            cursor: progress !important;
        }
        
        /* 加载遮罩层样式 */
        .loading-overlay {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.3);
            z-index: 9998;
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }
        
        .loading-spinner {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            display: flex;
            align-items: center;
            gap: 12px;
        }
        
        .loading-spinner::before {
            content: '';
            width: 16px;
            height: 16px;
            border: 2px solid #ddd;
            border-top: 2px solid #409eff;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
    `;
    document.head.appendChild(style);
    
    console.log('✅ Axios全局配置已加载 - 10秒超时，15秒页面加载检测');
})();