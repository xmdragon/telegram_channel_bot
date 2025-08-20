/**
 * 功能完整性测试脚本
 * 验证修复后的系统各项功能是否正常工作
 * 
 * 用法：在浏览器控制台中执行此脚本
 * 1. 打开 http://localhost:8000/static/index.html
 * 2. 登录并进入消息管理页面
 * 3. 在控制台中运行此脚本
 */

class FunctionalIntegrityTest {
    constructor() {
        this.testResults = [];
        this.vueInstance = null;
        this.originalFetch = window.fetch;
        this.apiCalls = [];
        
        this.init();
    }
    
    init() {
        // 检测Vue应用
        this.detectVueApp();
        
        // 拦截API调用
        this.interceptApiCalls();
        
        console.log('🧪 功能完整性测试工具已初始化');
    }
    
    detectVueApp() {
        const vueApp = document.querySelector('#app');
        if (vueApp && (vueApp.__vue__ || vueApp._vnode)) {
            this.vueInstance = vueApp.__vue__ || vueApp._vnode.componentInstance;
            console.log('✅ Vue应用已检测到');
        } else {
            console.warn('❌ 未检测到Vue应用');
        }
    }
    
    /**
     * 拦截API调用以监控网络请求
     */
    interceptApiCalls() {
        const self = this;
        
        // 拦截fetch
        window.fetch = async function(...args) {
            const startTime = Date.now();
            const url = typeof args[0] === 'string' ? args[0] : args[0].url;
            
            try {
                const response = await self.originalFetch.apply(this, args);
                const endTime = Date.now();
                
                self.apiCalls.push({
                    url,
                    method: args[1]?.method || 'GET',
                    status: response.status,
                    duration: endTime - startTime,
                    success: response.ok,
                    timestamp: startTime
                });
                
                return response;
            } catch (error) {
                const endTime = Date.now();
                
                self.apiCalls.push({
                    url,
                    method: args[1]?.method || 'GET',
                    status: 0,
                    duration: endTime - startTime,
                    success: false,
                    error: error.message,
                    timestamp: startTime
                });
                
                throw error;
            }
        };
    }
    
    /**
     * 运行完整的功能测试套件
     */
    async runFullTest() {
        console.log('🚀 开始功能完整性测试...\n');
        
        try {
            // 清理之前的数据
            this.testResults = [];
            this.apiCalls = [];
            
            // 1. 页面加载测试
            await this.testPageLoad();
            
            // 2. Vue应用状态测试
            await this.testVueAppState();
            
            // 3. 消息加载功能测试
            await this.testMessageLoading();
            
            // 4. 按钮功能测试
            await this.testButtonFunctions();
            
            // 5. 批量操作测试
            await this.testBatchOperations();
            
            // 6. 搜索和过滤测试
            await this.testSearchAndFilter();
            
            // 7. WebSocket连接测试
            await this.testWebSocketConnection();
            
            // 8. API交互测试
            await this.testApiInteractions();
            
            // 9. 错误处理测试
            await this.testErrorHandling();
            
            // 生成报告
            this.generateFunctionalReport();
            
        } catch (error) {
            console.error('❌ 功能测试出错:', error);
            this.testResults.push({
                test: 'Overall Functional Test',
                status: 'error',
                error: error.message
            });
        }
    }
    
    /**
     * 测试页面加载状态
     */
    async testPageLoad() {
        console.log('📄 1. 页面加载测试...');
        
        const hasTitle = !!document.title;
        const hasVueApp = !!document.querySelector('#app');
        const hasElementPlus = !!(window.ElementPlus || window.ElMessage);
        const hasAxios = !!window.axios;
        const hasAPI = !!window.API;
        
        const cssFiles = document.querySelectorAll('link[rel="stylesheet"]');
        const jsFiles = document.querySelectorAll('script[src]');
        
        this.testResults.push({
            test: 'Page Load',
            status: hasVueApp && hasElementPlus && hasAxios ? 'pass' : 'fail',
            details: {
                title: hasTitle,
                vueApp: hasVueApp,
                elementPlus: hasElementPlus,
                axios: hasAxios,
                apiConfig: hasAPI,
                cssFiles: cssFiles.length,
                jsFiles: jsFiles.length
            }
        });
        
        console.log(`   页面标题: ${hasTitle ? '✅' : '❌'}`);
        console.log(`   Vue应用: ${hasVueApp ? '✅' : '❌'}`);
        console.log(`   Element Plus: ${hasElementPlus ? '✅' : '❌'}`);
        console.log(`   Axios: ${hasAxios ? '✅' : '❌'}`);
        console.log(`   API配置: ${hasAPI ? '✅' : '❌'}`);
    }
    
