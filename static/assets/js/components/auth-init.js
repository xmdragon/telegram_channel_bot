// Telegram 认证页面初始化脚本

document.addEventListener('DOMContentLoaded', function() {
//     console.log('auth-init.js loaded');
    
    // 检查Vue.js是否加载
    if (typeof Vue === 'undefined') {
        console.error('Vue.js not loaded!');
    } else {
//         console.log('Vue.js loaded successfully');
    }
    
    // 检查Element Plus是否加载
    if (typeof ElementPlus === 'undefined') {
        console.error('Element Plus not loaded!');
    } else {
//         console.log('Element Plus loaded successfully');
    }
    
    // 检查axios是否加载
    if (typeof axios === 'undefined') {
        console.error('Axios not loaded!');
    } else {
//         console.log('Axios loaded successfully');
    }
    
    // 检查WebSocket支持
    if (typeof WebSocket === 'undefined') {
        console.warn('Browser does not support WebSocket');
    } else {
//         console.log('WebSocket support available');
    }
    
    // 页面加载完成
//     console.log('Auth page initialization complete');
}); 