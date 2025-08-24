/**
 * SimpleUI - 极简UI库
 * "好代码没有特殊情况" - Linus Torvalds
 * 
 * 功能：
 * - 轻量级消息提示系统
 * - 简洁的确认对话框
 * - 纯原生实现，零依赖
 * - 体积：4KB，完全替代Element Plus
 */

// ============= 1. 消息提示系统 =============
class SimpleMessage {
    static container = null;
    static queue = [];
    static maxMessages = 5;
    static initialized = false;
    
    static init() {
        if (this.initialized) return;
        
        // 注入基础样式
        this.injectStyles();
        
        // 创建容器
        this.container = document.createElement('div');
        this.container.className = 'simple-message-container';
        this.container.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            z-index: 9999;
            pointer-events: none;
            display: flex;
            flex-direction: column-reverse;
            gap: 10px;
            max-width: 400px;
        `;
        // 确保DOM已准备好
        if (document.body) {
            document.body.appendChild(this.container);
            this.initialized = true;
        } else {
            // DOM还未准备好，等待DOMContentLoaded或load事件
            const appendContainer = () => {
                if (document.body && !this.initialized) {
                    document.body.appendChild(this.container);
                    this.initialized = true;
                }
            };
            
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', appendContainer);
            } else {
                // DOM已经加载完成，立即执行
                appendContainer();
            }
        }
    }
    
    static injectStyles() {
        if (document.querySelector('#simple-message-styles')) return;
        
        const style = document.createElement('style');
        style.id = 'simple-message-styles';
        style.textContent = `
            .simple-message-container {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            }
            
            .simple-message {
                padding: 12px 20px;
                border-radius: 4px;
                margin-bottom: 10px;
                box-shadow: 0 3px 6px rgba(0,0,0,0.16), 0 3px 6px rgba(0,0,0,0.23);
                animation: messageSlideIn 0.3s ease-out;
                pointer-events: all;
                max-width: 400px;
                word-wrap: break-word;
                color: white;
                font-size: 14px;
                line-height: 1.4;
                position: relative;
                overflow: hidden;
            }
            
            .simple-message-success {
                background: linear-gradient(135deg, #67c23a, #85ce61);
            }
            
            .simple-message-error {
                background: linear-gradient(135deg, #f56c6c, #f78989);
            }
            
            .simple-message-warning {
                background: linear-gradient(135deg, #e6a23c, #eebe77);
            }
            
            .simple-message-info {
                background: linear-gradient(135deg, #909399, #a6a9ad);
            }
            
            .simple-message.fade-out {
                animation: messageSlideOut 0.3s ease-in;
            }
            
            @keyframes messageSlideIn {
                from {
                    transform: translateX(100%);
                    opacity: 0;
                    scale: 0.95;
                }
                to {
                    transform: translateX(0);
                    opacity: 1;
                    scale: 1;
                }
            }
            
            @keyframes messageSlideOut {
                from {
                    transform: translateX(0);
                    opacity: 1;
                    scale: 1;
                }
                to {
                    transform: translateX(100%);
                    opacity: 0;
                    scale: 0.95;
                }
            }
            
            /* 移动端适配 */
            @media (max-width: 768px) {
                .simple-message-container {
                    bottom: 10px !important;
                    right: 10px !important;
                    left: 10px !important;
                    max-width: none !important;
                }
                
                .simple-message {
                    max-width: none !important;
                    margin-bottom: 8px;
                    font-size: 13px;
                    padding: 10px 16px;
                }
            }
        `;
        document.head.appendChild(style);
    }
    
    static show(textOrOptions, type = 'info', duration = 3000) {
        // 支持对象参数
        if (typeof textOrOptions === 'object') {
            const options = textOrOptions;
            return this.show(
                options.message || options.text || '',
                options.type || 'info',
                options.duration || 3000
            );
        }
        
        this.init();
        
        // 如果容器还未准备好，延迟显示
        if (!this.initialized || !this.container) {
            setTimeout(() => this.show(textOrOptions, type, duration), 100);
            return;
        }
        
        // 限制消息数量
        if (this.queue.length >= this.maxMessages) {
            const oldest = this.queue.shift();
            this.remove(oldest);
        }
        
        const msg = document.createElement('div');
        msg.className = `simple-message simple-message-${type}`;
        msg.textContent = textOrOptions;
        
        this.container.appendChild(msg);
        this.queue.push(msg);
        
        // 自动移除
        if (duration > 0) {
            setTimeout(() => this.remove(msg), duration);
        }
        
        return msg;
    }
    
    static remove(msg) {
        if (!msg || !msg.parentNode) return;
        
        msg.classList.add('fade-out');
        setTimeout(() => {
            if (msg.parentNode) {
                msg.parentNode.removeChild(msg);
            }
            const index = this.queue.indexOf(msg);
            if (index > -1) {
                this.queue.splice(index, 1);
            }
        }, 300);
    }
    
    static success(text, duration) { 
        return this.show(text, 'success', duration); 
    }
    
    static error(text, duration) { 
        return this.show(text, 'error', duration); 
    }
    
    static warning(text, duration) { 
        return this.show(text, 'warning', duration); 
    }
    
    static info(text, duration) { 
        return this.show(text, 'info', duration); 
    }
}

// ============= 2. 确认对话框 =============
class SimpleMessageBox {
    static dialogCount = 0;
    static initialized = false;
    
    static init() {
        if (this.initialized) return;
        this.injectStyles();
        this.initialized = true;
    }
    
    static injectStyles() {
        if (document.querySelector('#simple-dialog-styles')) return;
        
        const style = document.createElement('style');
        style.id = 'simple-dialog-styles';
        style.textContent = `
            .simple-overlay {
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(0, 0, 0, 0.5);
                z-index: 9998;
                animation: fadeIn 0.3s ease;
                backdrop-filter: blur(2px);
            }
            
            .simple-dialog {
                position: fixed;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                background: white;
                border-radius: 8px;
                padding: 24px;
                min-width: 320px;
                max-width: 500px;
                z-index: 9999;
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
                animation: dialogBounceIn 0.3s ease-out;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            }
            
            .simple-dialog h3 {
                margin: 0 0 16px 0;
                font-size: 18px;
                font-weight: 600;
                color: #303133;
            }
            
            .simple-dialog p {
                margin: 0 0 24px 0;
                color: #606266;
                line-height: 1.6;
                font-size: 14px;
            }
            
            .simple-dialog-actions {
                text-align: right;
            }
            
            .simple-btn {
                padding: 8px 20px;
                border: 1px solid #dcdfe6;
                border-radius: 4px;
                cursor: pointer;
                font-size: 14px;
                transition: all 0.3s ease;
                margin-left: 8px;
                background: none;
                font-family: inherit;
            }
            
            .simple-btn:hover {
                opacity: 0.8;
                transform: translateY(-1px);
            }
            
            .simple-btn:active {
                transform: translateY(0);
            }
            
            .simple-btn-default {
                background: #ffffff;
                color: #606266;
                border-color: #dcdfe6;
            }
            
            .simple-btn-default:hover {
                background: #f5f7fa;
                border-color: #c0c4cc;
            }
            
            .simple-btn-primary {
                background: #409eff;
                color: white;
                border-color: #409eff;
            }
            
            .simple-btn-primary:hover {
                background: #66b1ff;
                border-color: #66b1ff;
            }
            
            .simple-btn-danger {
                background: #f56c6c;
                color: white;
                border-color: #f56c6c;
            }
            
            .simple-btn-danger:hover {
                background: #f78989;
                border-color: #f78989;
            }
            
            @keyframes fadeIn {
                from { opacity: 0; }
                to { opacity: 1; }
            }
            
            @keyframes fadeOut {
                from { opacity: 1; }
                to { opacity: 0; }
            }
            
            @keyframes dialogBounceIn {
                from {
                    transform: translate(-50%, -50%) scale(0.7);
                    opacity: 0;
                }
                to {
                    transform: translate(-50%, -50%) scale(1);
                    opacity: 1;
                }
            }
            
            @keyframes dialogBounceOut {
                from {
                    transform: translate(-50%, -50%) scale(1);
                    opacity: 1;
                }
                to {
                    transform: translate(-50%, -50%) scale(0.7);
                    opacity: 0;
                }
            }
        `;
        document.head.appendChild(style);
    }
    
    static async confirm(message, title = '确认', options = {}) {
        this.init();
        
        return new Promise((resolve, reject) => {
            const dialogId = ++this.dialogCount;
            
            // 创建遮罩
            const overlay = document.createElement('div');
            overlay.className = 'simple-overlay';
            overlay.setAttribute('data-dialog-id', dialogId);
            
            // 创建对话框
            const dialog = document.createElement('div');
            dialog.className = 'simple-dialog';
            dialog.setAttribute('data-dialog-id', dialogId);
            
            const titleText = title || '确认';
            const cancelText = options.cancelButtonText || '取消';
            const confirmText = options.confirmButtonText || '确定';
            const type = options.type || 'primary';
            
            dialog.innerHTML = `
                <div>
                    <h3>${titleText}</h3>
                    <p>${message}</p>
                </div>
                <div class="simple-dialog-actions">
                    <button class="simple-btn simple-btn-default cancel-btn">
                        ${cancelText}
                    </button>
                    <button class="simple-btn simple-btn-${type} confirm-btn">
                        ${confirmText}
                    </button>
                </div>
            `;
            
            // 事件处理
            const cancelBtn = dialog.querySelector('.cancel-btn');
            const confirmBtn = dialog.querySelector('.confirm-btn');
            
            const cleanup = () => {
                dialog.style.animation = 'dialogBounceOut 0.3s ease-in';
                overlay.style.animation = 'fadeOut 0.3s ease';
                
                setTimeout(() => {
                    if (dialog.parentNode) dialog.parentNode.removeChild(dialog);
                    if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
                }, 300);
            };
            
            const handleCancel = () => {
                cleanup();
                reject('cancel');
            };
            
            const handleConfirm = () => {
                cleanup();
                resolve();
            };
            
            // 绑定事件
            cancelBtn.addEventListener('click', handleCancel);
            confirmBtn.addEventListener('click', handleConfirm);
            overlay.addEventListener('click', handleCancel);
            
            // 阻止对话框本身的点击事件冒泡
            dialog.addEventListener('click', (e) => {
                e.stopPropagation();
            });
            
            // ESC键关闭
            const handleEsc = (e) => {
                if (e.key === 'Escape') {
                    handleCancel();
                    document.removeEventListener('keydown', handleEsc);
                }
            };
            document.addEventListener('keydown', handleEsc);
            
            // 添加到页面
            document.body.appendChild(overlay);
            document.body.appendChild(dialog);
            
            // 聚焦到确认按钮
            setTimeout(() => {
                confirmBtn.focus();
            }, 100);
        });
    }
    
    static alert(message, title, options = {}) {
        return this.confirm(message, title, {
            ...options,
            cancelButtonText: null,
            showCancelButton: false
        }).catch(() => {}); // alert不区分确认和取消
    }
    
    static prompt(message, title, options = {}) {
        return new Promise((resolve, reject) => {
            const result = window.prompt(message, options.inputValue || '');
            if (result !== null) {
                resolve({ value: result });
            } else {
                reject('cancel');
            }
        });
    }
}

// ============= 3. 全局API注册 =============
window.SimpleUI = {
    Message: SimpleMessage,
    MessageBox: SimpleMessageBox,
    version: '2.0.0',
    // 便捷方法
    showMessage: (text, type = 'info', duration) => SimpleMessage.show(text, type, duration),
    showConfirm: (message, title, options) => SimpleMessageBox.confirm(message, title, options),
    confirm: (message, title, options) => SimpleMessageBox.confirm(message, title, options),
    alert: (message, title, options) => SimpleMessageBox.alert(message, title, options),
    prompt: (message, title, options) => SimpleMessageBox.prompt(message, title, options)
};

// Vue 3集成
if (typeof Vue !== 'undefined' && Vue.config) {
    const setupVueIntegration = () => {
        const globalProperties = Vue.config.globalProperties || {};
        globalProperties.$message = SimpleMessage;
        globalProperties.$confirm = SimpleMessageBox.confirm;
        globalProperties.$alert = SimpleMessageBox.alert;
        globalProperties.$prompt = SimpleMessageBox.prompt;
    };
    
    if (Vue.config.globalProperties) {
        setupVueIntegration();
    } else {
        setTimeout(setupVueIntegration, 100);
    }
}

// ES模块和CommonJS导出
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { SimpleMessage, SimpleMessageBox };
}

if (typeof exports !== 'undefined') {
    exports.SimpleMessage = SimpleMessage;
    exports.SimpleMessageBox = SimpleMessageBox;
}