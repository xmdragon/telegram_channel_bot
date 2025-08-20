/**
 * 事件冒泡修复验证测试脚本
 * 测试三重事件阻止机制的有效性
 * 
 * 用法：在浏览器控制台中执行此脚本
 * 1. 打开 http://localhost:8000/static/index.html
 * 2. 进入消息管理页面
 * 3. 在控制台中运行此脚本
 */

class EventBubbleVerificationTest {
    constructor() {
        this.testResults = [];
        this.originalConsoleLog = console.log;
        this.eventLog = [];
        this.isVueApp = false;
        
        // 检测Vue应用
        this.detectVueApp();
        
        // 设置事件监听拦截
        this.setupEventInterception();
    }
    
    /**
     * 检测Vue应用是否存在
     */
    detectVueApp() {
        const vueApp = document.querySelector('#app');
        if (vueApp && vueApp.__vue__) {
            this.isVueApp = true;
            this.vueInstance = vueApp.__vue__;
            console.log('✅ Vue应用已检测到');
        } else {
            console.warn('❌ 未检测到Vue应用');
        }
    }
    
    /**
     * 设置事件拦截，监控所有DOM事件
     */
    setupEventInterception() {
        // 重写addEventListener来监控事件注册
        const originalAddEventListener = Element.prototype.addEventListener;
        const self = this;
        
        Element.prototype.addEventListener = function(type, listener, options) {
            if (type === 'click' && this.tagName === 'BUTTON') {
                // 包装点击监听器，记录事件传播情况
                const wrappedListener = function(event) {
                    self.eventLog.push({
                        type: 'click',
                        element: this,
                        target: event.target,
                        currentTarget: event.currentTarget,
                        bubbles: event.bubbles,
                        timestamp: Date.now(),
                        propagationStopped: false,
                        immediatePropagationStopped: false,
                        defaultPrevented: event.defaultPrevented
                    });
                    
                    // 监控事件方法调用
                    self.wrapEventMethods(event);
                    
                    return listener.call(this, event);
                };
                return originalAddEventListener.call(this, type, wrappedListener, options);
            }
            return originalAddEventListener.call(this, type, listener, options);
        };
    }
    
    /**
     * 包装事件方法以监控调用
     */
    wrapEventMethods(event) {
        const originalStopPropagation = event.stopPropagation;
        const originalStopImmediatePropagation = event.stopImmediatePropagation;
        const originalPreventDefault = event.preventDefault;
        const self = this;
        
        event.stopPropagation = function() {
            self.eventLog[self.eventLog.length - 1].propagationStopped = true;
            return originalStopPropagation.call(this);
        };
        
        event.stopImmediatePropagation = function() {
            self.eventLog[self.eventLog.length - 1].immediatePropagationStopped = true;
            return originalStopImmediatePropagation.call(this);
        };
        
        event.preventDefault = function() {
            self.eventLog[self.eventLog.length - 1].defaultPrevented = true;
            return originalPreventDefault.call(this);
        };
    }
    
    /**
     * 主验证测试套件
     */
    async runFullVerification() {
        console.log('🚀 开始事件冒泡修复验证测试...\n');
        
        try {
            // 清理之前的事件日志
            this.eventLog = [];
            
            // 1. DOM结构验证
            await this.verifyDOMStructure();
            
            // 2. 按钮事件绑定验证
            await this.verifyButtonEventBindings();
            
            // 3. 事件处理器验证
            await this.verifyEventHandlers();
            
            // 4. 实际点击测试
            await this.performClickTests();
            
            // 5. Vue响应性验证
            await this.verifyVueReactivity();
            
            // 6. WebSocket连接测试
            await this.verifyWebSocketIntegrity();
            
            // 输出最终报告
            this.generateReport();
            
        } catch (error) {
            console.error('❌ 验证测试出错:', error);
            this.testResults.push({
                test: 'Overall Test',
                status: 'error',
                error: error.message
            });
        }
    }
    
    /**
     * 验证DOM结构是否正确
     */
    async verifyDOMStructure() {
        console.log('📋 1. DOM结构验证...');
        
        const messageCards = document.querySelectorAll('.message-card, .message-item, [class*="message"]');
        const buttons = document.querySelectorAll('button[class*="btn"]');
        const vueApp = document.querySelector('#app');
        
        this.testResults.push({
            test: 'DOM Structure',
            status: messageCards.length > 0 && buttons.length > 0 ? 'pass' : 'fail',
            details: {
                messageCards: messageCards.length,
                buttons: buttons.length,
                vueApp: !!vueApp
            }
        });
        
        console.log(`   消息卡片: ${messageCards.length}个`);
        console.log(`   按钮数量: ${buttons.length}个`);
    }
    
