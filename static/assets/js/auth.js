// 临时重定向文件 - auth.js 已重命名为 admin-auth.js

// 动态加载正确的文件
(function() {
    'use strict';
    
    // 如果已经加载了 admin-auth.js，就不需要再加载
    if (window.authManager) {
        return;
    }
    
    // 动态加载 admin-auth.js
    const script = document.createElement('script');
    script.src = 'assets/js/admin-auth.js';
    script.async = false;
    document.head.appendChild(script);
})();