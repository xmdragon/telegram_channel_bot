/**
 * 导航栏组件
 */

// 延迟获取API配置，避免加载时错误
function getAPI() {
    return window.API || {};
}

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
                    <a href="./tail-filter-manager.html" :class="['nav-link', isActive('/tail-filter-manager.html') ? 'active' : '']">🤖 AI训练</a>
                    <a href="./status.html" :class="['nav-link', isActive('/status.html') ? 'active' : '']">📊 系统状态</a>
                    <a href="./logs.html" :class="['nav-link', isActive('/logs.html') ? 'active' : '']">📋 系统日志</a>
                    <a href="./admin-manage.html" :class="['nav-link', isActive('/admin-manage.html') ? 'active' : '']">👥 管理员</a>
                    <a href="./telegram-auth.html" :class="['nav-link', isActive('/telegram-auth.html') ? 'active' : '']">📱 Telegram认证</a>
                    <a href="#" @click.prevent="handleLogout" class="nav-link">🚪 登出</a>
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
        },
        async handleLogout() {
            try {
                await axios.post(getAPI().adminAuth?.logout || '/api/admin/auth/logout');
                // 清除本地存储的token
                localStorage.removeItem('admin_token');
                // 跳转到登录页
                window.location.href = '/static/login.html';
            } catch (error) {
                // console.error('登出失败:', error);
                // 即使失败也清除token并跳转
                localStorage.removeItem('admin_token');
                window.location.href = '/static/login.html';
            }
        }
    }
};

// 注册为全局组件
if (typeof window !== 'undefined' && window.Vue) {
    window.NavBar = NavBar;
}