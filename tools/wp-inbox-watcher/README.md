# WordPress Inbox Watcher — 第一轮

命令行启动，Tkinter 图形化窗口实时显示**最新消息**，终端同步输出；将受监视目录的文件/文件夹依次交给**唯一上传工作线程**，按文件**原始修改时间**分配到对应日期的 WordPress 日志文章，追加 Gutenberg 原生区块。首次扫描后持续监视变化。

## Linux Mint 安装 / 运行（启动器自动检查依赖）

解压后打开终端，进入 `wp-inbox-watcher` 文件夹，直接执行：

```bash
./run.sh
```

**无需预先手动安装 `python3-tk`。** `run.sh` 在程序启动前检查 Python 3 和 Tkinter；如果缺少，会先询问是否安装，确认后通过 Linux Mint / Ubuntu / Debian 的 `apt-get` 安装必要系统包（终端通过 `sudo`，无终端的图形化启动通过 PolicyKit `pkexec`）。仅在缺少依赖时申请管理员权限；监视程序不会自行提权，而是保持原来的启动用户身份。**不要使用 `sudo ./run.sh` 启动整个程序**。拒绝安装不会更改系统。

不带目录时先显示用途说明，随后调用系统文件夹选择器。直接带目录时：

```bash
./run.sh "$HOME/Desktop/WP-Inbox"
```

无桌面界面、或不想安装 Tkinter 时使用终端模式（无需 `python3-tk`）：

```bash
./run.sh --no-gui "$HOME/Desktop/WP-Inbox"
```

显式指定 WP-CLI 或 REST：

```bash
./run.sh "$HOME/Desktop/WP-Inbox" \
  --wp /usr/local/bin/wp --wp-path /var/www/html/wordpress

./run.sh "$HOME/Desktop/WP-Inbox" \
  --rest-url https://andrew.local
```

> 注意：**通过 `./run.sh` 才会触发启动时依赖检查与自安装**。直接执行 `python3 wp_inbox_watcher.py` 不会自动安装系统软件包。无 `apt-get` 的 Linux 发行版需自行安装 Python 3 与 Tkinter；在非交互环境且没有 Zenity 时，安装会中止并打印手动安装命令。

**首次强烈建议在测试 WordPress 站点与测试目录操作，避免误将私人文件发布。** 注意：本程序将自动创建并发布按文件日期对应的日志文章（如果不存在），不是仅预览。

## 监视目录

```text
WP-Inbox/
├── picture.jpg                # 等待处理
├── study/                     # 可以投递整个文件夹（递归处理文件）
├── key.txt                    # REST 模式才需要；用户名和 Application Password，权限 600
├── work/                      # 完全不监视
│   ├── debug.log              # 详细记录；含原文件名、文件路径、媒体 URL 等元数据
│   ├── settings.json          # REST 网站 URL，不含密码
│   ├── jobs/                  # 中断恢复和上传检查点
│   └── inflight/<任务ID>/原文件名  # 上传中 / 失败后保留的源文件
└── trash/<任务ID>/原文件名         # 完全不监视；保存成功归档的原文件
```

启动时和每次文件目录有变化时，扫描根目录下除了 `work`、`trash`、`key.txt` 和常见临时文件名以外的顶层条目。文件/目录尺寸与时间戳连续稳定默认至少 4 秒后入队；**单线程**逐一认领（移动到 `work/inflight`）、上传、更新日志文章、读取 WordPress 核查写入标识，然后移到 `trash`。失败留在 `work`，重启自动恢复，或点窗口中的“重试 work 中失败任务”。**不会自动删除 `trash`。** 所有子目录都会移动为一个任务，内部文件递归逐个上传；不跟随符号链接。

该程序采用 **2 秒轮询**，不依赖 `watchdog` / inotify，文件完全没变动不会再次发布。对于仍被其他软件长时间写入的文件，请先使用 `.part` 临时文件名，写入完成后再重命名。

## WordPress

