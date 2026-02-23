#!/bin/bash
# 部署脚本 - 在本地执行
# 用法: ./tools/deploy.sh [init|rollback|sync]
#   无参数 = 增量部署
#   init    = 首次全量部署（安装依赖 + 部署代码）
#   rollback = 回滚到上一版本
#   sync    = 只同步配置不重启
set -euo pipefail

# ============================================================
# 配置
# ============================================================
REMOTE="tcb"
REMOTE_DIR="/opt/tcb"
DEPLOY_BRANCH="worktree-sqlite-migration"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DEPLOY_COMMIT_FILE="$PROJECT_DIR/.deploy_commit"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
RELEASE_NAME="v${TIMESTAMP}"
MAX_RELEASES=5

# 共享数据目录 - 部署时创建符号链接
SHARED_LINKS=(
    "data:shared/data"
    "logs:shared/logs"
    "temp_media:shared/temp_media"
)

# 需要从本地复制到服务器的敏感文件
CONFIG_FILES=(
    "data/config/system.json"
    "data/config/channels.json"
    "data/config/admins.json"
    "data/config/telegram.json"
)

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log_ok()   { echo -e "${GREEN}✅ $1${NC}"; }
log_fail() { echo -e "${RED}❌ $1${NC}"; }
log_info() { echo -e "${YELLOW}➜ $1${NC}"; }
log_step() { echo -e "${CYAN}━━━ $1 ━━━${NC}"; }

remote_exec() { ssh "$REMOTE" "$1"; }
remote_check() { ssh "$REMOTE" "$1" 2>/dev/null; }

# ============================================================
# 共享目录符号链接
# ============================================================
create_shared_links() {
    local release_dir="$1"
    for link_def in "${SHARED_LINKS[@]}"; do
        local src="${link_def%%:*}"
        local target="${link_def##*:}"
        remote_exec "rm -rf ${release_dir}/${src} && ln -sf ${REMOTE_DIR}/${target} ${release_dir}/${src}"
    done
    # .env 链接
    remote_exec "ln -sf ${REMOTE_DIR}/shared/.env ${release_dir}/.env 2>/dev/null || true"
    # telegram sessions 链接
    remote_exec "ln -sf ${REMOTE_DIR}/shared/telegram_sessions ${release_dir}/telegram_sessions 2>/dev/null || true"
}

# ============================================================
# 清理旧版本（保留最近 N 个）
# ============================================================
cleanup_old_releases() {
    log_info "清理旧版本（保留最近 ${MAX_RELEASES} 个）"
    remote_exec "cd ${REMOTE_DIR}/releases && ls -1dt v* 2>/dev/null | tail -n +$((MAX_RELEASES + 1)) | xargs rm -rf 2>/dev/null || true"
}

# ============================================================
# 记录部署历史
# ============================================================
log_deploy() {
    local action="$1"
    local detail="$2"
    remote_exec "echo '$(date +%Y-%m-%d\ %H:%M:%S) | ${action} | ${detail}' >> ${REMOTE_DIR}/deploy_history.log"
}

