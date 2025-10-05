/**
 * 消息发布页面
 *
 * 功能：
 * - Markdown编辑和实时预览
 * - 媒体文件上传（最多10个）
 * - Emoji快速选择
 * - 自动添加频道落款
 */

const { createApp } = Vue;

createApp({
    components: {
        'nav-bar': window.NavBar
    },
    data() {
        return {
            content: '',
            signature: '',
            mediaFiles: [],
            isPublishing: false,
            showEmojiPicker: false,
            emojiCategories: [],
            currentEmojiTab: ''
        };
    },
    computed: {
        currentEmojis() {
            const category = this.emojiCategories.find(c => c.name === this.currentEmojiTab);
            return category ? category.emojis : [];
        },
        renderedContent() {
            if (!this.content.trim()) return '';
            return this.renderMarkdown(this.content);
        }
    },
    async mounted() {
        await this.loadSignature();
        await this.loadEmojis();
    },
    methods: {
        async loadSignature() {
            try {
                const response = await axios.get(API.config.get);
                const signatureConfig = response.data['target.signature'];
                this.signature = signatureConfig ? signatureConfig.value : '';
            } catch (error) {
                console.error('加载频道落款失败:', error);
            }
        },
        async loadEmojis() {
            try {
                const response = await axios.get(API.publish.emojiList);
                this.emojiCategories = response.data.categories || [];
                if (this.emojiCategories.length > 0) {
                    this.currentEmojiTab = this.emojiCategories[0].name;
                }
            } catch (error) {
                console.error('加载emoji列表失败:', error);
                SimpleUI.showMessage('加载emoji列表失败', 'error');
            }
        },
        insertMarkdown(before, after) {
            const editor = this.$refs.editor;
            const start = editor.selectionStart;
            const end = editor.selectionEnd;
            const selectedText = this.content.substring(start, end);
            const newText = before + selectedText + after;

            this.content = this.content.substring(0, start) + newText + this.content.substring(end);

            this.$nextTick(() => {
                editor.focus();
                editor.setSelectionRange(start + before.length, start + before.length + selectedText.length);
            });
        },
        insertLink() {
            const url = prompt('请输入链接地址:');
            if (url) {
                const text = prompt('请输入链接文本:', url);
                const editor = this.$refs.editor;
                const start = editor.selectionStart;
                const linkText = `[${text || url}](${url})`;

                this.content = this.content.substring(0, start) + linkText + this.content.substring(start);

                this.$nextTick(() => {
                    editor.focus();
                    editor.setSelectionRange(start + linkText.length, start + linkText.length);
                });
            }
        },
        insertEmoji(emoji) {
            const editor = this.$refs.editor;
            const start = editor.selectionStart;
            this.content = this.content.substring(0, start) + emoji + this.content.substring(start);

            this.$nextTick(() => {
                editor.focus();
                editor.setSelectionRange(start + emoji.length, start + emoji.length);
            });
        },
        handleKeyDown(e) {
            // Ctrl+B 加粗
            if (e.ctrlKey && e.key === 'b') {
                e.preventDefault();
                this.insertMarkdown('**', '**');
            }
            // Ctrl+I 斜体
            if (e.ctrlKey && e.key === 'i') {
                e.preventDefault();
                this.insertMarkdown('*', '*');
            }
        },
        async handleFileSelect(e) {
            const files = Array.from(e.target.files);
            await this.uploadFiles(files);
        },
        async handleDrop(e) {
            const files = Array.from(e.dataTransfer.files);
            await this.uploadFiles(files);
        },
        async uploadFiles(files) {
            if (this.mediaFiles.length + files.length > 10) {
                SimpleUI.showMessage('媒体文件不能超过10个', 'warning');
                return;
            }

            for (const file of files) {
                await this.uploadSingleFile(file);
            }
        },
        async uploadSingleFile(file) {
            try {
                const formData = new FormData();
                formData.append('file', file);

                const response = await axios.post(API.publish.uploadMedia, formData, {
                    headers: { 'Content-Type': 'multipart/form-data' }
                });

                this.mediaFiles.push(response.data);
                SimpleUI.showMessage(`上传成功: ${file.name}`, 'success');
            } catch (error) {
                console.error('上传失败:', error);
                const msg = error.response?.data?.detail || `上传失败: ${file.name}`;
                SimpleUI.showMessage(msg, 'error');
            }
        },
        async removeMedia(index) {
            const file = this.mediaFiles[index];
            try {
                await axios.delete(API.publish.deleteMedia(file.file_id));
                this.mediaFiles.splice(index, 1);
            } catch (error) {
                console.error('删除媒体失败:', error);
                SimpleUI.showMessage('删除失败', 'error');
            }
        },
        async publishMessage() {
            if (!this.content.trim()) {
                SimpleUI.showMessage('请输入消息内容', 'warning');
                return;
            }

            const confirmed = await SimpleUI.confirm(
                '确认发布',
                `确定要发布这条消息吗？${this.mediaFiles.length > 0 ? `\n包含${this.mediaFiles.length}个媒体文件` : ''}`
            );

            if (!confirmed) return;

            this.isPublishing = true;
            try {
                const response = await axios.post(API.publish.sendMessage, {
                    content: this.content,
                    media_files: this.mediaFiles.map(f => f.file_id),
                    parse_mode: 'Markdown'
                });

                SimpleUI.showMessage('消息发布成功！', 'success');
                this.clearAll();
            } catch (error) {
                console.error('发布失败:', error);
                const msg = error.response?.data?.detail || '发布失败';
                SimpleUI.showMessage(msg, 'error');
            } finally {
                this.isPublishing = false;
            }
        },
        clearAll() {
            this.content = '';
            this.mediaFiles.forEach(file => {
                axios.delete(API.publish.deleteMedia(file.file_id)).catch(() => {});
            });
            this.mediaFiles = [];
            this.showEmojiPicker = false;
        },
        formatFileSize(bytes) {
            if (bytes < 1024) return bytes + ' B';
            if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
            return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
        },
        renderMarkdown(text) {
            return text
                .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
                .replace(/\*(.+?)\*/g, '<i>$1</i>')
                .replace(/~~(.+?)~~/g, '<s>$1</s>')
                .replace(/`(.+?)`/g, '<code>$1</code>')
                .replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2" target="_blank">$1</a>')
                .replace(/\n/g, '<br>');
        }
    }
}).mount('#app');
