/**
 * UI兼容层 - 确保平滑过渡，零破坏性
 * "消除特殊情况，让程序正常工作" - Linus Torvalds
 * 
 * 功能：
 * - 自动检测并注入兼容API
 * - 确保Vue组件内的$message正常工作
 * - 处理各种边界情况和异步加载
 * - 提供降级机制
 */

class UIWrapper {
    static initialized = false;
    static retryCount = 0;
    static maxRetries = 10;
    
    /**
     * 主初始化函数
     */
    static init() {
        if (this.initialized) return;
        
        
        try {
            // 1. 注册全局UI对象
            this.setupGlobalAPIs();
            
            // 2. 设置Vue集成
            this.setupVueIntegration();
            
            // 3. 设置Element Plus兼容
            this.setupElementPlusCompatibility();
            
            // 4. 处理现有组件实例
            this.patchExistingInstances();
            
            // 5. 设置错误处理
            this.setupErrorHandling();
            
            this.initialized = true;
            
        } catch (error) {
            console.warn('⚠️ UI兼容层初始化出现问题:', error);
            this.scheduleRetry();
        }
    }
    
    /**
     * 设置全局API
     */
    static setupGlobalAPIs() {
        // 确保SimpleUI存在
        if (!window.SimpleUI) {
            console.warn('⚠️ SimpleUI未找到，使用降级方案');
            this.createFallbackUI();
            return;
        }
        
        // 设置Element Plus兼容API
        if (!window.ElMessage) {
            window.ElMessage = window.SimpleUI.Message;
        }
        
        if (!window.ElMessageBox) {
            window.ElMessageBox = window.SimpleUI.MessageBox;
        }
        
        // 设置ElementPlus命名空间（部分代码可能使用）
        if (!window.ElementPlus) {
            window.ElementPlus = {
                ElMessage: window.ElMessage,
                ElMessageBox: window.ElMessageBox
            };
        }
        
    }
    
    /**
     * 设置Vue集成
     */
    static setupVueIntegration() {
        // 检查Vue是否存在
        if (typeof Vue === 'undefined') {
            return;
        }
        
        // Vue 3集成
        if (Vue.config && Vue.config.globalProperties) {
            this.setupVue3Integration();
        }
        
        // 处理Vue应用实例
        this.patchVueApps();
        
    }
    
    /**
     * Vue 3集成
     */
    static setupVue3Integration() {
        const globalProps = Vue.config.globalProperties;
        
        // 设置全局属性
        globalProps.$message = window.ElMessage;
        globalProps.$confirm = window.ElMessageBox.confirm;
        globalProps.$alert = window.ElMessageBox.alert;
        globalProps.$prompt = window.ElMessageBox.prompt;
        
        // 兼容可能的其他调用方式
        globalProps.$msgbox = window.ElMessageBox;
        globalProps.$messageBox = window.ElMessageBox;
    }
    
    /**
     * 修补Vue应用实例
     */
    static patchVueApps() {
        // 监听新的Vue应用创建
        const originalCreateApp = Vue.createApp;
        if (originalCreateApp) {
            Vue.createApp = function(...args) {
                const app = originalCreateApp.apply(this, args);
                
                // 为新应用设置全局属性
                app.config.globalProperties.$message = window.ElMessage;
                app.config.globalProperties.$confirm = window.ElMessageBox.confirm;
                app.config.globalProperties.$alert = window.ElMessageBox.alert;
                app.config.globalProperties.$prompt = window.ElMessageBox.prompt;
                
                return app;
            };
        }
        
        // 处理已存在的应用
        this.patchExistingVueInstances();
    }
    
    /**
     * 修补现有Vue实例
     */
    static patchExistingVueInstances() {
        // 寻找可能的Vue实例
        const possibleApps = ['app', 'vueApp', 'application'];
        
        possibleApps.forEach(name => {
            if (window[name] && window[name].config) {
                const globalProps = window[name].config.globalProperties;
                if (globalProps) {
                    globalProps.$message = window.ElMessage;
                    globalProps.$confirm = window.ElMessageBox.confirm;
                    globalProps.$alert = window.ElMessageBox.alert;
                    globalProps.$prompt = window.ElMessageBox.prompt;
                }
            }
        });
    }
    
    /**
     * Element Plus兼容性设置
     */
    static setupElementPlusCompatibility() {
        // 处理可能的Element Plus残留引用
        if (window.ElementPlus && !window.ElementPlus.ElMessage) {
            window.ElementPlus.ElMessage = window.ElMessage;
            window.ElementPlus.ElMessageBox = window.ElMessageBox;
        }
        
        // 处理解构赋值（常见模式）
        this.handleDestructuringPatterns();
    }
    
