// 诊断脚本 - 在浏览器控制台运行
console.log('=== 时间诊断开始 ===');

// 检查Vue应用
if (typeof messageApp !== 'undefined' && messageApp.messages) {
    console.log('找到Vue应用，消息数量:', messageApp.messages.length);
    
    if (messageApp.messages.length > 0) {
        const msg = messageApp.messages[0];
        console.log('\n第一条消息:');
        console.log('  ID:', msg.id);
        console.log('  created_at原始值:', msg.created_at);
        console.log('  类型:', typeof msg.created_at);
        
        if (msg.created_at) {
            // 解析时间
            const date = new Date(msg.created_at);
            const now = new Date();
            const diff = now - date;
            
            console.log('\n时间解析:');
            console.log('  解析后Date:', date.toString());
            console.log('  ISO格式:', date.toISOString());
            console.log('  本地时间:', date.toLocaleString());
            console.log('  当前时间:', now.toString());
            console.log('  时间差(毫秒):', diff);
            console.log('  时间差(分钟):', Math.floor(diff / 60000));
            console.log('  时间差(小时):', (diff / 3600000).toFixed(1));
            
            // 测试formatTime函数
            if (typeof messageApp.formatTime === 'function') {
                const formatted = messageApp.formatTime(msg.created_at);
                console.log('\nformatTime结果:', formatted);
            }
            
            // 检查时区
            console.log('\n时区信息:');
            console.log('  浏览器时区偏移(分钟):', new Date().getTimezoneOffset());
            console.log('  当前时区:', Intl.DateTimeFormat().resolvedOptions().timeZone);
            
            // 手动计算正确的时间差
            console.log('\n正确的计算:');
            // 如果created_at包含+00:00，说明是UTC时间
            if (msg.created_at.includes('+00:00') || msg.created_at.includes('Z')) {
                console.log('  created_at是UTC时间');
                const utcTime = new Date(msg.created_at);
                const correctDiff = Date.now() - utcTime.getTime();
                console.log('  正确的时间差(毫秒):', correctDiff);
                console.log('  正确的时间差(小时):', (correctDiff / 3600000).toFixed(1));
                
                if (correctDiff < 60000) {
                    console.log('  应该显示: 刚刚');
                } else if (correctDiff < 3600000) {
                    console.log('  应该显示:', Math.floor(correctDiff / 60000) + '分钟前');
                } else if (correctDiff < 86400000) {
                    console.log('  应该显示:', Math.floor(correctDiff / 3600000) + '小时前');
                }
            }
        }
    }
} else {
    console.log('未找到Vue应用或消息数据');
    console.log('尝试手动调用API...');
    
    // 手动调用API
    fetch('/api/messages/?page=1&size=1')
        .then(response => response.json())
        .then(data => {
            console.log('API响应:', data);
            if (data.messages && data.messages[0]) {
                const msg = data.messages[0];
                console.log('第一条消息的created_at:', msg.created_at);
                
                // 测试时间解析
                const date = new Date(msg.created_at);
                const now = new Date();
                const diff = now - date;
                console.log('时间差(小时):', (diff / 3600000).toFixed(1));
            }
        })
        .catch(error => console.error('API调用失败:', error));
}

console.log('\n=== 诊断结束 ===');
console.log('如果时间差显示8小时，说明时区处理有问题');
console.log('如果时间差显示正确（如0.5小时），说明前端处理正确');