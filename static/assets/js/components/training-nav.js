// AI训练页面子导航组件
const TrainingNav = {
    props: {
        activeTab: {
            type: String,
            default: 'tail'
        }
    },
    
    data() {
        return {
            tabs: [
                { key: 'tail', label: '尾部过滤训练', url: API.pages.tailFilterManager },
                { key: 'ad', label: '广告向量管理', url: API.pages.adVectorManager },
                { key: 'promo', label: '推广链接训练', url: API.pages.promoManager },
                { key: 'separator', label: '分隔符配置', url: API.pages.separatorConfig },
                { key: 'media', label: '媒体文件管理', url: API.pages.mediaManager },
                { key: 'threshold', label: '阈值监控', url: API.pages.thresholdDashboard }
            ]
        };
    },
    
    template: `
        <div class="training-nav-container">
            <div class="training-nav-tabs">
                <div 
                    v-for="tab in tabs" 
                    :key="tab.key"
                    :class="['nav-tab', { active: activeTab === tab.key }]"
                    @click="handleSelect(tab)"
                >
                    {{ tab.label }}
                </div>
            </div>
        </div>
    `,
    
    methods: {
        handleSelect(tab) {
            // 获取当前URL
            const currentUrl = window.location.pathname + window.location.search;
            
            // 只在目标URL与当前URL不同时跳转
            if (tab.url && tab.url !== currentUrl) {
                window.location.href = tab.url;
            }
        }
    }
};

// 导出组件
if (typeof window !== 'undefined') {
    window.TrainingNav = TrainingNav;
}