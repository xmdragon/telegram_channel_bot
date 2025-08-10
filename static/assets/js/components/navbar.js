/**
 * 导航栏组件
 */
const NavBar = {
    props: {
        pageTitle: {
            type: String,
            default: ''
        },
        pageSubtitle: {
            type: String,
            default: ''
        }
    },
    template: `
        <nav class="navbar">
            <div class="navbar-content">
                <div class="navbar-title">
                    <h1>{{ pageTitle || '🚀 Telegram 消息审核系统' }}</h1>
                    <span class="navbar-subtitle" v-if="pageSubtitle">{{ pageSubtitle }}</span>
                </div>
                <div class="navbar-links">
                    <a href="./index.html" :class="['nav-link', isActive('/index.html') ? 'active' : '']">🏠 主控制台</a>
                    <a href="./config.html" :class="['nav-link', isActive('/config.html') ? 'active' : '']">⚙️ 系统配置</a>
                    <a href="./keywords.html" :class="['nav-link', isActive('/keywords.html') ? 'active' : '']">🔍 关键词管理</a>
                    <a href="./train.html" :class="['nav-link', isActive('/train.html') ? 'active' : '']">🤖 AI训练</a>
                    <a href="./status.html" :class="['nav-link', isActive('/status.html') ? 'active' : '']">📊 系统状态</a>
                    <a href="./logs.html" :class="['nav-link', isActive('/logs.html') ? 'active' : '']">📋 系统日志</a>
                    <a href="./auth.html" :class="['nav-link', isActive('/auth.html') ? 'active' : '']">🔐 登录</a>
                </div>
            </div>
        </nav>
    `,
    data() {
        return {
            currentPath: ''
        }
    },
    mounted() {
        // 获取当前路径
        this.currentPath = window.location.pathname;
    },
    methods: {
        isActive(path) {
            const currentPath = window.location.pathname;
            return currentPath.includes(path) || 
                   (path === '/index.html' && (currentPath === '/' || currentPath === ''));
        }
    }
};

// 注册为全局组件
if (typeof window !== 'undefined' && window.Vue) {
    window.NavBar = NavBar;
}