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
        <div class="nav-bar-container">
            <div class="nav-bar-header" v-if="pageTitle">
                <div class="nav-title-wrapper">
                    <h1 class="nav-page-title">{{ pageTitle }}</h1>
                    <span class="nav-page-subtitle" v-if="pageSubtitle">{{ pageSubtitle }}</span>
                </div>
            </div>
            <div class="nav-bar">
                <div class="nav-links">
                    <a href="./index.html" :class="['nav-link', currentPath === '/' || currentPath === '/index.html' ? 'active' : '']">🏠 主控制台</a>
                    <a href="./config.html" :class="['nav-link', currentPath === '/config' || currentPath === '/config.html' ? 'active' : '']">⚙️ 系统配置</a>
                    <a href="./keywords.html" :class="['nav-link', currentPath === '/keywords' || currentPath === '/keywords.html' ? 'active' : '']">🔍 关键词管理</a>
                    <a href="./status.html" :class="['nav-link', currentPath === '/status' || currentPath === '/status.html' ? 'active' : '']">📊 系统状态</a>
                    <a href="./logs.html" :class="['nav-link', currentPath === '/logs' || currentPath === '/logs.html' || currentPath.includes('logs.html') ? 'active' : '']">📋 系统日志</a>
                    <a href="./auth.html" :class="['nav-link', currentPath === '/auth' || currentPath === '/auth.html' ? 'active' : '']">🔐 Telegram登录</a>
                </div>
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