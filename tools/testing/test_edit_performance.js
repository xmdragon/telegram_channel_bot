/**
 * 前端消息编辑性能测试
 * 
 * 这个脚本可以在浏览器开发者控制台中运行，测试编辑性能优化效果
 */

// 测试性能优化的函数
function testEditPerformance() {
    console.log('🚀 开始测试消息编辑性能优化...');
    
    // 检查 updateSingleMessage 方法是否存在
    if (typeof app !== 'undefined' && app.updateSingleMessage) {
        console.log('✅ 发现优化的 updateSingleMessage 方法');
        
        // 模拟消息编辑更新
        const testUpdates = {
            filtered_content: '性能测试内容 - ' + new Date().toISOString(),
            updated_at: new Date().toISOString()
        };
        
        // 记录开始时间
        const startTime = performance.now();
        
        // 如果有消息，测试更新第一条消息
        if (app.messages && app.messages.length > 0) {
            const messageId = app.messages[0].id;
            console.log('📝 测试更新消息:', messageId);
            
            // 执行局部更新
            app.updateSingleMessage(messageId, testUpdates);
            
            // 记录结束时间
            const endTime = performance.now();
            const updateTime = endTime - startTime;
            
            console.log(`⚡ 局部更新耗时: ${updateTime.toFixed(2)}ms`);
            console.log('✅ 性能优化测试完成！');
            
            return {
                success: true,
                updateTime: updateTime,
                messageId: messageId,
                message: `局部更新成功，耗时 ${updateTime.toFixed(2)}ms`
            };
        } else {
            console.log('⚠️  没有找到消息进行测试');
            return {
                success: false,
                message: '没有消息可供测试'
            };
        }
    } else {
        console.log('❌ 未找到优化的 updateSingleMessage 方法，可能优化未生效');
        return {
            success: false,
            message: 'updateSingleMessage 方法不存在'
        };
    }
}

// 比较新旧方法的性能
function comparePerformance() {
    console.log('📊 比较编辑方法性能...');
    
    if (typeof app === 'undefined') {
        console.log('❌ 未找到 app 实例');
        return;
    }
    
    if (!app.messages || app.messages.length === 0) {
        console.log('⚠️  没有消息数据');
        return;
    }
    
    const messageId = app.messages[0].id;
    const testUpdates = {
        filtered_content: '性能对比测试',
        updated_at: new Date().toISOString()
    };
    
    // 测试新方法（局部更新）
    console.log('🔬 测试局部更新方法...');
    const startTime1 = performance.now();
    app.updateSingleMessage(messageId, testUpdates);
    const endTime1 = performance.now();
    const localUpdateTime = endTime1 - startTime1;
    
    // 恢复原始内容准备下次测试
    setTimeout(() => {
        // 模拟旧方法（整列表重新赋值）
        console.log('🔬 测试传统更新方法...');
        const startTime2 = performance.now();
        
        // 模拟旧的数组展开操作
        const messageIndex = app.messages.findIndex(msg => msg.id === messageId);
        if (messageIndex !== -1) {
            app.messages[messageIndex].filtered_content = '传统更新测试';
            app.messages[messageIndex].updated_at = new Date().toISOString();
            // 模拟旧的强制更新方式
            app.messages = [...app.messages];
        }
        
        const endTime2 = performance.now();
        const traditionalUpdateTime = endTime2 - startTime2;
        
        // 输出对比结果
        console.log('📈 性能对比结果:');
        console.log(`   局部更新: ${localUpdateTime.toFixed(2)}ms`);
        console.log(`   传统更新: ${traditionalUpdateTime.toFixed(2)}ms`);
        console.log(`   性能提升: ${((traditionalUpdateTime - localUpdateTime) / traditionalUpdateTime * 100).toFixed(1)}%`);
        
        if (localUpdateTime < traditionalUpdateTime) {
            console.log('🎉 局部更新性能更优！');
        } else {
            console.log('🤔 性能提升不明显，可能需要更多消息数据才能看出差异');
        }
    }, 100);
}

// 使用说明
console.log(`
📋 消息编辑性能测试工具使用说明:

在消息管理页面的浏览器控制台中运行：

1. 基础性能测试:
   testEditPerformance()

2. 新旧方法性能对比:
   comparePerformance()

3. 检查优化是否生效:
   console.log('优化方法存在:', typeof app?.updateSingleMessage === 'function')
`);

// 导出测试函数供控制台使用
if (typeof window !== 'undefined') {
    window.testEditPerformance = testEditPerformance;
    window.comparePerformance = comparePerformance;
}