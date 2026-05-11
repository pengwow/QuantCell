#!/bin/bash

# ==============================================================================
# QuantCell 一键安装与启动脚本
# ==============================================================================
# 功能说明：
#   1. 自动检测操作系统环境（Windows/macOS/Linux）
#   2. 自动安装工具链（uv、bun）
#   3. 配置后端环境（Python依赖、数据库初始化、服务启动）
#   4. 配置前端环境（npm依赖、编译构建、服务启动）
#   5. 进程管理与优雅终止
#   6. 完善的错误处理与日志输出
#
# 使用方法：
#   chmod +x install.sh
#   ./install.sh
# ==============================================================================

set -e  # 遇到错误立即退出

# ==================== 全局变量 ====================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
LOG_DIR="$PROJECT_ROOT/logs"

# 进程PID文件
BACKEND_PID_FILE="$LOG_DIR/backend.pid"
FRONTEND_PID_FILE="$LOG_DIR/frontend.pid"

# 日志文件
INSTALL_LOG="$LOG_DIR/install.log"
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"

# 端口配置
BACKEND_PORT=8000
FRONTEND_PORT=5173

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ==================== 工具函数 ====================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$INSTALL_LOG"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$INSTALL_LOG"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$INSTALL_LOG"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$INSTALL_LOG"
}

log_step() {
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  $1${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo "" | tee -a "$INSTALL_LOG"
}

# 检查命令是否存在
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# 创建日志目录
setup_log_dir() {
    mkdir -p "$LOG_DIR"
    touch "$INSTALL_LOG"
    log_info "日志目录已创建: $LOG_DIR"
}

# ==================== 必要命令检查 ====================

# 存储缺失的命令
MISSING_REQUIRED=()
MISSING_OPTIONAL=()

# 获取命令描述
get_command_desc() {
    case "$1" in
        bash)   echo "Bash shell 运行环境" ;;
        mkdir)  echo "创建目录" ;;
        cd)     echo "切换工作目录" ;;
        echo)   echo "输出文本" ;;
        tee)    echo "同时输出到屏幕和文件" ;;
        date)   echo "获取当前时间" ;;
        command) echo "检查命令是否存在" ;;
        cat)    echo "读取文件内容" ;;
        kill)   echo "终止进程" ;;
        sleep)  echo "暂停执行" ;;
        wait)   echo "等待后台进程" ;;
        grep)   echo "文本搜索" ;;
        touch)  echo "创建空文件" ;;
        rm)     echo "删除文件" ;;
        nohup)  echo "忽略挂断信号运行命令" ;;
        lsof)   echo "查看端口占用情况 (macOS/Linux)" ;;
        curl)   echo "下载文件 (curl/wget 至少需要其一)" ;;
        wget)   echo "下载文件 (curl/wget 至少需要其一)" ;;
        unzip)  echo "解压 ZIP 文件 (部分依赖包可能需要)" ;;
        tar)    echo "解压 tar.gz 文件 (部分依赖包可能需要)" ;;
        python3) echo "Python 3 运行时 (后端服务必需)" ;;
        python) echo "Python 运行时 (兼容旧系统)" ;;
        *)      echo "系统工具" ;;
    esac
}