# ============================================================
# init: 首次全量部署
# ============================================================
do_init() {
    log_step "首次全量部署"

    # 1. 上传并执行服务器初始化脚本
    log_info "上传服务器初始化脚本"
    scp "$SCRIPT_DIR/deploy_server_init.sh" "${REMOTE}:/tmp/deploy_server_init.sh"
    log_info "执行服务器初始化（这可能需要几分钟）"
    ssh "$REMOTE" "bash /tmp/deploy_server_init.sh"

    # 2. 全量打包
    log_info "打包项目文件"
    cd "$PROJECT_DIR"
    local archive="/tmp/tcb-deploy-${TIMESTAMP}.tar.gz"
    git archive HEAD | gzip > "$archive"
    local size
    size=$(du -h "$archive" | cut -f1)
    log_ok "打包完成: ${size}"

    # 3. 上传
    log_info "上传到服务器"
    scp "$archive" "${REMOTE}:/tmp/tcb-deploy.tar.gz"
    rm -f "$archive"

    # 4. 解压到 release 目录
    local release_dir="${REMOTE_DIR}/releases/${RELEASE_NAME}"
    log_info "部署到 ${release_dir}"
    remote_exec "mkdir -p ${release_dir} && tar -xzf /tmp/tcb-deploy.tar.gz -C ${release_dir} && rm -f /tmp/tcb-deploy.tar.gz"

    # 5. 创建共享目录链接
    create_shared_links "$release_dir"

    # 6. 切换 current 链接
    remote_exec "ln -sfn ${release_dir} ${REMOTE_DIR}/current"
    log_ok "current -> ${RELEASE_NAME}"

    # 7. 上传敏感配置文件
    log_info "上传配置文件"
    for config in "${CONFIG_FILES[@]}"; do
        local local_file="${PROJECT_DIR}/${config}"
        if [ -f "$local_file" ]; then
            scp "$local_file" "${REMOTE}:${REMOTE_DIR}/shared/${config}"
            log_ok "  ${config}"
        else
            log_info "  跳过 ${config}（本地不存在）"
        fi
    done

    # 上传 .env（优先用 .env，回退到 .env.example）
    if [ -f "$PROJECT_DIR/.env" ]; then
        scp "$PROJECT_DIR/.env" "${REMOTE}:${REMOTE_DIR}/shared/.env"
        log_ok "  .env（从 .env）"
    elif [ -f "$PROJECT_DIR/.env.example" ]; then
        scp "$PROJECT_DIR/.env.example" "${REMOTE}:${REMOTE_DIR}/shared/.env"
        log_ok "  .env（从 .env.example）"
    else
        log_fail "  .env 和 .env.example 都不存在！"
        exit 1
    fi

    # 8. 安装 Python 依赖
    log_info "安装 Python 依赖"
    remote_exec "${REMOTE_DIR}/shared/venv/bin/pip install -r ${REMOTE_DIR}/current/requirements.txt -q"
    log_ok "依赖安装完成"

    # 9. 启动服务
    log_info "启动服务"
    remote_exec "supervisorctl reread && supervisorctl update && supervisorctl restart tcb:"
    sleep 3

    # 10. 记录部署 commit
    local commit
    commit=$(git rev-parse HEAD)
    echo "$commit" > "$DEPLOY_COMMIT_FILE"
    remote_exec "echo '${commit}' > ${REMOTE_DIR}/.deploy_commit"
    log_deploy "init" "commit=${commit} release=${RELEASE_NAME}"

    # 11. 清理
    cleanup_old_releases

    echo ""
    log_step "部署完成"
    echo ""
    remote_exec "supervisorctl status tcb:"
    echo ""
    echo "验证:"
    echo "  curl http://tcb.gxfc.life/api/health"
    echo "  curl -I http://tcb.gxfc.life/static/login.html"
}

# ============================================================
# 增量部署（默认）
# ============================================================
do_deploy() {
    log_step "增量部署"
    cd "$PROJECT_DIR"

    # 获取上次部署的 commit
    if [ ! -f "$DEPLOY_COMMIT_FILE" ]; then
        log_fail "找不到 .deploy_commit，请先执行 init"
        exit 1
    fi
    local last_commit
    last_commit=$(cat "$DEPLOY_COMMIT_FILE")
    local current_commit
    current_commit=$(git rev-parse HEAD)

    if [ "$last_commit" = "$current_commit" ]; then
        log_ok "无变化，跳过部署"
        exit 0
    fi

    # 识别变化文件
    local changed_files
    changed_files=$(git diff --name-only "$last_commit" HEAD)
    local file_count
    file_count=$(echo "$changed_files" | grep -c '.' || true)

    if [ "$file_count" -eq 0 ]; then
        log_ok "无文件变化，跳过部署"
        exit 0
    fi

    log_info "发现 ${file_count} 个文件变化"
    echo "$changed_files" | head -20
    [ "$file_count" -gt 20 ] && echo "... 还有 $((file_count - 20)) 个文件"

    # 判断是否需要全量部署（超过 50 个文件变化用全量更高效）
    if [ "$file_count" -gt 50 ]; then
        log_info "变化文件过多（${file_count}），使用全量部署"
        local archive="/tmp/tcb-deploy-${TIMESTAMP}.tar.gz"
        git archive HEAD | gzip > "$archive"

        local release_dir="${REMOTE_DIR}/releases/${RELEASE_NAME}"
        scp "$archive" "${REMOTE}:/tmp/tcb-deploy.tar.gz"
        rm -f "$archive"
        remote_exec "mkdir -p ${release_dir} && tar -xzf /tmp/tcb-deploy.tar.gz -C ${release_dir} && rm -f /tmp/tcb-deploy.tar.gz"
        create_shared_links "$release_dir"
        remote_exec "ln -sfn ${release_dir} ${REMOTE_DIR}/current"
        log_ok "全量部署到 ${RELEASE_NAME}"
    else
        # 增量打包
        local archive="/tmp/tcb-incremental-${TIMESTAMP}.tar.gz"
        echo "$changed_files" | git archive HEAD --files-from=- | gzip > "$archive"
        local size
        size=$(du -h "$archive" | cut -f1)
        log_info "增量包: ${size}"

        scp "$archive" "${REMOTE}:/tmp/tcb-incremental.tar.gz"
        rm -f "$archive"
        remote_exec "tar -xzf /tmp/tcb-incremental.tar.gz -C ${REMOTE_DIR}/current/ && rm -f /tmp/tcb-incremental.tar.gz"
        log_ok "增量文件已更新"
    fi

    # 判断是否需要重启
    local need_restart=false
    local need_pip=false

    if echo "$changed_files" | grep -q 'requirements.txt'; then
        need_pip=true
        need_restart=true
    fi

    if echo "$changed_files" | grep -qE '\.(py)$'; then
        need_restart=true
    fi

    if [ "$need_pip" = true ]; then
        log_info "更新 Python 依赖"
        remote_exec "${REMOTE_DIR}/shared/venv/bin/pip install -r ${REMOTE_DIR}/current/requirements.txt -q"
        log_ok "依赖更新完成"
    fi

    if [ "$need_restart" = true ]; then
        log_info "重启服务"
        remote_exec "supervisorctl restart tcb:"
        sleep 2
        remote_exec "supervisorctl status tcb:"
    else
        log_ok "仅静态文件变化，无需重启"
    fi

    # 记录
    echo "$current_commit" > "$DEPLOY_COMMIT_FILE"
    remote_exec "echo '${current_commit}' > ${REMOTE_DIR}/.deploy_commit"
    log_deploy "deploy" "commit=${current_commit} files=${file_count}"
    cleanup_old_releases

    echo ""
    log_ok "增量部署完成 (${last_commit:0:7} → ${current_commit:0:7})"
}