    /**
     * 验证按钮事件绑定
     */
    async verifyButtonEventBindings() {
        console.log('🎯 2. 按钮事件绑定验证...');
        
        const criticalButtons = [
            '.btn-success', // 发布按钮
            '.btn-danger',  // 拒绝按钮
            '.btn-warning', // 广告按钮
            '.btn-info',    // 尾部按钮
            '.btn-primary', // 过滤按钮
            '.batch-action-btn' // 批量操作按钮
        ];
        
        let bindingResults = {};
        
        for (const selector of criticalButtons) {
            const buttons = document.querySelectorAll(selector);
            bindingResults[selector] = {
                found: buttons.length,
                hasVueBinding: false
            };
            
            buttons.forEach(btn => {
                // 检查是否有Vue事件绑定 (@click)
                if (btn.getAttribute('data-v-') || btn.__vueParentComponent) {
                    bindingResults[selector].hasVueBinding = true;
                }
            });
        }
        
        this.testResults.push({
            test: 'Button Event Bindings',
            status: 'info',
            details: bindingResults
        });
        
        console.log('   事件绑定状态:', bindingResults);
    }
    
    /**
     * 验证事件处理器是否包含三重阻止机制
     */
    async verifyEventHandlers() {
        console.log('⚡ 3. 事件处理器验证...');
        
        // 检查是否存在关键的方法
        const criticalMethods = [
            'approveMessage',
            'rejectMessage', 
            'markAsAd',
            'trainTail',
            'filterTail',
            'approveMessages', // 批量发布
            'rejectMessages'   // 批量拒绝
        ];
        
        let methodVerification = {};
        
        // 检查Vue实例中的方法
        if (this.vueInstance) {
            for (const method of criticalMethods) {
                if (typeof this.vueInstance[method] === 'function') {
                    methodVerification[method] = 'found';
                    
                    // 尝试检查方法源码是否包含三重阻止
                    try {
                        const methodSource = this.vueInstance[method].toString();
                        const hasPreventDefault = methodSource.includes('preventDefault');
                        const hasStopPropagation = methodSource.includes('stopPropagation');
                        const hasStopImmediate = methodSource.includes('stopImmediatePropagation');
                        
                        methodVerification[method] = {
                            status: 'found',
                            hasTripleStop: hasPreventDefault && hasStopPropagation && hasStopImmediate,
                            preventDefault: hasPreventDefault,
                            stopPropagation: hasStopPropagation,
                            stopImmediatePropagation: hasStopImmediate
                        };
                    } catch (e) {
                        methodVerification[method] = { status: 'found', verification: 'unable' };
                    }
                } else {
                    methodVerification[method] = 'not_found';
                }
            }
        }
        
        this.testResults.push({
            test: 'Event Handler Verification',
            status: 'info',
            details: methodVerification
        });
        
        console.log('   方法验证结果:', methodVerification);
    }
    
    /**
     * 执行实际的点击测试
     */
    async performClickTests() {
        console.log('🖱️  4. 实际点击测试...');
        
        // 清理事件日志
        this.eventLog = [];
        
        // 查找第一个发布按钮进行测试
        const approveBtn = document.querySelector('.btn-success');
        if (approveBtn) {
            console.log('   找到发布按钮，执行点击测试...');
            
            // 模拟点击事件
            const clickEvent = new MouseEvent('click', {
                bubbles: true,
                cancelable: true,
                view: window
            });
            
            // 添加父元素事件监听器来测试冒泡
            const parentElement = approveBtn.parentElement;
            let parentClickTriggered = false;
            
            const parentClickHandler = (e) => {
                parentClickTriggered = true;
                console.log('   ⚠️  父元素点击事件被触发 - 事件冒泡未被阻止！');
            };
            
            if (parentElement) {
                parentElement.addEventListener('click', parentClickHandler);
            }
            
            // 执行点击
            approveBtn.dispatchEvent(clickEvent);
            
            // 等待事件处理
            await new Promise(resolve => setTimeout(resolve, 100));
            
            // 清理监听器
            if (parentElement) {
                parentElement.removeEventListener('click', parentClickHandler);
            }
            
            this.testResults.push({
                test: 'Click Event Propagation',
                status: !parentClickTriggered ? 'pass' : 'fail',
                details: {
                    buttonFound: true,
                    parentClickTriggered,
                    eventLog: this.eventLog.slice()
                }
            });
            
            if (!parentClickTriggered) {
                console.log('   ✅ 事件冒泡已被成功阻止');
            }
            
        } else {
            console.log('   ❌ 未找到发布按钮');
            this.testResults.push({
                test: 'Click Event Propagation',
                status: 'skip',
                reason: 'No approve button found'
            });
        }
    }
    