check_required_commands() {
    log_step "检查必要系统命令"

    local has_error=false

    # 必要命令列表
    local required_cmds=(
        "bash"
        "mkdir"
        "cd"
        "echo"
        "tee"
        "date"
        "command"
        "cat"
        "kill"
        "sleep"
        "wait"
        "grep"
        "touch"
        "rm"
        "nohup"
        "lsof"
    )

    # 检查必要命令
    log_info "检查必须存在的命令..."
    for cmd in "${required_cmds[@]}"; do
        if command_exists "$cmd"; then
            log_success "✓ $cmd - $(get_command_desc $cmd)"
        else
            log_error "✗ $cmd - $(get_command_desc $cmd)"
            MISSING_REQUIRED+=("$cmd")
            has_error=true
        fi
    done

    # 检查可选命令（分组检查）
    echo ""
    log_info "检查推荐命令..."

    # curl 和 wget 至少需要一个
    if command_exists "curl" || command_exists "wget"; then
        if command_exists "curl"; then
            log_success "✓ curl - $(get_command_desc curl)"
        fi
        if command_exists "wget"; then
            log_success "✓ wget - $(get_command_desc wget)"
        fi
    else
        log_warning "✗ 缺少下载工具: 需要安装 curl 或 wget 其中之一"
        MISSING_OPTIONAL+=("curl或wget")
        has_error=true
    fi

    # 检查其他可选命令
    for cmd in "unzip" "tar"; do
        if command_exists "$cmd"; then
            log_success "✓ $cmd - $(get_command_desc $cmd)"
        else
            log_warning "⚠ $cmd - $(get_command_desc $cmd) (建议安装)"
            MISSING_OPTIONAL+=("$cmd")
        fi
    done

    # python3 和 python 至少需要一个
    if command_exists "python3" || command_exists "python"; then
        if command_exists "python3"; then
            PYTHON_VERSION=$(python3 --version 2>&1 | head -1)
            log_success "✓ python3 - $PYTHON_VERSION"
        elif command_exists "python"; then
            PYTHON_VERSION=$(python --version 2>&1 | head -1)
            log_success "✓ python - $PYTHON_VERSION"
        fi
    else
        log_warning "⚠ python3/python - $(get_command_desc python3) (后端服务需要 Python 环境)"
        MISSING_OPTIONAL+=("python")
    fi

    # 检查结果汇总
    echo ""
    if [ ${#MISSING_REQUIRED[@]} -gt 0 ]; then
        log_error "========================================"
        log_error "缺少以下必要命令 (${#MISSING_REQUIRED[@]} 个):"
        log_error "========================================"
        for cmd in "${MISSING_REQUIRED[@]}"; do
            log_error "  - $cmd: $(get_command_desc $cmd)"
        done
        echo ""
        show_install_guide "${MISSING_REQUIRED[@]}"
        return 1
    fi

    if [ ${#MISSING_OPTIONAL[@]} -gt 0 ]; then
        log_warning "========================================"
        log_warning "缺少以下推荐命令 (${#MISSING_OPTIONAL[@]} 个):"
        log_warning "========================================"
        for cmd in "${MISSING_OPTIONAL[@]}"; do
            log_warning "  - $cmd"
        done
        echo ""
        show_optional_install_guide "${MISSING_OPTIONAL[@]}"
        log_warning "缺少这些命令可能导致部分功能无法使用"
    fi

    log_success "必要命令检查完成"
    return 0
}

show_install_guide() {
    log_info "根据您的操作系统，请使用以下命令安装缺失的工具："
    echo ""
    
    case "$OS_TYPE" in
        macos)
            echo -e "  ${YELLOW}macOS 安装方法:${NC}"
            echo "  # 使用 Homebrew (推荐)"
            echo "  /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
            echo ""
            echo "  # 然后安装缺失的工具:"
            for cmd in "$@"; do
                case $cmd in
                    lsof)   echo "  brew install lsof" ;;
                    grep)   echo "  brew install grep" ;;
                    *)      echo "  brew install $cmd" ;;
                esac
            done
            ;;
        linux)
            echo -e "  ${YELLOW}Linux 安装方法:${NC}"
            
            # 检测包管理器
            if command_exists apt-get; then
                echo "  # Debian/Ubuntu:"
                echo "  sudo apt-get update"
                CMD_LIST=""
                for cmd in "$@"; do
                    case $cmd in
                        lsof)   CMD_LIST="$CMD_LIST lsof" ;;
                        nohup)  CMD_LIST="$CMD_LIST coreutils" ;;
                        *)      CMD_LIST="$CMD_LIST $cmd" ;;
                    esac
                done
                echo "  sudo apt-get install$CMD_LIST"
            elif command_exists yum; then
                echo "  # CentOS/RHEL/Fedora:"
                CMD_LIST=""
                for cmd in "$@"; do
                    case $cmd in
                        lsof)   CMD_LIST="$CMD_LIST lsof" ;;
                        nohup)  CMD_LIST="$CMD_LIST coreutils" ;;
                        *)      CMD_LIST="$CMD_LIST $cmd" ;;
                    esac
                done
                echo "  sudo yum install$CMD_LIST"
            elif command_exists dnf; then
                echo "  # Fedora (新版):"
                CMD_LIST=""
                for cmd in "$@"; do
                    CMD_LIST="$CMD_LIST $cmd"
                done
                echo "  sudo dnf install$CMD_LIST"
            elif command_exists pacman; then
                echo "  # Arch Linux:"
                CMD_LIST=""
                for cmd in "$@"; do
                    CMD_LIST="$CMD_LIST $cmd"
                done
                echo "  sudo pacman -S$CMD_LIST"
            else
                echo "  # 请根据您的发行版选择合适的包管理器"
                echo "  # 常见工具名: $(echo "$@" | tr ' ' ', ')"
            fi
            ;;
        windows)
            echo -e "  ${YELLOW}Windows 安装方法:${NC}"
            echo "  # 请通过 Git Bash 或 WSL 安装所需工具"
            echo "  # 或访问: https://git-scm.com/downloads"
            echo ""
            echo "  # 推荐使用 Chocolatey:"
            echo "  # 安装 Chocolatey: https://chocolatey.org/install"
            CMD_LIST=""
            for cmd in "$@"; do
                CMD_LIST="$CMD_LIST $cmd"
            done
            echo "  choco install$CMD_LIST -y"
            ;;
        *)
            echo "  # 请手动安装以下命令: $@"
            ;;
    esac
    
    echo ""
}