    /**
     * 测试Vue应用状态
     */
    async testVueAppState() {
        console.log('⚛️  2. Vue应用状态测试...');
        
        if (!this.vueInstance) {
            this.testResults.push({
                test: 'Vue App State',
                status: 'skip',
                reason: 'Vue instance not available'
            });
            return;
        }
        
        const requiredData = [
            'messages',
            'loading',
            'filters',
            'stats'
        ];
        
        const requiredMethods = [
            'loadMessages',
            'approveMessage',
            'rejectMessage',
            'loadStats'
        ];
        
        let dataStatus = {};
        let methodStatus = {};
        
        // 检查数据属性
        for (const prop of requiredData) {
            dataStatus[prop] = this.vueInstance.hasOwnProperty(prop);
        }
        
        // 检查方法
        for (const method of requiredMethods) {
            methodStatus[method] = typeof this.vueInstance[method] === 'function';
        }
        
        const dataOk = Object.values(dataStatus).every(Boolean);
        const methodsOk = Object.values(methodStatus).every(Boolean);
        
        this.testResults.push({
            test: 'Vue App State',
            status: dataOk && methodsOk ? 'pass' : 'fail',
            details: {
                dataProperties: dataStatus,
                methods: methodStatus
            }
        });
        
        console.log(`   数据属性: ${dataOk ? '✅' : '❌'}`);
        console.log(`   方法检查: ${methodsOk ? '✅' : '❌'}`);
    }
    
    /**
     * 测试消息加载功能
     */
    async testMessageLoading() {
        console.log('📥 3. 消息加载功能测试...');
        
        if (!this.vueInstance) {
            this.testResults.push({
                test: 'Message Loading',
                status: 'skip',
                reason: 'Vue instance not available'
            });
            return;
        }
        
        try {
            const initialMessageCount = this.vueInstance.messages ? this.vueInstance.messages.length : 0;
            
            // 尝试加载消息
            if (typeof this.vueInstance.loadMessages === 'function') {
                await this.vueInstance.loadMessages();
                
                const newMessageCount = this.vueInstance.messages ? this.vueInstance.messages.length : 0;
                
                this.testResults.push({
                    test: 'Message Loading',
                    status: newMessageCount >= 0 ? 'pass' : 'fail',
                    details: {
                        initialCount: initialMessageCount,
                        newCount: newMessageCount,
                        loadingState: this.vueInstance.loading
                    }
                });
                
                console.log(`   初始消息数: ${initialMessageCount}`);
                console.log(`   加载后消息数: ${newMessageCount}`);
            } else {
                this.testResults.push({
                    test: 'Message Loading',
                    status: 'fail',
                    reason: 'loadMessages method not found'
                });
            }
        } catch (error) {
            this.testResults.push({
                test: 'Message Loading',
                status: 'error',
                error: error.message
            });
            console.log(`   ❌ 加载失败: ${error.message}`);
        }
    }
    
    /**
     * 测试按钮功能
     */
    async testButtonFunctions() {
        console.log('🔘 4. 按钮功能测试...');
        
        const buttonSelectors = {
            'approve': '.btn-success',
            'reject': '.btn-danger', 
            'markAd': '.btn-warning',
            'trainTail': '.btn-info',
            'filterTail': '.btn-primary'
        };
        
        let buttonTests = {};
        
        for (const [type, selector] of Object.entries(buttonSelectors)) {
            const buttons = document.querySelectorAll(selector);
            
            buttonTests[type] = {
                found: buttons.length,
                hasClickHandler: false,
                hasTripleStop: false
            };
            
            // 检查第一个按钮的事件处理
            if (buttons.length > 0) {
                const button = buttons[0];
                
                // 检查是否有Vue事件绑定
                const vueEvents = button.__vueListeners || {};
                buttonTests[type].hasClickHandler = !!vueEvents.click;
                
                // 模拟检查事件处理器
                if (this.vueInstance) {
                    const methodName = type === 'approve' ? 'approveMessage' :
                                     type === 'reject' ? 'rejectMessage' : 
                                     `${type}Message`;
                    
                    if (typeof this.vueInstance[methodName] === 'function') {
                        const methodSource = this.vueInstance[methodName].toString();
                        buttonTests[type].hasTripleStop = 
                            methodSource.includes('preventDefault') &&
                            methodSource.includes('stopPropagation') &&
                            methodSource.includes('stopImmediatePropagation');
                    }
                }
            }
        }
        
        const allButtonsOk = Object.values(buttonTests).every(test => test.found > 0);
        
        this.testResults.push({
            test: 'Button Functions',
            status: allButtonsOk ? 'pass' : 'warn',
            details: buttonTests
        });
        
        console.log('   按钮功能状态:', buttonTests);
    }
    
