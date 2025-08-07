/**
 * 导航栏组件
 */
const NavBar = {
    template: `
        <div class="nav-bar">
            <div class="nav-links">
                <a href="/" :class="['nav-link', currentPath === '/' || currentPath === '/index.html' ? 'active' : '']">🏠 主控制台</a>
                <a href="/config" :class="['nav-link', currentPath === '/config' || currentPath === '/config.html' ? 'active' : '']">⚙️ 系统配置</a>
                <a href="/keywords" :class="['nav-link', currentPath === '/keywords' || currentPath === '/keywords.html' ? 'active' : '']">🔍 关键词管理</a>
                <a href="/status" :class="['nav-link', currentPath === '/status' || currentPath === '/status.html' ? 'active' : '']">📊 系统状态</a>
                <a href="/auth" :class="['nav-link', currentPath === '/auth' || currentPath === '/auth.html' ? 'active' : '']">🔐 Telegram登录</a>
            </div>
        </div>
    `,
    data() {
        return {
            currentPath: ''
        }
    },
    mounted() {
        // 获取当前路径
        this.currentPath = window.location.pathname;
    }
};

// 注册为全局组件
if (typeof window !== 'undefined' && window.Vue) {
    window.NavBar = NavBar;
}