/* 尾部过滤训练组件 - 从train.js提取并增强 */

// 确保API配置可用
const API = window.API;

// 检查依赖
if (!window.Vue) {
    console.error('Vue 未加载!');
}

const { createApp } = Vue;

const app = createApp({
    data() {
        return {
            // 尾部过滤训练表单
            trainingForm: {
                original_message: '',
                tail_content: '',
                contentType: null
            },
            
            // 媒体组信息
            mediaGroupInfo: null,
            
            // 预览内容
            filteredPreview: '',
            
            // 状态控制
            submitting: false,
            loading: false,
            
            // 编辑模式
            editingSampleId: null
        };
    },
    
    methods: {
        // 移除媒体组标记
        removeMediaGroupInfo(content) {
            if (!content) return content;
            
            // 匹配媒体组标记模式: [📎 媒体组: ... | ID: ...]
            const mediaGroupPattern = /\[📎 媒体组:.*?\]/;
            const match = content.match(mediaGroupPattern);
            
            if (match) {
                this.mediaGroupInfo = match[0]; // 保存媒体组信息
                return content.replace(mediaGroupPattern, '').trim();
            }
            
            this.mediaGroupInfo = null;
            return content;
        },
        
        // 还原媒体组标记
        restoreMediaGroupInfo(content) {
            if (this.mediaGroupInfo && content) {
                return this.mediaGroupInfo + '\n\n' + content;
            }
            return content;
        },
        
        // 更新预览
        updatePreview() {
            if (this.trainingForm.original_message && this.trainingForm.tail_content) {
                const original = this.trainingForm.original_message;
                const tail = this.trainingForm.tail_content;
                this.filteredPreview = original.replace(tail, '').trim();
            } else {
                this.filteredPreview = '';
            }
        },
        
        // 提交训练样本
        async submitTraining() {
            if (!this.trainingForm.original_message || !this.trainingForm.tail_content) {
                window.SimpleUI.Message.warning('请填写完整的训练内容');
                return;
            }
            
            this.submitting = true;
            try {
                // 提交时还原媒体组信息
                const originalMessage = this.restoreMediaGroupInfo(this.trainingForm.original_message);
                
                if (this.editingSampleId) {
                    // 更新现有样本
                    const response = await axios.put(API.training.tailFilterSampleById(this.editingSampleId), {
                        tail_content: this.trainingForm.tail_content,
                        original_message: originalMessage
                    });
                    window.SimpleUI.Message.success('训练样本更新成功！');
                } else {
                    // 添加新样本
                    const response = await axios.post(API.training.tailFilterSamples, {
                        original_message: originalMessage,
                        tail_content: this.trainingForm.tail_content
                    });
                    window.SimpleUI.Message.success('训练样本提交成功！');
                }
                
                this.clearForm();
            } catch (error) {
                console.error('提交训练样本失败:', error);
                window.SimpleUI.Message.error(error.response?.data?.detail || '提交失败');
            } finally {
                this.submitting = false;
            }
        },
        
        // 清空表单
        clearForm() {
            this.trainingForm = {
                original_message: '',
                tail_content: '',
                contentType: null
            };
            this.filteredPreview = '';
            this.editingSampleId = null;
            this.mediaGroupInfo = null; // 清除媒体组信息
            
            // 清除URL参数
            if (window.location.search) {
                window.history.replaceState({}, document.title, window.location.pathname);
            }
        },
        
        // 加载单个样本数据（用于编辑）
        async loadSample(sampleId) {
            try {
                this.loading = true;
                const response = await axios.get(API.training.tailFilterSampleById(sampleId));
                
                if (response.data.success && response.data.sample) {
                    const sample = response.data.sample;
                    
                    // 填充表单 - 移除媒体组标记
                    this.trainingForm.tail_content = sample.tail_part || '';
                    this.trainingForm.original_message = this.removeMediaGroupInfo(sample.original_message || '');
                    this.trainingForm.contentType = 'original';
                    
                    // 设置编辑模式
                    this.editingSampleId = sampleId;
                    
                    // 更新预览
                    this.updatePreview();
                    
                    window.SimpleUI.Message.success('样本数据已加载，可以进行编辑');
                } else {
                    window.SimpleUI.Message.warning('样本不存在或已被删除');
                }
            } catch (error) {
                console.error('加载样本失败:', error);
                if (error.response && error.response.status === 404) {
                    window.SimpleUI.Message.warning('样本不存在');
                } else {
                    window.SimpleUI.Message.error('加载样本失败');
                }
            } finally {
                this.loading = false;
            }
        },
        
        // 检查URL参数
        checkUrlParams() {
            const params = new URLSearchParams(window.location.search);
            const sampleId = params.get('sampleId');
            const messageId = params.get('message_id');
            
            if (sampleId) {
                this.loadSample(parseInt(sampleId));
            } else if (messageId) {
                // 从index页面跳转来的消息ID参数
                this.loadMessageForTraining(messageId);
            }
        },
        
        // 从消息ID加载数据用于训练
        async loadMessageForTraining(messageId) {
            try {
                this.loading = true;
                const response = await axios.get(API.messages.getById(encodeURIComponent(messageId)));
                
                if (response.data.success && response.data.data) {
                    const message = response.data.data;
                    
                    // 优先使用filtered_content，如果没有则使用原始content
                    const content = message.filtered_content || message.content;
                    const useFiltered = !!message.filtered_content;
                    
                    if (content) {
                        // 移除媒体组标记后填充
                        this.trainingForm.original_message = this.removeMediaGroupInfo(content);
                        this.trainingForm.contentType = useFiltered ? 'filtered' : 'original';
                        this.updatePreview();
                        
                        const contentTypeText = useFiltered ? '过滤后内容' : '原始内容';
                        window.SimpleUI.Message.success(`已自动填充${contentTypeText}，请标记出需要过滤的尾部内容`);
                        
                        // 焦点设置到尾部内容输入框
                        setTimeout(() => {
                            const tailInput = document.querySelector('textarea[placeholder*="尾部内容"]');
                            if (tailInput) {
                                tailInput.focus();
                            }
                        }, 100);
                    } else {
                        window.SimpleUI.Message.warning('消息内容为空');
                    }
                } else {
                    window.SimpleUI.Message.warning('消息不存在或已被删除');
                }
            } catch (error) {
                console.error('加载消息失败:', error);
                window.SimpleUI.Message.error('加载消息失败');
            } finally {
                this.loading = false;
            }
        }
    },
    
    async mounted() {
        // 检查URL参数
        this.checkUrlParams();
        
        // 设置axios拦截器
        if (typeof setupAxiosAuth === 'function') {
            setupAxiosAuth();
        }
    }
});

// 注册导航栏组件
app.component('nav-bar', window.NavBar);
app.component('training-nav', window.TrainingNav);

// 挂载应用
app.mount('#app');