    /**
     * 测试批量操作
     */
    async testBatchOperations() {
        console.log('📦 5. 批量操作测试...');
        
        const batchButtons = document.querySelectorAll('.batch-action-btn, [class*="batch"]');
        const selectAllCheckbox = document.querySelector('#select-all, [id*="select"][id*="all"]');
        
        let batchTest = {
            batchButtonsFound: batchButtons.length,
            selectAllFound: !!selectAllCheckbox,
            hasBatchMethods: false
        };
        
        if (this.vueInstance) {
            const batchMethods = ['approveMessages', 'rejectMessages', 'toggleSelectAll'];
            batchTest.hasBatchMethods = batchMethods.some(method => 
                typeof this.vueInstance[method] === 'function'
            );
        }
        
        this.testResults.push({
            test: 'Batch Operations',
            status: batchTest.batchButtonsFound > 0 || batchTest.hasBatchMethods ? 'pass' : 'warn',
            details: batchTest
        });
        
        console.log('   批量操作状态:', batchTest);
    }
    
    /**
     * 测试搜索和过滤功能
     */
    async testSearchAndFilter() {
        console.log('🔍 6. 搜索和过滤测试...');
        
        const searchInput = document.querySelector('input[type="search"], input[placeholder*="搜索"]');
        const filterSelects = document.querySelectorAll('select, .el-select');
        
        let searchTest = {
            searchInputFound: !!searchInput,
            filterSelectsFound: filterSelects.length,
            hasSearchMethod: false,
            hasFilterMethods: false
        };
        
        if (this.vueInstance) {
            searchTest.hasSearchMethod = typeof this.vueInstance.searchMessages === 'function';
            searchTest.hasFilterMethods = 
                typeof this.vueInstance.applyFilters === 'function' ||
                typeof this.vueInstance.filterByChannel === 'function';
        }
        
        this.testResults.push({
            test: 'Search and Filter',
            status: searchTest.searchInputFound || searchTest.hasSearchMethod ? 'pass' : 'warn',
            details: searchTest
        });
        
        console.log('   搜索过滤状态:', searchTest);
    }
    
    /**
     * 测试WebSocket连接
     */
    async testWebSocketConnection() {
        console.log('🔌 7. WebSocket连接测试...');
        
        const hasWebSocketManager = !!(window.WebSocketManager || 
                                       this.vueInstance?.websocket ||
                                       this.vueInstance?.ws);
        
        let wsTest = {
            webSocketManagerExists: hasWebSocketManager,
            webSocketSupported: !!window.WebSocket,
            connectionAttempted: false,
            connectionWorking: false
        };
        
        // 尝试检查WebSocket连接状态
        if (hasWebSocketManager && this.vueInstance) {
            if (this.vueInstance.websocket || this.vueInstance.ws) {
                const ws = this.vueInstance.websocket || this.vueInstance.ws;
                wsTest.connectionAttempted = true;
                wsTest.connectionWorking = ws.readyState === WebSocket.OPEN;
            }
        }
        
        this.testResults.push({
            test: 'WebSocket Connection',
            status: hasWebSocketManager && wsTest.webSocketSupported ? 'pass' : 'warn',
            details: wsTest
        });
        
        console.log('   WebSocket状态:', wsTest);
    }
    
    /**
     * 测试API交互
     */
    async testApiInteractions() {
        console.log('🌐 8. API交互测试...');
        
        const apiCallCount = this.apiCalls.length;
        const successfulCalls = this.apiCalls.filter(call => call.success).length;
        const failedCalls = this.apiCalls.filter(call => !call.success).length;
        
        const avgDuration = apiCallCount > 0 ? 
            this.apiCalls.reduce((sum, call) => sum + call.duration, 0) / apiCallCount : 0;
        
        let apiTest = {
            totalCalls: apiCallCount,
            successfulCalls,
            failedCalls,
            averageDuration: Math.round(avgDuration),
            hasApiConfig: !!window.API
        };
        
        this.testResults.push({
            test: 'API Interactions',
            status: apiTest.hasApiConfig && (failedCalls === 0 || successfulCalls > failedCalls) ? 'pass' : 'warn',
            details: apiTest
        });
        
        console.log('   API交互状态:', apiTest);
        
        // 显示最近的API调用
        if (this.apiCalls.length > 0) {
            console.log('   最近的API调用:');
            this.apiCalls.slice(-5).forEach((call, i) => {
                console.log(`     ${i+1}. ${call.method} ${call.url} - ${call.status} (${call.duration}ms)`);
            });
        }
    }
    