show_optional_install_guide() {
    log_info "可选命令安装建议（按需安装）："
    echo ""
    
    case "$OS_TYPE" in
        macos)
            echo -e "  ${YELLOW}macOS:${NC}"
            echo "  brew install unzip tar python3"
            ;;
        linux)
            if command_exists apt-get; then
                echo -e "  ${YELLOW}Debian/Ubuntu:${NC}"
                echo "  sudo apt-get install unzip tar python3"
            elif command_exists yum; then
                echo -e "  ${YELLOW}CentOS/RHEL:${NC}"
                echo "  sudo yum install unzip tar python3"
            elif command_exists dnf; then
                echo -e "  ${YELLOW}Fedora:${NC}"
                echo "  sudo dnf install unzip tar python3"
            fi
            ;;
        *)
            echo "  # 请根据操作系统安装: unzip, tar, python3"
            ;;
    esac
    
    echo ""
}

# ==================== 系统环境检测 ====================

detect_os() {
    log_step "检测操作系统环境"

    OS_TYPE="unknown"
    OS_VERSION=""

    case "$(uname -s)" in
        Darwin)
            OS_TYPE="macos"
            OS_VERSION=$(sw_vers -productVersion 2>/dev/null || echo "unknown")
            log_info "检测到 macOS 系统 (版本: $OS_VERSION)"
            ;;
        Linux)
            OS_TYPE="linux"
            if [ -f /etc/os-release ]; then
                . /etc/os-release
                OS_VERSION="$NAME $VERSION"
            else
                OS_VERSION="Unknown Linux"
            fi
            log_info "检测到 Linux 系统 ($OS_VERSION)"
            ;;
        MINGW*|MSYS*|CYGWIN*)
            OS_TYPE="windows"
            OS_VERSION="Windows (via MSYS/Git Bash)"
            log_info "检测到 Windows 环境"
            ;;
        *)
            OS_TYPE="unknown"
            log_warning "未知操作系统: $(uname -s)"
            ;;
    esac

    log_success "系统环境检测完成: $OS_TYPE"
}

# ==================== 工具链安装 ====================

install_uv() {
    log_step "检查/安装 uv (Python包管理器)"

    if command_exists uv; then
        UV_VERSION=$(uv --version)
        log_success "uv 已安装 (版本: $UV_VERSION)"
        
        # 检查是否需要更新
        if [ "$AUTO_UPDATE" = "true" ]; then
            log_info "正在更新 uv 到最新版本..."
            uv self update || log_warning "uv 更新失败，继续使用当前版本"
        fi
        return 0
    fi

    log_info "正在安装 uv..."

    case "$OS_TYPE" in
        macos|linux)
            # 使用官方安装脚本
            if command_exists curl; then
                curl -LsSf https://astral.sh/uv/install.sh | sh || {
                    log_error "uv 安装失败 (curl方式)"
                    return 1
                }
            elif command_exists wget; then
                wget -qO- https://astral.sh/uv/install.sh | sh || {
                    log_error "uv 安装失败 (wget方式)"
                    return 1
                }
            else
                log_error "需要 curl 或 wget 来安装 uv"
                return 1
            fi
            
            # 将 uv 添加到 PATH
            export PATH="$HOME/.local/bin:$PATH"
            
            # 持久化到 shell 配置文件
            if [ -f ~/.bashrc ]; then
                echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
            fi
            if [ -f ~/.zshrc ]; then
                echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
            fi
            ;;
        windows)
            log_info "Windows 环境请手动安装 uv: https://docs.astral.sh/uv/getting-started/installation/"
            log_info "或使用 PowerShell 运行: powershell -ExecutionPolicy ByPass -c \"irm https://astral.sh/uv/install.ps1 | iex\""
            return 1
            ;;
        *)
            log_error "不支持的操作系统: $OS_TYPE"
            return 1
            ;;
    esac

    # 验证安装
    if command_exists uv; then
        UV_VERSION=$(uv --version)
        log_success "uv 安装成功 (版本: $UV_VERSION)"
        return 0
    else
        log_error "uv 安装失败"
        return 1
    fi
}

