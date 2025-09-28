// 训练中心页面子导航组件
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
                { key: 'separator', label: '分隔符配置', url: API.pages.separatorConfig },
                { key: 'text', label: '文本过滤', url: API.pages.textFilter },
                { key: 'ad', label: '关键词管理', url: API.pages.adVectorManager },
                { key: 'telegram', label: 'Telegram消息', url: API.pages.telegramMessage },
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