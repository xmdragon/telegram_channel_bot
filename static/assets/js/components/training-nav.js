// AI训练页面子导航组件
const TrainingNav = {
    props: {
        activeTab: {
            type: String,
            default: 'tail'
        }
    },
    
    render() {
        const { h } = Vue;
        
        return h('div', { class: 'training-nav-container' }, [
            h('div', { class: 'training-nav-tabs' }, [
                h('div', {
                    class: ['nav-tab', { active: this.activeTab === 'tail' }],
                    onClick: () => this.handleSelect('tail')
                }, '尾部过滤训练'),
                
                h('div', {
                    class: ['nav-tab', { active: this.activeTab === 'ad' }],
                    onClick: () => this.handleSelect('ad')
                }, '广告检测训练'),
                
                h('div', {
                    class: ['nav-tab', { active: this.activeTab === 'separator' }],
                    onClick: () => this.handleSelect('separator')
                }, '分隔符配置'),
                
                h('div', {
                    class: ['nav-tab', { active: this.activeTab === 'data' }],
                    onClick: () => this.handleSelect('data')
                }, '数据管理'),
                
                h('div', {
                    class: ['nav-tab', { active: this.activeTab === 'media' }],
                    onClick: () => this.handleSelect('media')
                }, '媒体文件管理')
            ])
        ]);
    },
    
    methods: {
        handleSelect(key) {
            // 根据选择跳转到不同页面
            const routes = {
                'tail': '/static/tail_filter_manager.html',
                'ad': '/static/ad_training_manager.html',
                'separator': '/static/train.html?mode=separator',
                'data': '/static/train.html?mode=data',
                'media': '/static/media_manager.html'
            };
            
            const targetUrl = routes[key];
            
            // 获取当前URL
            const currentUrl = window.location.pathname + window.location.search;
            
            // 只在目标URL与当前URL不同时跳转
            if (targetUrl && targetUrl !== currentUrl) {
                window.location.href = targetUrl;
            }
        }
    }
};

// 导出组件
if (typeof window !== 'undefined') {
    window.TrainingNav = TrainingNav;
}