    /**
     * 处理解构赋值模式
     */
    static handleDestructuringPatterns() {
        // 监听可能的解构赋值
        const originalElementPlus = window.ElementPlus;
        
        Object.defineProperty(window, 'ElementPlus', {
            get() {
                return {
                    ElMessage: window.ElMessage,
                    ElMessageBox: window.ElMessageBox,
                    // 其他可能需要的属性
                    ...originalElementPlus
                };
            },
            set(value) {
                // 允许设置，但保持我们的覆盖
                Object.assign(value, {
                    ElMessage: window.ElMessage,
                    ElMessageBox: window.ElMessageBox
                });
                return value;
            }
        });
    }
    
    /**
     * 修补现有组件实例 (简化版)
     */
    static patchExistingInstances() {
        // 简化的实例修补，避免复杂DOM查询
        try {
            const appElement = document.getElementById('app');
            if (appElement && appElement.__vue__) {
                // Vue 2实例
                appElement.__vue__.$message = window.ElMessage;
                appElement.__vue__.$confirm = window.ElMessageBox.confirm;
            }
        } catch (error) {
            console.warn('🔧 Vue实例修补跳过:', error.message);
        }
    }
    
    /**
     * 创建降级UI（在SimpleUI不可用时）
     */
    static createFallbackUI() {
        
        window.ElMessage = {
            success: (msg) => this.showNativeMessage(msg, 'success'),
            error: (msg) => this.showNativeMessage(msg, 'error'),
            warning: (msg) => this.showNativeMessage(msg, 'warning'),
            info: (msg) => this.showNativeMessage(msg, 'info')
        };
        
        window.ElMessageBox = {
            confirm: (message, title) => {
                return new Promise((resolve, reject) => {
                    const result = window.confirm(`${title || '确认'}\\n\\n${message}`);
                    if (result) {
                        resolve();
                    } else {
                        reject('cancel');
                    }
                });
            },
            alert: (message, title) => {
                window.alert(`${title || '提示'}\\n\\n${message}`);
                return Promise.resolve();
            }
        };
    }
    
    /**
     * 显示原生消息（降级方案）
     */
    static showNativeMessage(message, type) {
        const prefix = {
            success: '✅',
            error: '❌', 
            warning: '⚠️',
            info: 'ℹ️'
        };
        
        
        // 尝试使用原生通知
        if ('Notification' in window && Notification.permission === 'granted') {
            new Notification(message, {
                icon: '/favicon.ico'
            });
        } else {
            // 最后的降级：使用alert
            window.alert(`${prefix[type]} ${message}`);
        }
    }
    
    /**
     * 错误处理设置
     */
    static setupErrorHandling() {
        // 捕获可能的UI调用错误
        const originalError = window.onerror;
        
        window.onerror = (message, source, lineno, colno, error) => {
            if (message.includes('ElMessage') || message.includes('$message')) {
                console.warn('🔧 检测到UI调用错误，尝试修复:', message);
                this.handleUIError(error);
            }
            
            if (originalError) {
                return originalError(message, source, lineno, colno, error);
            }
        };
        
        // 捕获Promise错误
        window.addEventListener('unhandledrejection', (event) => {
            if (event.reason && event.reason.toString().includes('ElMessage')) {
                console.warn('🔧 检测到UI Promise错误，尝试修复');
                this.handleUIError(event.reason);
            }
        });
    }
    
    /**
     * 处理UI相关错误
     */
    static handleUIError(error) {
        
        // 重新初始化
        this.initialized = false;
        setTimeout(() => {
            this.init();
        }, 100);
    }
    
    /**
     * 重试机制
     */
    static scheduleRetry() {
        if (this.retryCount >= this.maxRetries) {
            console.error('❌ UI兼容层初始化失败，已达到最大重试次数');
            this.createFallbackUI();
            return;
        }
        
        this.retryCount++;
        const delay = Math.min(1000 * this.retryCount, 5000);
        
        
        setTimeout(() => {
            this.init();
        }, delay);
    }
    
    /**
     * 手动初始化接口
     */
    static forceInit() {
        this.initialized = false;
        this.retryCount = 0;
        this.init();
    }
    
    /**
     * 检查状态
     */
    static getStatus() {
        return {
            initialized: this.initialized,
            retryCount: this.retryCount,
            hasSimpleUI: !!window.SimpleUI,
            hasElMessage: !!window.ElMessage,
            hasElMessageBox: !!window.ElMessageBox,
            hasVue: typeof Vue !== 'undefined'
        };
    }
}

// ============= 自动初始化 =============
// 多种初始化时机
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => UIWrapper.init());
} else {
    // 页面已加载完成
    setTimeout(() => UIWrapper.init(), 0);
}

// 确保在SimpleUI加载后初始化
if (window.SimpleUI) {
    UIWrapper.init();
} else {
    // 轮询等待SimpleUI
    let checkCount = 0;
    const checkInterval = setInterval(() => {
        if (window.SimpleUI || checkCount > 50) {
            clearInterval(checkInterval);
            UIWrapper.init();
        }
        checkCount++;
    }, 100);
}

// 导出到全局
window.UIWrapper = UIWrapper;

// 调试信息

// ES模块支持
if (typeof module !== 'undefined' && module.exports) {
    module.exports = UIWrapper;
}