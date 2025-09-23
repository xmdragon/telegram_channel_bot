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
                    <a href="./tail-filter-manager.html" :class="['nav-link', isActive('/tail-filter-manager.html') ? 'active' : '']">🤖 训练中心</a>
                    <a href="./status.html" :class="['nav-link', isActive('/status.html') ? 'active' : '']">📊 系统状态</a>
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
                // 获取token
                const token = localStorage.getItem('admin_token');
                
                if (token) {
                    // 携带认证头发送登出请求
                    await axios.post(API.adminAuth.logout, {}, {
                        headers: {
                            'Authorization': `Bearer ${token}`
                        }
                    });
                }
                
                // 清除本地存储
                localStorage.removeItem('admin_token');
                localStorage.removeItem('admin_info');
                
                // 显示登出成功消息
                if (window.SimpleMessage) {
                    window.SimpleMessage.success('已成功登出');
                }
                
                // 延时跳转，让用户看到成功消息
                setTimeout(() => {
                    window.location.href = API.pages.login;
                }, 1000);
                
            } catch (error) {
                console.error('登出请求失败:', error);
                
                // 即使服务端登出失败，也清除本地token并跳转
                localStorage.removeItem('admin_token');
                localStorage.removeItem('admin_info');
                
                if (window.SimpleMessage) {
                    window.SimpleMessage.warning('登出完成');
                }
                
                setTimeout(() => {
                    window.location.href = API.pages.login;
                }, 1000);
            }
        }
    }
};

// 注册为全局组件
if (typeof window !== 'undefined' && window.Vue) {
    window.NavBar = NavBar;
}