1. 自动查找 WP-CLI 可执行文件和常见 WordPress 安装路径。若发现**多个有效候选组合**，图形选择列表供选择（不可用时改终端编号）。可用 `--wp`、`--wp-path` 明确指定。首先验证 `wp core is-installed`；如果 WP-CLI 不可用，改用 REST。
2. REST 模式询问站点 URL，以及 `key.txt` 缺失时提示 WordPress 用户名 + **Application Password**（不是普通后台密码）。严格按第一行用户名、第二行应用密码保存 `key.txt`，仅本机当前用户可读。`work/settings.json` 单独保存站点 URL；以后启动复用。REST 需要 WordPress 原生 Application Password 认证和允许上传媒体/编辑文章权限。
3. 搜索标题包含英文月份/缩写、日期、星期和年份的日志文章（兼容 `find-today-post.sh`）；若不存在，自动创建并发布日期标题，例如 `October 16  Friday  2026`。**本轮按每个文件的修改日期创建/查找相应日期的文章；其时间显示为原文件修改时间。** 文件夹中不同日期文件可能写入不同日期文章。使用运行计算机的时区，建议与 WordPress 网站时区一致。
4. 先 `media import` / REST 上传附件，再为图片添加 `wp:image`、视频添加 `wp:video`、音频添加 `wp:audio`、PDF 添加带内嵌预览的 `wp:file`；`.ics`、`.html`、文本和其他文件添加普通 `wp:file` 下载链接。每个文件前还有一个 `HH:MM 路径` 段落。这样不会把 HTML 作为可执行代码插入文章。
5. 追加后立刻 **write → read back**，通过稳定的 `wpi-...` 标识检测已追加块，尽量降低崩溃后重复发布的风险。多份程序或已有 Shell 脚本同时修改同一文章可能发生覆盖，本轮不支持并发写入同一篇文章，请避免并行写入。

**注意**：WordPress 默认可能不允许上传 `.ics`、`.html` 或其他危险/未知文件类型。此时任务报错，原文件留在 `work`，不会静默假装成功；需要在 WordPress 端配置允许的 MIME 才能上传。PDF 的 Gutenberg 实际渲染效果取决于 WordPress 主题和浏览器。

## 安全、诊断及限制

- `key.txt` **明文保存**应用密码，只是应用户要求支持离线重启；`chmod 600` 限制权限。不要上传到 GitHub、共享盘或公开目录。优先使用权限最小的专用 WordPress 账号。建议不要在同步盘中设收件目录。
- REST 除 `localhost` 和 `.local` 等局域名外默认强制 HTTPS。自签名站点可导入正确 CA；仅测试环境才使用 `--allow-insecure-cert`。
- 日志在 `work/debug.log`，会包含文件名与路径等隐私信息，但不会故意记录密码或认证头。
- 多媒体文件使用流式 REST 上传，不把大文件整体加载进内存；WP-CLI 中使用临时 PHP 文件写入长文章内容，避免命令行长度限制。
- 任务记录支持重启恢复；但在服务器已成功接收媒体、**本地还没写入上传检查点**就断电的极小窗口中，可能产生未附加的重复媒体，需要人工检查。
- 本程序只验证本地逻辑。具体 WP-CLI、REST、权限、真实 WordPress 编辑器预览等效果，仍需你在自己的 WordPress 站点验收。

## 本地运行测试

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile wp_inbox_watcher.py
```


## v0.3.0: ZIP / tar.gz wrapping of folders and rejected file types

This version replaces the previous per-file folder uploads: each **new folder** is
archived as a single file, preserving its full directory tree and original name,
including extensions. For example, `Folder.ics/` becomes `Folder.ics.zip`.

- A `.xpi` file becomes `extension.xpi.zip` by default. No global WordPress MIME
  rules are loosened and no temporary PHP upload filter is injected.
- Other disallowed file types are retried once inside a ZIP when WordPress returns
  an explicit file-type rejection. Authentication and network failures are not
  retried as ZIPs.
- An optional `--archive-format tar.gz` makes archives such as
  `extension.xpi.tar.gz` and `Folder.tar.gz`.
- Successful originals are preserved under `trash/<job-id>/`, with temporary
  archives removed from `work/archives/`. Failed work stays in
  `work/inflight/` for recovery.
- Previously partially processed v0.2 folder jobs retain their existing
  per-file checkpoints; only newly claimed folders use the single-archive format.
- `work/debug.log` records archive creation, WordPress errors, media IDs and
  write/readback verification. Symlinks and special files are rejected rather
  than silently packaged.

### Run the standalone CPython file

```bash
python3 tools/wp-inbox-watcher/wp_inbox_watcher.py ~/Desktop/outbox
python3 tools/wp-inbox-watcher/wp_inbox_watcher.py ~/Desktop/outbox --archive-format tar.gz
```

When Tkinter is unavailable, the standalone script can **ask** before using apt
to install it. In headless mode pass `--no-gui`.

The program writes to real WordPress posts. Verify first with a test site and
disposable inbox. A WordPress site that rejects both normal media uploads and
ZIP/gzip uploads still cannot accept the archive; the source remains in work.

