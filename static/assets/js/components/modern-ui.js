// Modern UI Vue Components
const ModernUI = {
    // Button Component
    Button: {
        props: {
            type: { type: String, default: 'primary' },
            size: { type: String, default: '' },
            disabled: { type: Boolean, default: false },
            loading: { type: Boolean, default: false }
        },
        template: `
            <button 
                :class="['btn', 'btn-' + type, size ? 'btn-' + size : '']"
                :disabled="disabled || loading"
                @click="$emit('click', $event)">
                <span v-if="loading" class="spinner-small"></span>
                <slot></slot>
            </button>
        `
    },

    // Card Component
    Card: {
        props: {
            shadow: { type: String, default: 'always' }
        },
        template: `
            <div class="card">
                <div v-if="$slots.header" class="card-header">
                    <slot name="header"></slot>
                </div>
                <div class="card-body">
                    <slot></slot>
                </div>
            </div>
        `
    },

    // Input Component
    Input: {
        props: {
            modelValue: [String, Number],
            placeholder: String,
            type: { type: String, default: 'text' },
            disabled: Boolean,
            clearable: Boolean
        },
        emits: ['update:modelValue', 'input', 'clear'],
        template: `
            <div class="input-wrapper">
                <input 
                    :type="type"
                    :value="modelValue"
                    :placeholder="placeholder"
                    :disabled="disabled"
                    class="form-input"
                    @input="$emit('update:modelValue', $event.target.value)"
                />
                <span 
                    v-if="clearable && modelValue" 
                    class="input-clear"
                    @click="$emit('update:modelValue', ''); $emit('clear')">
                    ×
                </span>
            </div>
        `
    },

    // Select Component
    Select: {
        props: {
            modelValue: [String, Number],
            options: Array,
            placeholder: String,
            disabled: Boolean
        },
        emits: ['update:modelValue', 'change'],
        template: `
            <select 
                :value="modelValue"
                :disabled="disabled"
                class="form-select"
                @change="$emit('update:modelValue', $event.target.value); $emit('change', $event.target.value)">
                <option v-if="placeholder" value="" disabled>{{ placeholder }}</option>
                <option 
                    v-for="option in options" 
                    :key="option.value"
                    :value="option.value">
                    {{ option.label }}
                </option>
            </select>
        `
    },

    // Checkbox Component
    Checkbox: {
        props: {
            modelValue: Boolean,
            label: String,
            disabled: Boolean
        },
        emits: ['update:modelValue', 'change'],
        template: `
            <label class="checkbox-wrapper">
                <input 
                    type="checkbox"
                    :checked="modelValue"
                    :disabled="disabled"
                    @change="$emit('update:modelValue', $event.target.checked); $emit('change', $event.target.checked)"
                />
                <span class="checkbox-label">{{ label }}</span>
            </label>
        `
    },

    // Tag Component
    Tag: {
        props: {
            type: { type: String, default: 'primary' },
            closable: Boolean
        },
        emits: ['close'],
        template: `
            <span :class="['tag', 'tag-' + type]">
                <slot></slot>
                <span v-if="closable" class="tag-close" @click="$emit('close')">×</span>
            </span>
        `
    },

    // Alert Component
    Alert: {
        props: {
            type: { type: String, default: 'info' },
            title: String,
            closable: Boolean,
            showIcon: { type: Boolean, default: true }
        },
        emits: ['close'],
        data() {
            return {
                visible: true
            }
        },
        template: `
            <div v-if="visible" :class="['alert', 'alert-' + type]">
                <span v-if="showIcon" class="alert-icon">{{ getIcon() }}</span>
                <div class="alert-content">
                    <div v-if="title" class="alert-title">{{ title }}</div>
                    <slot></slot>
                </div>
                <span v-if="closable" class="alert-close" @click="visible = false; $emit('close')">×</span>
            </div>
        `,
        methods: {
            getIcon() {
                const icons = {
                    info: 'ℹ',
                    success: '✓',
                    warning: '⚠',
                    danger: '✕'
                };
                return icons[this.type] || 'ℹ';
            }
        }
    },

    // Modal/Dialog Component
    Dialog: {
        props: {
            modelValue: Boolean,
            title: String,
            width: { type: String, default: '500px' }
        },
        emits: ['update:modelValue'],
        template: `
            <teleport to="body">
                <div v-if="modelValue" class="modal-overlay" @click.self="$emit('update:modelValue', false)">
                    <div class="modal" :style="{ maxWidth: width }">
                        <div class="modal-header">
                            <h3 class="modal-title">{{ title }}</h3>
                            <span class="modal-close" @click="$emit('update:modelValue', false)">×</span>
                        </div>
                        <div class="modal-body">
                            <slot></slot>
                        </div>
                        <div v-if="$slots.footer" class="modal-footer">
                            <slot name="footer"></slot>
                        </div>
                    </div>
                </div>
            </teleport>
        `
    },

    // Loading Component
    Loading: {
        props: {
            text: { type: String, default: '加载中...' }
        },
        template: `
            <div class="loading">
                <div class="spinner"></div>
                <div v-if="text" class="loading-text">{{ text }}</div>
            </div>
        `
    },

    // Empty Component
    Empty: {
        props: {
            description: { type: String, default: '暂无数据' },
            image: String
        },
        template: `
            <div class="empty-state">
                <div class="empty-icon">{{ image || '📭' }}</div>
                <div class="empty-description">{{ description }}</div>
                <div v-if="$slots.default" class="empty-extra">
                    <slot></slot>
                </div>
            </div>
        `
    },

    // Pagination Component
    Pagination: {
        props: {
            current: { type: Number, default: 1 },
            total: { type: Number, default: 0 },
            pageSize: { type: Number, default: 10 }
        },
        emits: ['change'],
        computed: {
            totalPages() {
                return Math.ceil(this.total / this.pageSize);
            },
            pages() {
                const pages = [];
                const maxButtons = 7;
                
                if (this.totalPages <= maxButtons) {
                    for (let i = 1; i <= this.totalPages; i++) {
                        pages.push(i);
                    }
                } else {
                    if (this.current <= 3) {
                        for (let i = 1; i <= 5; i++) {
                            pages.push(i);
                        }
                        pages.push('...');
                        pages.push(this.totalPages);
                    } else if (this.current >= this.totalPages - 2) {
                        pages.push(1);
                        pages.push('...');
                        for (let i = this.totalPages - 4; i <= this.totalPages; i++) {
                            pages.push(i);
                        }
                    } else {
                        pages.push(1);
                        pages.push('...');
                        for (let i = this.current - 1; i <= this.current + 1; i++) {
                            pages.push(i);
                        }
                        pages.push('...');
                        pages.push(this.totalPages);
                    }
                }
                
                return pages;
            }
        },
        template: `
            <div class="pagination">
                <button 
                    class="page-item"
                    :disabled="current === 1"
                    @click="$emit('change', current - 1)">
                    上一页
                </button>
                
                <button 
                    v-for="page in pages"
                    :key="page"
                    :class="['page-item', { active: page === current, disabled: page === '...' }]"
                    :disabled="page === '...'"
                    @click="page !== '...' && $emit('change', page)">
                    {{ page }}
                </button>
                
                <button 
                    class="page-item"
                    :disabled="current === totalPages"
                    @click="$emit('change', current + 1)">
                    下一页
                </button>
            </div>
        `
    },

    // Table Component
    Table: {
        props: {
            data: Array,
            columns: Array,
            stripe: Boolean,
            border: Boolean
        },
        template: `
            <div class="table-container">
                <table class="table" :class="{ stripe, border }">
                    <thead>
                        <tr>
                            <th v-for="col in columns" :key="col.prop">
                                {{ col.label }}
                            </th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr v-for="(row, index) in data" :key="index">
                            <td v-for="col in columns" :key="col.prop">
                                <slot :name="col.prop" :row="row">
                                    {{ row[col.prop] }}
                                </slot>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
        `
    },

    // Switch Component
    Switch: {
        props: {
            modelValue: Boolean,
            disabled: Boolean,
            activeText: String,
            inactiveText: String
        },
        emits: ['update:modelValue', 'change'],
        template: `
            <label class="switch-wrapper">
                <span v-if="inactiveText" class="switch-text">{{ inactiveText }}</span>
                <div class="switch" :class="{ active: modelValue, disabled }">
                    <input 
                        type="checkbox"
                        :checked="modelValue"
                        :disabled="disabled"
                        @change="$emit('update:modelValue', $event.target.checked); $emit('change', $event.target.checked)"
                    />
                    <span class="switch-slider"></span>
                </div>
                <span v-if="activeText" class="switch-text">{{ activeText }}</span>
            </label>
        `
    },

    // Message Component (programmatic)
    Message: {
        success(message) {
            this.show(message, 'success');
        },
        error(message) {
            this.show(message, 'danger');
        },
        warning(message) {
            this.show(message, 'warning');
        },
        info(message) {
            this.show(message, 'info');
        },
        show(message, type = 'info') {
            const container = document.getElementById('message-container') || this.createContainer();
            
            const messageEl = document.createElement('div');
            messageEl.className = `message message-${type} fade-in`;
            messageEl.innerHTML = `
                <span class="message-icon">${this.getIcon(type)}</span>
                <span class="message-content">${message}</span>
            `;
            
            container.appendChild(messageEl);
            
            setTimeout(() => {
                messageEl.classList.add('fade-out');
                setTimeout(() => {
                    container.removeChild(messageEl);
                }, 300);
            }, 3000);
        },
        createContainer() {
            const container = document.createElement('div');
            container.id = 'message-container';
            container.style.cssText = `
                position: fixed;
                top: 20px;
                left: 50%;
                transform: translateX(-50%);
                z-index: 9999;
                display: flex;
                flex-direction: column;
                gap: 10px;
            `;
            document.body.appendChild(container);
            return container;
        },
        getIcon(type) {
            const icons = {
                success: '✓',
                danger: '✕',
                warning: '⚠',
                info: 'ℹ'
            };
            return icons[type] || 'ℹ';
        }
    }
};

