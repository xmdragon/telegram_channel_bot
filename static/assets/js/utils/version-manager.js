/**
 * 动态版本号管理器 - Linus式缓存优化
 * 解决固定版本号导致的缓存失效问题
 */

class VersionManager {
    constructor() {
        this.devMode = this.detectDevMode();
        this.coreLibVersions = {
            'vue.prod.js': '3.4.21',
            'axios.js': '1.6.0',
            'chart.js': '4.4.0'
        };
        this.currentVersion = this.generateVersion();
    }
    
    /**
     * 检测是否为开发模式
     */
    detectDevMode() {
        // 开发环境：localhost 或 127.0.0.1
        return location.hostname === 'localhost' || 
               location.hostname === '127.0.0.1' ||
               location.hostname === '0.0.0.0';
    }
    
    /**
     * 生成版本号
     */
    generateVersion() {
        if (this.devMode) {
            // 开发环境：使用时间戳确保实时更新
            return Date.now();
        } else {
            // 生产环境：使用构建时间或git hash
            return window.BUILD_VERSION || '1.0.0';
        }
    }
    
    /**
     * 获取资源的版本化URL
     */
    getVersionedUrl(url) {
        const filename = url.split('/').pop();
        
        // 核心库使用固定版本号（长期缓存）
        if (this.coreLibVersions[filename]) {
            const separator = url.includes('?') ? '&' : '?';
            return `${url}${separator}v=${this.coreLibVersions[filename]}`;
        }
        
        // 业务代码使用动态版本号
        const separator = url.includes('?') ? '&' : '?';
        return `${url}${separator}v=${this.currentVersion}`;
    }
    
    /**
     * 批量替换页面中的版本号
     */
    updatePageVersions() {
        const scripts = document.querySelectorAll('script[src*="v=1755809999"]');
        const links = document.querySelectorAll('link[href*="v=1755809999"]');
        
        // 替换script标签
        scripts.forEach(script => {
            const oldSrc = script.src;
            const newSrc = oldSrc.replace(/v=1755809999/, `v=${this.currentVersion}`);
            
            const newScript = document.createElement('script');
            newScript.src = newSrc;
            newScript.onload = () => script.remove();
            document.head.appendChild(newScript);
        });
        
        // 替换link标签
        links.forEach(link => {
            const oldHref = link.href;
            const newHref = oldHref.replace(/v=1755809999/, `v=${this.currentVersion}`);
            link.href = newHref;
        });
        
        console.log(`版本号已更新: ${this.devMode ? '开发模式' : '生产模式'} v=${this.currentVersion}`);
    }
    
    /**
     * 动态加载脚本
     */
    loadScript(src, callback = null) {
        const script = document.createElement('script');
        script.src = this.getVersionedUrl(src);
        script.onload = callback;
        script.onerror = () => console.error(`脚本加载失败: ${src}`);
        document.head.appendChild(script);
        return script;
    }
    
    /**
     * 动态加载样式表
     */
    loadStylesheet(href, callback = null) {
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = this.getVersionedUrl(href);
        link.onload = callback;
        link.onerror = () => console.error(`样式表加载失败: ${href}`);
        document.head.appendChild(link);
        return link;
    }
}

// 创建全局实例
window.versionManager = new VersionManager();

// 暴露常用方法到全局
window.getVersionedUrl = (url) => window.versionManager.getVersionedUrl(url);

// 自动执行版本更新（如果页面已有旧版本号）
document.addEventListener('DOMContentLoaded', () => {
    if (document.querySelector('[src*="v=1755809999"], [href*="v=1755809999"]')) {
        console.log('检测到旧版本号，执行版本更新...');
        window.versionManager.updatePageVersions();
    }
});

console.log(`🏗️ 版本管理器已初始化 - ${window.versionManager.devMode ? '开发模式' : '生产模式'}`);