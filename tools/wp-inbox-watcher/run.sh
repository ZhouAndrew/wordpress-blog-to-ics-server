#!/usr/bin/env bash
# WordPress Inbox Watcher launcher for Linux Mint / Ubuntu / Debian.
# Only stdlib + tkinter are needed. System packages are installed on demand,
# with the user's permission; the watcher is not privilege-elevated.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$(command -v python3 || true)"
NEEDS_GUI=1

for arg in "$@"; do
  case "$arg" in
    --no-gui|--help|-h) NEEDS_GUI=0 ;;
  esac
done

say() { printf '[WordPress Inbox Watcher] %s\n' "$*" >&2; }

have_tk() {
  "$PYTHON" -c 'import tkinter' >/dev/null 2>&1
}

# Called only when dependencies are actually missing.
ask_to_install() {
  local packages="$1" answer
  say "缺少必要依赖：${packages}。"
  if [[ -t 0 ]]; then
    printf '现在自动安装吗？需要管理员授权。[Y/n] ' >&2
    IFS= read -r answer || return 1
    case "$answer" in
      ''|y|Y|yes|YES|Yes|是) return 0 ;;
      *) return 1 ;;
    esac
  fi
  if command -v zenity >/dev/null 2>&1 && [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
    zenity --question --title='WordPress Inbox Watcher — 依赖安装' \
      --text="启动需要安装系统软件包：${packages}\n\n现在自动安装吗？系统会请求管理员授权。" \
      --ok-label='安装' --cancel-label='取消'
    return $?
  fi
  return 1
}

missing=()
if [[ -z "$PYTHON" ]]; then
  missing+=(python3)
fi
if (( NEEDS_GUI )) && { [[ -z "$PYTHON" ]] || ! have_tk; }; then
  missing+=(python3-tk)
fi

if (( ${#missing[@]} )); then
  if ! command -v apt-get >/dev/null 2>&1; then
    say "当前系统没有 apt-get；请使用发行版的软件包管理器安装：${missing[*]}。"
    exit 1
  fi
  if ! ask_to_install "${missing[*]}"; then
    say "已取消自动安装；可自行运行：sudo apt-get install -y ${missing[*]}"
    exit 1
  fi

  say "准备安装 ${missing[*]}（只在缺少依赖时执行）..."
  if (( EUID == 0 )); then
    apt-get install -y "${missing[@]}"
  elif [[ -t 0 ]] && command -v sudo >/dev/null 2>&1; then
    sudo apt-get install -y "${missing[@]}"
  elif command -v pkexec >/dev/null 2>&1; then
    # Graphical desktop launch without terminal: use PolicyKit password dialog.
    pkexec apt-get install -y "${missing[@]}"
  else
    say "无法请求管理员授权；请在终端执行：sudo apt-get install -y ${missing[*]}"
    exit 1
  fi
fi

# Re-resolve after installation; don't launch a Python process with missing deps.
PYTHON="$(command -v python3 || true)"
if [[ -z "$PYTHON" ]]; then
  say '安装后仍未找到 python3，无法启动。'
  exit 1
fi
if (( NEEDS_GUI )) && ! have_tk; then
  # A virtual environment may shadow the distro Python with tkinter support.
  if [[ -x /usr/bin/python3 ]] && /usr/bin/python3 -c 'import tkinter' >/dev/null 2>&1; then
    PYTHON=/usr/bin/python3
  else
    say '安装后仍无法导入 tkinter；可以改用 ./run.sh --no-gui 运行终端模式。'
    exit 1
  fi
fi

say '依赖检查通过，正在启动。'
exec "$PYTHON" "$SCRIPT_DIR/wp_inbox_watcher.py" "$@"
