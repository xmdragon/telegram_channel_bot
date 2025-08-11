const { createApp } = Vue;
const { ElMessage, ElMessageBox } = ElementPlus;

createApp({
    data() {
        return {
            currentAdmin: {
                id: null,
                username: '',
                is_super_admin: false,
                permissions: [],
                last_login: null
            },
            admins: [],
            availablePermissions: {},
            
            // 修改密码对话框
            changePasswordDialog: {
                visible: false,
                loading: false,
                form: {
                    old_password: '',
                    new_password: '',
                    confirm_password: ''
                }
            },
            
            // 创建管理员对话框
            createAdminDialog: {
                visible: false,
                loading: false,
                form: {
                    username: '',
                    password: '',
                    is_super_admin: false,
                    permissions: []
                }
            },
            
            // 编辑管理员对话框
            editAdminDialog: {
                visible: false,
                loading: false,
                admin: null,
                form: {
                    is_active: true,
                    is_super_admin: false,
                    permissions: [],
                    password: ''
                }
            }
        };
    },
    
    async mounted() {
        // 初始化认证
        await authManager.initPageAuth();
        
        // 加载当前管理员信息
        await this.loadCurrentAdmin();
        
        // 如果是超级管理员，加载管理员列表和权限
        if (this.currentAdmin.is_super_admin) {
            await this.loadAdmins();
            await this.loadPermissions();
        }
    },
    
    methods: {
        // 加载当前管理员信息
        async loadCurrentAdmin() {
            try {
                const response = await axios.get('/api/auth/current');
                this.currentAdmin = response.data;
            } catch (error) {
                ElMessage.error('加载管理员信息失败');
                console.error(error);
            }
        },
        
        // 加载管理员列表
        async loadAdmins() {
            try {
                const response = await axios.get('/api/auth/admins');
                this.admins = response.data.admins;
                console.log('加载的管理员列表:', this.admins);
            } catch (error) {
                ElMessage.error('加载管理员列表失败');
                console.error(error);
            }
        },
        
        // 加载可用权限
        async loadPermissions() {
            try {
                const response = await axios.get('/api/auth/permissions');
                this.availablePermissions = response.data.permissions;
            } catch (error) {
                ElMessage.error('加载权限列表失败');
                console.error(error);
            }
        },
        
        // 显示修改密码对话框
        showChangePasswordDialog() {
            this.changePasswordDialog.form = {
                old_password: '',
                new_password: '',
                confirm_password: ''
            };
            this.changePasswordDialog.visible = true;
        },
        
        // 修改密码
        async changePassword() {
            const form = this.changePasswordDialog.form;
            
            // 验证表单
            if (!form.old_password || !form.new_password) {
                ElMessage.warning('请填写所有必填项');
                return;
            }
            
            if (form.new_password.length < 6) {
                ElMessage.warning('新密码长度至少6位');
                return;
            }
            
            if (form.new_password !== form.confirm_password) {
                ElMessage.warning('两次输入的新密码不一致');
                return;
            }
            
            this.changePasswordDialog.loading = true;
            try {
                await axios.post('/api/auth/change-password', {
                    old_password: form.old_password,
                    new_password: form.new_password
                });
                
                ElMessage.success('密码修改成功，请重新登录');
                this.changePasswordDialog.visible = false;
                
                // 2秒后跳转到登录页
                setTimeout(() => {
                    authManager.logout();
                }, 2000);
            } catch (error) {
                if (error.response?.data?.detail) {
                    ElMessage.error(error.response.data.detail);
                } else {
                    ElMessage.error('密码修改失败');
                }
            } finally {
                this.changePasswordDialog.loading = false;
            }
        },
        
        // 显示创建管理员对话框
        showCreateAdminDialog() {
            this.createAdminDialog.form = {
                username: '',
                password: '',
                is_super_admin: false,
                permissions: []
            };
            this.createAdminDialog.visible = true;
        },
        
        // 创建管理员
        async createAdmin() {
            const form = this.createAdminDialog.form;
            
            // 验证表单
            if (!form.username || !form.password) {
                ElMessage.warning('请填写用户名和密码');
                return;
            }
            
            if (form.password.length < 6) {
                ElMessage.warning('密码长度至少6位');
                return;
            }
            
            if (!form.is_super_admin && form.permissions.length === 0) {
                ElMessage.warning('普通管理员至少需要分配一个权限');
                return;
            }
            
            this.createAdminDialog.loading = true;
            try {
                await axios.post('/api/auth/admins', form);
                ElMessage.success('管理员创建成功');
                this.createAdminDialog.visible = false;
                await this.loadAdmins();
            } catch (error) {
                if (error.response?.data?.detail) {
                    ElMessage.error(error.response.data.detail);
                } else {
                    ElMessage.error('创建管理员失败');
                }
            } finally {
                this.createAdminDialog.loading = false;
            }
        },
        
        // 显示编辑管理员对话框
        showEditAdminDialog(admin) {
            this.editAdminDialog.admin = admin;
            this.editAdminDialog.form = {
                is_active: admin.is_active,
                is_super_admin: admin.is_super_admin,
                permissions: [...admin.permissions],
                password: ''
            };
            this.editAdminDialog.visible = true;
        },
        
        // 更新管理员
        async updateAdmin() {
            const form = this.editAdminDialog.form;
            const adminId = this.editAdminDialog.admin.id;
            
            // 如果设置了密码，验证长度
            if (form.password && form.password.length < 6) {
                ElMessage.warning('密码长度至少6位');
                return;
            }
            
            if (!form.is_super_admin && form.permissions.length === 0) {
                ElMessage.warning('普通管理员至少需要分配一个权限');
                return;
            }
            
            // 构建更新数据
            const updateData = {
                is_active: form.is_active,
                is_super_admin: form.is_super_admin,
                permissions: form.is_super_admin ? null : form.permissions
            };
            
            if (form.password) {
                updateData.password = form.password;
            }
            
            this.editAdminDialog.loading = true;
            try {
                await axios.put(`/api/auth/admins/${adminId}`, updateData);
                ElMessage.success('管理员信息更新成功');
                this.editAdminDialog.visible = false;
                await this.loadAdmins();
            } catch (error) {
                if (error.response?.data?.detail) {
                    ElMessage.error(error.response.data.detail);
                } else {
                    ElMessage.error('更新管理员失败');
                }
            } finally {
                this.editAdminDialog.loading = false;
            }
        },
        
        // 删除管理员
        async deleteAdmin(admin) {
            try {
                await ElMessageBox.confirm(
                    `确定要删除管理员 "${admin.username}" 吗？此操作不可恢复。`,
                    '删除确认',
                    {
                        confirmButtonText: '确定删除',
                        cancelButtonText: '取消',
                        type: 'warning'
                    }
                );
                
                await axios.delete(`/api/auth/admins/${admin.id}`);
                ElMessage.success('管理员删除成功');
                await this.loadAdmins();
            } catch (error) {
                if (error === 'cancel') return;
                
                if (error.response?.data?.detail) {
                    ElMessage.error(error.response.data.detail);
                } else {
                    ElMessage.error('删除管理员失败');
                }
            }
        },
        
        // 获取权限标签
        getPermissionLabel(permission) {
            const labels = {
                'messages.view': '查看消息',
                'messages.approve': '批准消息',
                'messages.reject': '拒绝消息',
                'config.view': '查看配置',
                'config.edit': '编辑配置',
                'training.view': '查看训练',
                'training.edit': '编辑训练',
                'system.view': '查看系统',
                'system.manage': '管理系统'
            };
            return labels[permission] || permission;
        },
        
        // 获取模块标签
        getModuleLabel(module) {
            const labels = {
                'messages': '消息管理',
                'config': '配置管理',
                'training': '训练管理',
                'system': '系统管理'
            };
            return labels[module] || module;
        },
        
        // 格式化日期时间
        formatDateTime(datetime) {
            if (!datetime) return '';
            const date = new Date(datetime);
            return date.toLocaleString('zh-CN', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit'
            });
        }
    },
    
    components: {
        'nav-bar': NavBar
    }
}).use(ElementPlus).mount('#app');