install_bun() {
    log_step "检查/安装 bun (前端包管理器)"

    if command_exists bun; then
        BUN_VERSION=$(bun --version)
        log_success "bun 已安装 (版本: $BUN_VERSION)"
        return 0
    fi

    log_info "正在安装 bun..."

    case "$OS_TYPE" in
        macos|linux)
            # 使用官方安装脚本
            if command_exists curl; then
                curl -fsSL https://bun.sh/install | bash || {
                    log_error "bun 安装失败 (curl方式)"
                    return 1
                }
            elif command_exists wget; then
                wget -qO- https://bun.sh/install | bash || {
                    log_error "bun 安装失败 (wget方式)"
                    return 1
                }
            else
                log_error "需要 curl 或 wget 来安装 bun"
                return 1
            fi
            
            # 将 bun 添加到 PATH
            export PATH="$HOME/.bun/bin:$PATH"
            
            # 持久化到 shell 配置文件
            if [ -f ~/.bashrc ]; then
                echo 'export PATH="$HOME/.bun/bin:$PATH"' >> ~/.bashrc
            fi
            if [ -f ~/.zshrc ]; then
                echo 'export PATH="$HOME/.bun/bin:$PATH"' >> ~/.zshrc
            fi
            ;;
        windows)
            log_info "Windows 环境请手动安装 bun: https://bun.sh/docs/installation"
            log_info "或使用 PowerShell 运行: powershell -c \"irm bun.sh/install.ps1 | iex\""
            return 1
            ;;
        *)
            log_error "不支持的操作系统: $OS_TYPE"
            return 1
            ;;
    esac

    # 刷新 shell 环境
    source ~/.bashrc 2>/dev/null || source ~/.zshrc 2>/dev/null || true

    # 验证安装
    if command_exists bun; then
        BUN_VERSION=$(bun --version)
        log_success "bun 安装成功 (版本: $BUN_VERSION)"
        return 0
    else
        log_error "bun 安装失败"
        return 1
    fi
}

# ==================== 后端环境配置 ====================

setup_backend() {
    log_step "配置后端环境"

    # 检查后端目录
    if [ ! -d "$BACKEND_DIR" ]; then
        log_error "后端目录不存在: $BACKEND_DIR"
        return 1
    fi

    cd "$BACKEND_DIR" || {
        log_error "无法进入后端目录"
        return 1
    }

    # 安装 Python 依赖
    log_info "安装 Python 依赖..."
    if [ -f "pyproject.toml" ]; then
        uv sync || {
            log_error "Python 依赖安装失败"
            return 1
        }
        log_success "Python 依赖安装完成"
    elif [ -f "requirements.txt" ]; then
        uv pip install -r requirements.txt || {
            log_error "Python 依赖安装失败"
            return 1
        }
        log_success "Python 依赖安装完成"
    else
        log_warning "未找到 pyproject.toml 或 requirements.txt，跳过依赖安装"
    fi

    # 初始化数据库
    log_info "初始化数据库..."
    if [ -f "scripts/init_database.py" ]; then
        uv run python scripts/init_database.py --init-db --init-agent-params || {
            log_warning "数据库初始化失败（可能已初始化过），继续执行..."
        }
        log_success "数据库初始化完成"
    else
        log_warning "未找到 init_database.py 脚本，跳过数据库初始化"
    fi

    cd "$PROJECT_ROOT" || true
    return 0
}

# ==================== 前端环境配置 ====================

