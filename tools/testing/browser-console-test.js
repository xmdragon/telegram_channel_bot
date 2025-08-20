/**
 * 浏览器控制台快速测试脚本
 * 复制此脚本内容到浏览器控制台运行
 */

(function() {
    console.log('🚀 事件冒泡修复验证工具');
    console.log('=' .repeat(40));
    
    // 检测页面环境
    const hasVueApp = !!document.querySelector('#app');
    const hasButtons = document.querySelectorAll('.btn').length;
    const hasMessages = document.querySelectorAll('[class*="message"]').length;
    
    console.log(`Vue应用: ${hasVueApp ? '✅' : '❌'}`);
    console.log(`按钮数量: ${hasButtons}`);
    console.log(`消息数量: ${hasMessages}`);
    
    if (!hasVueApp || hasButtons === 0) {
        console.log('❌ 环境检查失败，请确保在消息管理页面执行此脚本');
        return;
    }
    
    // 事件监控器
    let eventLog = [];
    let parentEventTriggered = false;
    
    // 包装事件处理器
    function wrapEventHandler(element, eventType) {
        const parent = element.parentElement;
        if (!parent) return;
        
        const handler = (e) => {
            parentEventTriggered = true;
            console.log('⚠️  检测到父元素事件触发 - 事件冒泡未被阻止！');
            eventLog.push({
                type: eventType,
                element: e.target.tagName,
                time: new Date().toISOString()
            });
        };
        
        parent.addEventListener(eventType, handler, true);
        
        // 返回清理函数
        return () => parent.removeEventListener(eventType, handler, true);
    }
    
    // 快速测试函数
    window.testEventBubbleFix = function() {
        console.log('\n🧪 开始事件冒泡测试...');
        
        // 重置状态
        eventLog = [];
        parentEventTriggered = false;
        
        // 查找测试按钮
        const approveBtn = document.querySelector('.btn-success');
        const rejectBtn = document.querySelector('.btn-danger');
        
        if (!approveBtn && !rejectBtn) {
            console.log('❌ 未找到测试按钮，请确保页面有待审核消息');
            return;
        }
        
        const testBtn = approveBtn || rejectBtn;
        const btnType = approveBtn ? '发布' : '拒绝';
        
        console.log(`找到${btnType}按钮，开始测试...`);
        
        // 设置监控
        const cleanup = wrapEventHandler(testBtn, 'click');
        
        // 模拟点击
        const clickEvent = new MouseEvent('click', {
            bubbles: true,
            cancelable: true,
            view: window
        });
        
        setTimeout(() => {
            testBtn.dispatchEvent(clickEvent);
            
            // 等待事件处理完成
            setTimeout(() => {
                if (cleanup) cleanup();
                
                // 输出结果
                console.log('\n📋 测试结果:');
                if (parentEventTriggered) {
                    console.log('❌ 失败：检测到事件冒泡');
                    console.log('   需要检查按钮事件处理器是否正确实现三重阻止机制');
                } else {
                    console.log('✅ 成功：事件冒泡已被阻止');
                    console.log('   按钮点击不会触发父元素事件');
                }
                
                if (eventLog.length > 0) {
                    console.log('\n📝 事件日志:', eventLog);
                }
                
                console.log('\n💡 下一步：');
                console.log('1. 手动点击页面上的按钮验证功能');
                console.log('2. 确认不再出现"收到X条消息"提示');
                console.log('3. 验证消息状态更新正常');
                
            }, 500);
        }, 100);
    };
    
    // 快速功能检查
    window.quickCheck = function() {
        console.log('\n⚡ 快速功能检查');
        console.log('-' .repeat(20));
        
        const checks = {
            'Vue应用': !!document.querySelector('#app').__vue__,
            '发布按钮': !!document.querySelector('.btn-success'),
            '拒绝按钮': !!document.querySelector('.btn-danger'),
            '消息卡片': document.querySelectorAll('[class*="message"]').length > 0,
            'Element UI': !!(window.ElementPlus || window.ElMessage),
            'API配置': !!window.API
        };
        
        Object.entries(checks).forEach(([name, status]) => {
            console.log(`${status ? '✅' : '❌'} ${name}`);
        });
        
        const passCount = Object.values(checks).filter(Boolean).length;
        const total = Object.keys(checks).length;
        console.log(`\n整体状态: ${passCount}/${total} 通过 (${Math.round(passCount/total*100)}%)`);
    };
    
    // 监听器检查
    window.checkButtonHandlers = function() {
        console.log('\n🔍 按钮事件处理器检查');
        console.log('-' .repeat(25));
        
        const buttons = {
            '发布按钮': document.querySelector('.btn-success'),
            '拒绝按钮': document.querySelector('.btn-danger'),
            '编辑按钮': document.querySelector('.btn-secondary'),
            '广告按钮': document.querySelector('.btn-warning')
        };
        
        Object.entries(buttons).forEach(([name, btn]) => {
            if (btn) {
                const hasVueBinding = !!(btn.__vueParentComponent || btn.__vueListeners);
                const hasClickAttr = btn.hasAttribute('@click') || btn.getAttribute('onclick');
                console.log(`${name}: Vue绑定=${hasVueBinding}, 点击属性=${!!hasClickAttr}`);
            } else {
                console.log(`${name}: 未找到`);
            }
        });
    };
    
    // 使用说明
    console.log('\n📖 使用方法:');
    console.log('testEventBubbleFix() - 测试事件冒泡修复');
    console.log('quickCheck() - 快速功能检查');  
    console.log('checkButtonHandlers() - 检查按钮事件处理');
    
    console.log('\n✨ 推荐测试流程:');
    console.log('1. quickCheck() - 检查基础环境');
    console.log('2. testEventBubbleFix() - 测试事件冒泡');
    console.log('3. 手动点击按钮验证功能');
    
    // 自动运行快速检查
    console.log('\n🔄 自动运行快速检查...');
    window.quickCheck();
    
})();