// Add required CSS for components
const style = document.createElement('style');
style.textContent = `
    /* Input wrapper */
    .input-wrapper {
        position: relative;
        display: inline-block;
        width: 100%;
    }
    
    .input-clear {
        position: absolute;
        right: 10px;
        top: 50%;
        transform: translateY(-50%);
        cursor: pointer;
        font-size: 20px;
        color: var(--text-tertiary);
        transition: color 0.3s;
    }
    
    .input-clear:hover {
        color: var(--text-secondary);
    }
    
    /* Checkbox */
    .checkbox-wrapper {
        display: inline-flex;
        align-items: center;
        cursor: pointer;
        user-select: none;
    }
    
    .checkbox-wrapper input[type="checkbox"] {
        margin-right: 8px;
    }
    
    .checkbox-label {
        color: var(--text-primary);
    }
    
    /* Switch */
    .switch-wrapper {
        display: inline-flex;
        align-items: center;
        gap: 8px;
    }
    
    .switch {
        position: relative;
        display: inline-block;
        width: 44px;
        height: 24px;
    }
    
    .switch input {
        opacity: 0;
        width: 0;
        height: 0;
    }
    
    .switch-slider {
        position: absolute;
        cursor: pointer;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background-color: var(--border-color);
        border-radius: 24px;
        transition: 0.3s;
    }
    
    .switch-slider:before {
        position: absolute;
        content: "";
        height: 18px;
        width: 18px;
        left: 3px;
        bottom: 3px;
        background-color: white;
        border-radius: 50%;
        transition: 0.3s;
    }
    
    .switch.active .switch-slider {
        background-color: var(--primary-color);
    }
    
    .switch.active .switch-slider:before {
        transform: translateX(20px);
    }
    
    .switch.disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }
    
    .switch-text {
        font-size: 14px;
        color: var(--text-secondary);
    }
    
    /* Tag close button */
    .tag-close {
        margin-left: 4px;
        cursor: pointer;
        font-weight: bold;
    }
    
    /* Alert close button */
    .alert {
        position: relative;
        display: flex;
        align-items: flex-start;
        gap: 12px;
    }
    
    .alert-icon {
        font-size: 18px;
        flex-shrink: 0;
    }
    
    .alert-content {
        flex: 1;
    }
    
    .alert-title {
        font-weight: 600;
        margin-bottom: 4px;
    }
    
    .alert-close {
        cursor: pointer;
        font-size: 20px;
        line-height: 1;
        opacity: 0.5;
        transition: opacity 0.3s;
    }
    
    .alert-close:hover {
        opacity: 1;
    }
    
    /* Modal close button */
    .modal-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    
    .modal-close {
        cursor: pointer;
        font-size: 24px;
        line-height: 1;
        opacity: 0.5;
        transition: opacity 0.3s;
    }
    
    .modal-close:hover {
        opacity: 1;
    }
    
    /* Loading text */
    .loading-text {
        margin-top: 12px;
        color: var(--text-secondary);
        font-size: 14px;
    }
    
    /* Small spinner for buttons */
    .spinner-small {
        display: inline-block;
        width: 14px;
        height: 14px;
        border: 2px solid rgba(255, 255, 255, 0.3);
        border-top-color: white;
        border-radius: 50%;
        animation: spin 0.8s linear infinite;
    }
    
    /* Message toast */
    .message {
        padding: 12px 20px;
        border-radius: 8px;
        background: white;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
        display: flex;
        align-items: center;
        gap: 8px;
        min-width: 200px;
        max-width: 400px;
    }
    
    .message-success {
        border-left: 4px solid var(--success-color);
    }
    
    .message-danger {
        border-left: 4px solid var(--danger-color);
    }
    
    .message-warning {
        border-left: 4px solid var(--warning-color);
    }
    
    .message-info {
        border-left: 4px solid var(--info-color);
    }
    
    .message-icon {
        font-size: 18px;
    }
    
    .message-success .message-icon {
        color: var(--success-color);
    }
    
    .message-danger .message-icon {
        color: var(--danger-color);
    }
    
    .message-warning .message-icon {
        color: var(--warning-color);
    }
    
    .message-info .message-icon {
        color: var(--info-color);
    }
    
    .message-content {
        flex: 1;
        color: var(--text-primary);
    }
    
    .fade-out {
        animation: fadeOut 0.3s ease-out forwards;
    }
    
    @keyframes fadeOut {
        to {
            opacity: 0;
            transform: translateY(-10px);
        }
    }
`;
document.head.appendChild(style);

// Export for use
window.ModernUI = ModernUI;