setup_frontend() {
    log_step "配置前端环境"

    # 检查前端目录
    if [ ! -d "$FRONTEND_DIR" ]; then
        log_error "前端目录不存在: $FRONTEND_DIR"
        return 1
    fi

    cd "$FRONTEND_DIR" || {
        log_error "无法进入前端目录"
        return 1
    }

    # 安装 npm 依赖
    log_info "安装前端依赖..."
    if [ -f "package.json" ]; then
        bun install || {
            log_error "前端依赖安装失败"
            return 1
        }
        log_success "前端依赖安装完成"
    else
        log_warning "未找到 package.json，跳过依赖安装"
    fi

    # 构建前端项目
    log_info "构建前端项目..."
    if grep -q '"build"' package.json 2>/dev/null; then
        bun run build || {
            log_error "前端构建失败"
            return 1
        }
        log_success "前端构建完成"
    else
        log_warning "未找到 build 脚本，跳过构建"
    fi

    cd "$PROJECT_ROOT" || true
    return 0
}

# ==================== 服务启动与管理 ====================

start_backend() {
    log_info "启动后端服务..."

    if [ ! -d "$BACKEND_DIR" ]; then
        log_error "后端目录不存在"
        return 1
    fi

    # 检查端口是否被占用
    if lsof -Pi :$BACKEND_PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
        log_warning "端口 $BACKEND_PORT 已被占用，尝试停止现有进程..."
        lsof -ti :$BACKEND_PORT | xargs kill -9 2>/dev/null || true
        sleep 2
    fi

    cd "$BACKEND_DIR" || return 1

    # 启动后端服务（后台运行）
    nohup uvicorn main:app --host 0.0.0.0 --port $BACKEND_PORT > "$BACKEND_LOG" 2>&1 &
    BACKEND_PID=$!
    echo $BACKEND_PID > "$BACKEND_PID_FILE"

    cd "$PROJECT_ROOT" || true

    # 等待服务启动
    sleep 3

    # 检查进程是否还在运行
    if kill -0 $BACKEND_PID 2>/dev/null; then
        log_success "后端服务已启动 (PID: $BACKEND_PID, 端口: $BACKEND_PORT)"
        log_info "后端日志: $BACKEND_LOG"
        return 0
    else
        log_error "后端服务启动失败，请查看日志: $BACKEND_LOG"
        return 1
    fi
}

start_frontend() {
    log_info "启动前端服务..."

    if [ ! -d "$FRONTEND_DIR" ]; then
        log_error "前端目录不存在"
        return 1
    fi

    # 检查端口是否被占用
    if lsof -Pi :$FRONTEND_PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
        log_warning "端口 $FRONTEND_PORT 已被占用，尝试停止现有进程..."
        lsof -ti :$FRONTEND_PORT | xargs kill -9 2>/dev/null || true
        sleep 2
    fi

    cd "$FRONTEND_DIR" || return 1

    # 启动前端开发服务器（后台运行）
    nohup bun run dev > "$FRONTEND_LOG" 2>&1 &
    FRONTEND_PID=$!
    echo $FRONTEND_PID > "$FRONTEND_PID_FILE"

    cd "$PROJECT_ROOT" || true

    # 等待服务启动
    sleep 5

    # 检查进程是否还在运行
    if kill -0 $FRONTEND_PID 2>/dev/null; then
        log_success "前端服务已启动 (PID: $FRONTEND_PID, 端口: $FRONTEND_PORT)"
        log_info "前端日志: $FRONTEND_LOG"
        return 0
    else
        log_error "前端服务启动失败，请查看日志: $FRONTEND_LOG"
        return 1
    fi
}

stop_services() {
    log_step "停止所有服务"

    # 停止后端服务
    if [ -f "$BACKEND_PID_FILE" ]; then
        BACKEND_PID=$(cat "$BACKEND_PID_FILE")
        if kill -0 $BACKEND_PID 2>/dev/null; then
            log_info "停止后端服务 (PID: $BACKEND_PID)..."
            kill $BACKEND_PID 2>/dev/null || true
            wait $BACKEND_PID 2>/dev/null || true
            log_success "后端服务已停止"
        else
            log_warning "后端进程已不存在"
        fi
        rm -f "$BACKEND_PID_FILE"
    fi

    # 停止前端服务
    if [ -f "$FRONTEND_PID_FILE" ]; then
        FRONTEND_PID=$(cat "$FRONTEND_PID_FILE")
        if kill -0 $FRONTEND_PID 2>/dev/null; then
            log_info "停止前端服务 (PID: $FRONTEND_PID)..."
            kill $FRONTEND_PID 2>/dev/null || true
            wait $FRONTEND_PID 2>/dev/null || true
            log_success "前端服务已停止"
        else
            log_warning "前端进程已不存在"
        fi
        rm -f "$FRONTEND_PID_FILE"
    fi

    # 强制清理残留进程
    log_info "清理残留进程..."
    lsof -ti :$BACKEND_PORT | xargs kill -9 2>/dev/null || true
    lsof -ti :$FRONTEND_PORT | xargs kill -9 2>/dev/null || true

    log_success "所有服务已停止"
}