# ============================================================
# rollback: 回滚到上一版本
# ============================================================
do_rollback() {
    log_step "回滚"

    local current
    current=$(remote_exec "readlink ${REMOTE_DIR}/current | xargs basename")
    local releases
    releases=$(remote_exec "ls -1dt ${REMOTE_DIR}/releases/v* | head -5")
    local release_count
    release_count=$(echo "$releases" | grep -c '.' || true)

    if [ "$release_count" -lt 2 ]; then
        log_fail "只有一个版本，无法回滚"
        exit 1
    fi

    # 找到上一个版本
    local previous
    previous=$(echo "$releases" | sed -n '2p')
    local prev_name
    prev_name=$(basename "$previous")

    log_info "当前: ${current}"
    log_info "回滚到: ${prev_name}"

    remote_exec "ln -sfn ${previous} ${REMOTE_DIR}/current"
    remote_exec "supervisorctl restart tcb:"
    sleep 2

    log_deploy "rollback" "from=${current} to=${prev_name}"

    echo ""
    log_ok "回滚完成: ${current} → ${prev_name}"
    remote_exec "supervisorctl status tcb:"
}

# ============================================================
# sync: 只同步配置
# ============================================================
do_sync() {
    log_step "同步配置"
    cd "$PROJECT_DIR"

    for config in "${CONFIG_FILES[@]}"; do
        local local_file="${PROJECT_DIR}/${config}"
        if [ -f "$local_file" ]; then
            scp "$local_file" "${REMOTE}:${REMOTE_DIR}/shared/${config}"
            log_ok "${config}"
        fi
    done

    if [ -f "$PROJECT_DIR/.env" ]; then
        scp "$PROJECT_DIR/.env" "${REMOTE}:${REMOTE_DIR}/shared/.env"
        log_ok ".env（从 .env）"
    elif [ -f "$PROJECT_DIR/.env.example" ]; then
        scp "$PROJECT_DIR/.env.example" "${REMOTE}:${REMOTE_DIR}/shared/.env"
        log_ok ".env（从 .env.example）"
    fi

    log_deploy "sync" "config files synced"
    log_ok "配置同步完成（未重启服务）"
}

# ============================================================
# 主入口
# ============================================================
MODE="${1:-deploy}"

case "$MODE" in
    init)     do_init ;;
    deploy)   do_deploy ;;
    rollback) do_rollback ;;
    sync)     do_sync ;;
    *)
        echo "用法: $0 [init|rollback|sync]"
        echo "  无参数  增量部署（默认）"
        echo "  init    首次全量部署"
        echo "  rollback 回滚到上一版本"
        echo "  sync    只同步配置文件"
        exit 1
        ;;
esac