    /**
     * 验证Vue响应性是否正常
     */
    async verifyVueReactivity() {
        console.log('⚛️  5. Vue响应性验证...');
        
        if (!this.vueInstance) {
            this.testResults.push({
                test: 'Vue Reactivity',
                status: 'skip',
                reason: 'Vue instance not available'
            });
            return;
        }
        
        // 检查关键响应式数据是否存在
        const reactiveProperties = [
            'messages',
            'selectedMessages',
            'filters',
            'loading',
            'isLoadingMore'
        ];
        
        let reactivityStatus = {};
        
        for (const prop of reactiveProperties) {
            if (this.vueInstance.hasOwnProperty(prop)) {
                reactivityStatus[prop] = {
                    exists: true,
                    type: typeof this.vueInstance[prop],
                    isArray: Array.isArray(this.vueInstance[prop])
                };
            } else {
                reactivityStatus[prop] = { exists: false };
            }
        }
        
        this.testResults.push({
            test: 'Vue Reactivity',
            status: 'info',
            details: reactivityStatus
        });
        
        console.log('   响应性状态:', reactivityStatus);
    }
    
    /**
     * 验证WebSocket连接完整性
     */
    async verifyWebSocketIntegrity() {
        console.log('🔌 6. WebSocket连接验证...');
        
        // 检查WebSocket管理器
        const hasWebSocketManager = window.WebSocketManager || this.vueInstance?.websocket;
        
        this.testResults.push({
            test: 'WebSocket Integrity',
            status: hasWebSocketManager ? 'pass' : 'warn',
            details: {
                webSocketManagerExists: !!hasWebSocketManager,
                windowWebSocket: !!window.WebSocket
            }
        });
        
        if (hasWebSocketManager) {
            console.log('   ✅ WebSocket管理器正常');
        } else {
            console.log('   ⚠️  WebSocket管理器未找到');
        }
    }
    
    /**
     * 生成验证报告
     */
    generateReport() {
        console.log('\n📊 事件冒泡修复验证报告');
        console.log('=' .repeat(50));
        
        let passCount = 0;
        let failCount = 0;
        let skipCount = 0;
        let warnCount = 0;
        
        this.testResults.forEach((result, index) => {
            const status = result.status;
            const icon = {
                'pass': '✅',
                'fail': '❌', 
                'skip': '⏭️',
                'warn': '⚠️',
                'info': 'ℹ️',
                'error': '💥'
            }[status] || '❓';
            
            console.log(`${icon} ${result.test}: ${status.toUpperCase()}`);
            
            if (result.details) {
                console.log('   详情:', result.details);
            }
            
            if (result.error) {
                console.log('   错误:', result.error);
            }
            
            if (result.reason) {
                console.log('   原因:', result.reason);
            }
            
            // 统计
            if (status === 'pass') passCount++;
            else if (status === 'fail') failCount++;
            else if (status === 'skip') skipCount++;
            else if (status === 'warn') warnCount++;
        });
        
        console.log('\n📈 测试结果统计:');
        console.log(`   ✅ 通过: ${passCount}`);
        console.log(`   ❌ 失败: ${failCount}`);
        console.log(`   ⚠️  警告: ${warnCount}`);
        console.log(`   ⏭️ 跳过: ${skipCount}`);
        
        // 总体评估
        if (failCount === 0 && warnCount <= 1) {
            console.log('\n🎉 修复验证：成功！');
            console.log('   事件冒泡问题已被有效解决');
        } else if (failCount > 0) {
            console.log('\n⚠️  修复验证：存在问题');
            console.log('   仍有部分事件冒泡问题未解决');
        } else {
            console.log('\n✅ 修复验证：基本成功');
            console.log('   大部分问题已解决，有轻微警告');
        }
        
        console.log('\n🔍 详细的事件日志:');
        this.eventLog.forEach((log, i) => {
            console.log(`   ${i+1}. ${log.type} - ${log.element?.tagName} - 冒泡阻止: ${log.propagationStopped}`);
        });
    }
    
    /**
     * 快速测试方法 - 用于用户手动验证
     */
    quickTest() {
        console.log('🚀 快速验证测试');
        
        const buttons = document.querySelectorAll('.btn-success, .btn-danger');
        console.log(`找到 ${buttons.length} 个关键按钮`);
        
        if (buttons.length > 0) {
            console.log('请手动点击按钮并观察：');
            console.log('1. 是否显示"收到X条消息"（应该不显示）');
            console.log('2. 按钮功能是否正常工作');
            console.log('3. 页面是否有异常滚动或刷新');
        }
        
        return buttons.length;
    }
}

// 自动执行验证
if (typeof window !== 'undefined') {
    window.EventBubbleTest = new EventBubbleVerificationTest();
    
    // 提供便捷方法
    window.testEventBubble = () => window.EventBubbleTest.runFullVerification();
    window.quickEventTest = () => window.EventBubbleTest.quickTest();
    
    console.log('🔧 事件冒泡验证工具已就绪');
    console.log('执行 testEventBubble() 进行完整验证');
    console.log('执行 quickEventTest() 进行快速验证');
}