check_services_status() {
    log_step "检查服务状态"

    # 检查后端服务
    if [ -f "$BACKEND_PID_FILE" ]; then
        BACKEND_PID=$(cat "$BACKEND_PID_FILE")
        if kill -0 $BACKEND_PID 2>/dev/null; then
            log_success "后端服务运行中 (PID: $BACKEND_PID, http://localhost:$BACKEND_PORT)"
        else
            log_error "后端服务未运行"
        fi
    else
        log_warning "后端服务未启动"
    fi

    # 检查前端服务
    if [ -f "$FRONTEND_PID_FILE" ]; then
        FRONTEND_PID=$(cat "$FRONTEND_PID_FILE")
        if kill -0 $FRONTEND_PID 2>/dev/null; then
            log_success "前端服务运行中 (PID: $FRONTEND_PID, http://localhost:$FRONTEND_PORT)"
        else
            log_error "前端服务未运行"
        fi
    else
        log_warning "前端服务未启动"
    fi
}

# ==================== 信号处理 ====================

cleanup() {
    echo ""
    log_warning "接收到终止信号，正在清理..."
    stop_services
    exit 0
}

trap cleanup SIGINT SIGTERM

# ==================== 主程序 ====================

show_banner() {
    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║                                              ║${NC}"
    echo -e "${GREEN}║          QuantCell 一键安装与启动           ║${NC}"
    echo -e "${GREEN}║                                              ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
    echo ""
}

show_usage() {
    echo "使用方法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  --install       仅安装环境和依赖（不启动服务）"
    echo "  --start         仅启动服务（跳过安装）"
    echo "  --stop          停止所有服务"
    echo "  --status        查看服务状态"
    echo "  --restart       重启所有服务"
    echo "  --update        更新工具链（uv, bun）"
    echo "  --check         仅检查必要命令（不执行其他操作）"
    echo "  --help          显示帮助信息"
    echo ""
    echo "说明:"
    echo "  脚本会自动检查以下必要命令是否已安装:"
    echo "  - 必需命令: bash, mkdir, cd, echo, tee, date, command, cat,"
    echo "              kill, sleep, wait, grep, touch, rm, nohup, lsof"
    echo "  - 推荐命令: curl/wget (至少一个), unzip, tar, python3/python"
    echo ""
    echo "示例:"
    echo "  $0              # 完整安装并启动（包含命令检查）"
    echo "  $0 --install    # 仅安装"
    echo "  $0 --start      # 仅启动"
    echo "  $0 --stop       # 停止服务"
    echo "  $0 --status     # 查看状态"
    echo "  $0 --check      # 仅检查命令环境"
}

parse_args() {
    ACTION="full"
    AUTO_UPDATE="false"

    while [[ $# -gt 0 ]]; do
        case $1 in
            --install)
                ACTION="install"
                shift
                ;;
            --start)
                ACTION="start"
                shift
                ;;
            --stop)
                ACTION="stop"
                shift
                ;;
            --status)
                ACTION="status"
                shift
                ;;
            --restart)
                ACTION="restart"
                shift
                ;;
            --check)
                ACTION="check"
                shift
                ;;
            --update)
                AUTO_UPDATE="true"
                shift
                ;;
            --help|-h)
                show_usage
                exit 0
                ;;
            *)
                log_error "未知参数: $1"
                show_usage
                exit 1
                ;;
        esac
    done
}