    /**
     * 测试错误处理
     */
    async testErrorHandling() {
        console.log('🚨 9. 错误处理测试...');
        
        let errorTest = {
            hasGlobalErrorHandler: !!window.onerror,
            hasVueErrorHandler: false,
            hasMessageManager: !!window.MessageManager,
            hasConsoleErrorLogging: true
        };
        
        // 检查Vue错误处理
        if (this.vueInstance && this.vueInstance.$options) {
            errorTest.hasVueErrorHandler = !!this.vueInstance.$options.errorHandler;
        }
        
        this.testResults.push({
            test: 'Error Handling',
            status: errorTest.hasMessageManager ? 'pass' : 'warn',
            details: errorTest
        });
        
        console.log('   错误处理状态:', errorTest);
    }
    
    /**
     * 生成功能测试报告
     */
    generateFunctionalReport() {
        console.log('\n📊 功能完整性测试报告');
        console.log('=' .repeat(50));
        
        let passCount = 0;
        let failCount = 0;
        let warnCount = 0;
        let skipCount = 0;
        let errorCount = 0;
        
        this.testResults.forEach((result) => {
            const status = result.status;
            const icon = {
                'pass': '✅',
                'fail': '❌',
                'warn': '⚠️',
                'skip': '⏭️',
                'error': '💥',
                'info': 'ℹ️'
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
            switch (status) {
                case 'pass': passCount++; break;
                case 'fail': failCount++; break;
                case 'warn': warnCount++; break;
                case 'skip': skipCount++; break;
                case 'error': errorCount++; break;
            }
        });
        
        console.log('\n📈 功能测试统计:');
        console.log(`   ✅ 通过: ${passCount}`);
        console.log(`   ❌ 失败: ${failCount}`);
        console.log(`   ⚠️  警告: ${warnCount}`);
        console.log(`   💥 错误: ${errorCount}`);
        console.log(`   ⏭️ 跳过: ${skipCount}`);
        
        // 总体评估
        const totalTests = this.testResults.length;
        const healthScore = Math.round((passCount / totalTests) * 100);
        
        console.log(`\n🏥 系统健康度: ${healthScore}%`);
        
        if (healthScore >= 90) {
            console.log('🎉 系统状态：优秀！所有核心功能正常工作');
        } else if (healthScore >= 70) {
            console.log('✅ 系统状态：良好，大部分功能正常');
        } else if (healthScore >= 50) {
            console.log('⚠️  系统状态：一般，存在一些功能问题');
        } else {
            console.log('❌ 系统状态：较差，需要修复多个功能');
        }
        
        // 功能完整性建议
        console.log('\n💡 建议:');
        if (failCount === 0 && errorCount === 0) {
            console.log('   - 系统功能完整，可以正常使用');
        } else {
            console.log('   - 建议修复失败和错误的功能');
            console.log('   - 检查网络连接和API服务状态');
        }
        
        if (warnCount > 0) {
            console.log('   - 关注警告项，可能影响用户体验');
        }
    }
    
    /**
     * 快速功能检查
     */
    quickFunctionalCheck() {
        console.log('⚡ 快速功能检查');
        
        const checks = {
            'Vue应用': !!this.vueInstance,
            '消息列表': !!document.querySelector('.message-card, .message-item, [class*="message"]'),
            '按钮组件': !!document.querySelector('.btn'),
            'Element UI': !!(window.ElementPlus || window.ElMessage),
            'API配置': !!window.API,
            'WebSocket': !!window.WebSocket
        };
        
        console.log('基础功能检查结果:');
        Object.entries(checks).forEach(([name, status]) => {
            console.log(`   ${status ? '✅' : '❌'} ${name}`);
        });
        
        const passCount = Object.values(checks).filter(Boolean).length;
        const total = Object.keys(checks).length;
        
        console.log(`\n整体状态: ${passCount}/${total} 通过 (${Math.round(passCount/total*100)}%)`);
        
        return { passCount, total, percentage: Math.round(passCount/total*100) };
    }
}

// 自动执行功能测试
if (typeof window !== 'undefined') {
    window.FunctionalTest = new FunctionalIntegrityTest();
    
    // 提供便捷方法
    window.testFunctional = () => window.FunctionalTest.runFullTest();
    window.quickFunctionalCheck = () => window.FunctionalTest.quickFunctionalCheck();
    
    console.log('🔧 功能完整性测试工具已就绪');
    console.log('执行 testFunctional() 进行完整功能测试');
    console.log('执行 quickFunctionalCheck() 进行快速功能检查');
}