main() {
    parse_args "$@"

    show_banner
    setup_log_dir
    detect_os

    # 检查必要命令（除了 --stop 和 --status 操作）
    if [[ "$ACTION" != "stop" && "$ACTION" != "status" ]]; then
        if ! check_required_commands; then
            log_error "必要命令检查未通过，请先安装缺失的命令后重试"
            exit 1
        fi
    fi

    case "$ACTION" in
        check)
            # 仅检查命令环境，不执行其他操作
            if ! check_required_commands; then
                exit 1
            fi
            log_success "命令环境检查完成，所有必要命令已就绪"
            ;;

        install)
            log_step "执行安装流程"
            install_uv && install_bun && setup_backend && setup_frontend
            log_success "安装完成！"
            echo ""
            echo -e "${GREEN}提示: 运行 '$0 --start' 启动服务${NC}"
            ;;

        start)
            log_step "启动服务"
            start_backend && start_frontend
            echo ""
            echo -e "${GREEN}========================================${NC}"
            echo -e "${GREEN}  服务启动完成！${NC}"
            echo -e "${GREEN}========================================${NC}"
            echo ""
            echo -e "  后端 API: ${BLUE}http://localhost:$BACKEND_PORT${NC}"
            echo -e "  前端界面: ${BLUE}http://localhost:$FRONTEND_PORT${NC}"
            echo ""
            echo -e "  按 ${YELLOW}Ctrl+C${NC} 停止所有服务"
            echo ""

            # 保持脚本运行，等待 Ctrl+C
            wait
            ;;

        stop)
            stop_services
            ;;

        status)
            check_services_status
            ;;

        restart)
            log_step "重启服务"
            stop_services
            sleep 2
            start_backend && start_frontend
            echo ""
            echo -e "${GREEN}========================================${NC}"
            echo -e "${GREEN}  服务重启完成！${NC}"
            echo -e "${GREEN}========================================${NC}"
            echo ""
            echo -e "  后端 API: ${BLUE}http://localhost:$BACKEND_PORT${NC}"
            echo -e "  前端界面: ${BLUE}http://localhost:$FRONTEND_PORT${NC}"
            echo ""
            echo -e "  按 ${YELLOW}Ctrl+C${NC} 停止所有服务"
            echo ""

            wait
            ;;

        full)
            log_step "执行完整安装与启动流程"

            # 1. 安装工具链
            log_info "步骤 1/4: 安装工具链..."
            if ! install_uv; then
                log_error "uv 安装失败，终止安装"
                exit 1
            fi

            if ! install_bun; then
                log_error "bun 安装失败，终止安装"
                exit 1
            fi

            # 2. 配置后端环境
            log_info "步骤 2/4: 配置后端环境..."
            if ! setup_backend; then
                log_error "后端环境配置失败，终止安装"
                exit 1
            fi

            # 3. 配置前端环境
            log_info "步骤 3/4: 配置前端环境..."
            if ! setup_frontend; then
                log_error "前端环境配置失败，终止安装"
                exit 1
            fi

            # 4. 启动服务
            log_info "步骤 4/4: 启动服务..."
            if ! start_backend; then
                log_error "后端服务启动失败"
                exit 1
            fi

            if ! start_frontend; then
                log_error "前端服务启动失败"
                stop_services
                exit 1
            fi

            # 显示启动信息
            echo ""
            echo -e "${GREEN}========================================${NC}"
            echo -e "${GREEN}  🎉 安装与启动完成！${NC}"
            echo -e "${GREEN}========================================${NC}"
            echo ""
            echo -e "  ✅ 后端 API: ${BLUE}http://localhost:$BACKEND_PORT${NC}"
            echo -e "  ✅ 前端界面: ${BLUE}http://localhost:$FRONTEND_PORT${NC}"
            echo ""
            echo -e "  📋 日志文件:${NC}"
            echo -e "     - 安装日志: $INSTALL_LOG"
            echo -e "     - 后端日志: $BACKEND_LOG"
            echo -e "     - 前端日志: $FRONTEND_LOG"
            echo ""
            echo -e "  💡 提示:${NC}"
            echo -e "     - 按 ${YELLOW}Ctrl+C${NC} 停止所有服务"
            echo -e "     - 运行 '${YELLOW}$0 --status${NC}' 查看服务状态"
            echo -e "     - 运行 '${YELLOW}$0 --restart${NC}' 重启服务"
            echo ""

            # 保持脚本运行，等待 Ctrl+C
            wait
            ;;
    esac
}

# 执行主程序
main "$@"
