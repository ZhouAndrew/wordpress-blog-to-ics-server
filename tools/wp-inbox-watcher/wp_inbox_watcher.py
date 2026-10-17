#!/usr/bin/env python3
"""Monitor an inbox and append uploaded media as Gutenberg blocks to dated WordPress posts."""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import getpass
import io
import hashlib
import html
import http.client
import json
import logging
import mimetypes
import os
from pathlib import Path
import queue
import re
import shutil
import ssl
import stat
import tarfile
import subprocess
import sys
import threading
import time
from typing import Any
import urllib.parse
import uuid
import zipfile

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, scrolledtext, ttk
except ImportError:
    tk = None

IGNORED_NAMES = {"work", "trash", "key.txt"}
TEMP_SUFFIXES = (".part", ".partial", ".tmp", ".crdownload", ".swp", "~")
APP_NAME = "WordPress Inbox Watcher"
INSTRUCTIONS = (
    "WordPress Inbox Watcher：监视一个可读写目录，将新文件或文件夹中的文件按原始修改时间"
    "上传并追加到相应日期的 WordPress 日志文章。文件夹整体打包，禁止的文件类型打包后重试；"
    "压缩包名保留原始后缀（例如 plugin.xpi.zip）。work 和 trash 不会被监视；"
    "成功文件移入 trash，失败任务保留在 work。最新消息在窗口和终端显示，"
    "详细调试日志保存在 work/debug.log。"
)


def ensure_tkinter(argv: list[str] | None = None) -> bool:
    """Optionally install python3-tk when launching this single .py file.

    Only attempts apt on an interactive user-confirmed request.  Never elevates
    the watcher itself, and never mutates the filesystem in --no-gui mode.
    """
    if tk is not None:
        return True
    argv = list(sys.argv[1:] if argv is None else argv)
    if any(arg in ("--no-gui", "--help", "-h") for arg in argv):
        return False
    print("图形界面需要 python3-tk。", file=sys.stderr)
    if not shutil.which("apt-get"):
        print("未找到 apt-get；请安装对应发行版的 tkinter，或使用 --no-gui。", file=sys.stderr)
        return False
    approved = False
    if sys.stdin.isatty():
        try:
            reply = input("是否自动安装 python3-tk？需要管理员授权。[y/N] ")
            approved = reply.strip().casefold() in ("y", "yes", "是")
        except EOFError:
            approved = False
    elif shutil.which("zenity") and (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        try:
            approved = subprocess.run(["zenity", "--question", "--title=WordPress Inbox Watcher",
                                     "--text=缺少 python3-tk。现在安装吗？需要管理员授权。"],
                                     timeout=120, check=False).returncode == 0
        except (OSError, subprocess.SubprocessError):
            pass
    if not approved:
        print("未安装 Tkinter；可执行：sudo apt-get install python3-tk", file=sys.stderr)
        return False
    if os.geteuid() == 0:
        command = ["apt-get", "install", "-y", "python3-tk"]
    elif sys.stdin.isatty() and shutil.which("sudo"):
        command = ["sudo", "apt-get", "install", "-y", "python3-tk"]
    elif shutil.which("pkexec"):
        command = ["pkexec", "apt-get", "install", "-y", "python3-tk"]
    else:
        print("无法申请系统权限，请手动运行 sudo apt-get install python3-tk", file=sys.stderr)
        return False
    try:
        subprocess.run(command, check=True, timeout=600)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"安装 python3-tk 失败：{exc}", file=sys.stderr)
        return False
    # Python imports can be cached, and a venv may not see distro packages.
    # Re-execute only after a verified interpreter can actually import tkinter.
    candidates = [sys.executable, "/usr/bin/python3"]
    for python in dict.fromkeys(candidates):
        if not Path(python).is_file():
            continue
        try:
            ok = subprocess.run([python, "-c", "import tkinter"], timeout=10,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
        except (OSError, subprocess.SubprocessError):
            continue
        if ok:
            os.execv(python, [python, str(Path(__file__).resolve()), *argv])
    print("安装后仍不能加载 Tkinter；请使用 --no-gui。", file=sys.stderr)
    return False


# These suffixes commonly fail WordPress' default upload policy.
# ZIP wrapping is preferable to relaxing the server's MIME safety rules.
PREPACK_SUFFIXES = {".xpi"}


def rejected_file_type(error: Exception) -> bool:
    """Recognize WordPress file-type errors, but not unrelated auth/network failures."""
    message = str(error).casefold()
    return bool(re.search(
        r"file[ -]?type|mime[ -]?type|invalid_file_type|upload_filetype|"
        r"文件类型|不允许上传此类文件|不支持的文件格式",
        message
    ) and any(term in message for term in (
        "not allowed", "not permitted", "not supported", "not accepted",
        "invalid", "prohibited", "unsupported", "blocked", "security",
        "sorry", "不允许", "不支持", "拒绝", "禁止", "无效", "安全",
    )))


def archive_filename(original_name: str, archive_format: str) -> str:
    """Append the archive extension *after* the complete original name."""
    if archive_format not in ("zip", "tar.gz"):
        raise ValueError("archive format must be zip or tar.gz")
    return original_name + "." + archive_format


def create_upload_archive(source: Path, target: Path, archive_format: str) -> Path:
    """Create one atomic archive, keeping original names and directory hierarchy.

    Reject symlinks and special files, including inside directories.  The archive
    lives outside the watched inbox; its creation cannot re-trigger processing.
    """
    if source.is_symlink() or not (source.is_file() or source.is_dir()):
        raise RuntimeError(f"无法安全打包此目录项: {source}")
    if target.exists() and (target.is_symlink() or not target.is_file()):
        raise RuntimeError(f"压缩包目标路径异常: {target}")
    members = [source]
    if source.is_dir():
        members.extend(sorted(source.rglob("*"), key=lambda p: p.as_posix()))
    for item in members:
        if item.is_symlink() or not (item.is_file() or item.is_dir()):
            raise RuntimeError(f"文件夹中包含符号链接或特殊文件，拒绝打包: {item}")
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".partial-" + uuid.uuid4().hex)
    try:
        if archive_format == "zip":
            with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED,
                                 allowZip64=True) as archive:
                for item in members:
                    archive.write(item, arcname=item.relative_to(source.parent).as_posix())
        elif archive_format == "tar.gz":
            with tarfile.open(temp, mode="w:gz") as archive:
                for item in members:
                    archive.add(item, arcname=item.relative_to(source.parent).as_posix(),
                                recursive=False)
        else:
            raise ValueError(f"不支持的打包格式: {archive_format}")
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)
    return target


def upload_error_hint(error: Exception, filename: str, backend: Any) -> str:
    """Display upload failures in the message window and the debug log."""
    detail = str(error)
    if rejected_file_type(error):
        detail += ("；WordPress 拒绝了该文件类型（包括可能的压缩包）。"
                   "原始文件保留在 work 中；请检查站点允许的 zip/gz 类型并重试。")
    return detail


def local_time(timestamp: float) -> dt.datetime:
    return dt.datetime.fromtimestamp(timestamp).astimezone()


def post_title(when: dt.datetime) -> str:
    return f"{when.strftime('%B')} {when.day}  {when.strftime('%A')}  {when.year}"


def is_same_day_title(title: str, when: dt.datetime) -> bool:
    """Follow the month/day/weekday/year convention used by the supplied shell scripts."""
    parts = [when.strftime("%B"), when.strftime("%b")]
    title = html.unescape(re.sub(r"<[^>]+>", "", title))
    return (any(re.search(r"\b" + re.escape(p) + r"\b", title, re.I) for p in parts)
            and bool(re.search(r"(?<!\d)" + str(when.day) + r"(?!\d)", title))
            and bool(re.search(r"\b" + re.escape(when.strftime("%A")) + r"\b", title, re.I))
            and bool(re.search(r"(?<!\d)" + str(when.year) + r"(?!\d)", title)))


def classify(path: Path) -> tuple[str, str]:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    ext = path.suffix.lower()
    if ext == ".pdf":
        return "pdf", "application/pdf"
    if ext in (".ics", ".ifb"):
        return "calendar", "text/calendar"
    if mime.startswith("image/"):
        return "image", mime
    if mime.startswith("video/"):
        return "video", mime
    if mime.startswith("audio/"):
        return "audio", mime
    if mime in ("text/html", "application/xhtml+xml"):
        return "html", mime
    if mime.startswith("text/"):
        return "text", mime
    return "file", mime


def gutenberg_block(category: str, media_id: int, url: str, name: str, token: str,
                    when: dt.datetime, relative: str) -> str:
    """Construct core blocks analogous to upload-file.sh, with a stable dedupe marker."""
    safe_url = html.escape(url, quote=True)
    safe_name = html.escape(name, quote=True)
    marker = "wpi-" + re.sub(r"[^a-f0-9]", "", token.lower())[:32]
    attrs: dict[str, Any] = {"id": media_id, "className": marker}
    if category == "image":
        attrs["sizeSlug"] = "large"
        kind = "image"
        body = (f'<figure class="wp-block-image size-large {marker}">'
                f'<img src="{safe_url}" alt="{safe_name}" class="wp-image-{media_id}"/></figure>')
    elif category == "video":
        kind = "video"
        body = (f'<figure class="wp-block-video {marker}">'
                f'<video controls src="{safe_url}"></video></figure>')
    elif category == "audio":
        kind = "audio"
        body = (f'<figure class="wp-block-audio {marker}">'
                f'<audio controls src="{safe_url}"></audio></figure>')
    else:
        kind = "file"
        attrs["href"] = url
        if category == "pdf":
            attrs["displayPreview"] = True
        body = (f'<div class="wp-block-file {marker}"><a href="{safe_url}">{safe_name}</a>'
                + (f'<object class="wp-block-file__embed" data="{safe_url}" type="application/pdf"'
                   ' style="width:100%;height:500px" aria-label="PDF preview"></object>'
                   if category == "pdf" else "")
                + "</div>")
    block = f"<!-- wp:{kind} {json.dumps(attrs, ensure_ascii=False, separators=(',', ':'))} -->\n{body}\n<!-- /wp:{kind} -->"
    # Preserve the captured pre-move time in a separate, valid Gutenberg paragraph.
    summary = f"{when.strftime('%H:%M')} {relative}"
    meta = f"<!-- wp:paragraph -->\n<p>{html.escape(summary)}</p>\n<!-- /wp:paragraph -->"
    return meta + "\n\n" + block


def append_blocks(existing: str, incoming: str) -> str:
    return existing.rstrip() + ("\n\n" if existing.strip() else "") + incoming


def write_json(path: Path, data: dict[str, Any]) -> None:
    temp = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    try:
        with temp.open("w", encoding="utf-8") as stream:
            os.chmod(temp, 0o600)
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def verify_inbox(root: Path) -> None:
    if not root.is_dir() or root.is_symlink():
        raise ValueError(f"目录不存在或是符号链接: {root}")
    with os.scandir(root) as entries:
        list(entries)
    test = root / (".wpi-permission-check-" + uuid.uuid4().hex)
    with test.open("x") as stream:
        stream.write("test")
    test.unlink()
    for child in (root / "work", root / "trash"):
        if child.is_symlink():
            raise ValueError(f"禁止使用符号链接作为受保护目录: {child}")
        child.mkdir(exist_ok=True)
        if not child.is_dir():
            raise ValueError(f"不是目录: {child}")
        with os.scandir(child) as entries:
            list(entries)
        probe = child / (".permission-check-" + uuid.uuid4().hex)
        with probe.open("x") as f:
            f.write("ok")
        probe.unlink()


class EventHandler(logging.Handler):
    def __init__(self, q: queue.Queue):
        super().__init__(logging.INFO)
        self.q = q

    def emit(self, record: logging.LogRecord) -> None:
        try:
            # Send concise latest messages to Tk; full tracebacks go to debug.log.
            self.q.put_nowait((record.levelname, f"{record.levelname}: {record.getMessage()}"))
        except Exception:
            pass


def make_logger(work: Path, events: queue.Queue) -> logging.Logger:
    log = logging.getLogger("wpi." + uuid.uuid4().hex)
    log.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s %(levelname)-8s [%(threadName)s] %(message)s")
    file_handler = logging.FileHandler(work / "debug.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    log.addHandler(file_handler)
    output = logging.StreamHandler(sys.stdout)
    output.setLevel(logging.INFO)
    output.setFormatter(formatter)
    log.addHandler(output)
    events_handler = EventHandler(events)
    events_handler.setFormatter(formatter)
    log.addHandler(events_handler)
    return log


def choose_dialog(title: str, options: list[str], root=None) -> int | None:
    if not root:
        return None
    answer: list[int | None] = [None]
    top = tk.Toplevel(root)
    top.title(title)
    top.geometry("770x320")
    top.transient(root)
    tk.Label(top, text=title, wraplength=700, font=("Sans", 11, "bold")).pack(pady=10)
    listing = tk.Listbox(top, width=110, height=10)
    listing.pack(fill="both", expand=True, padx=12)
    for item in options:
        listing.insert("end", item)
    listing.selection_set(0)

    def confirm():
        selection = listing.curselection()
        if selection:
            answer[0] = int(selection[0])
            top.destroy()

    tk.Button(top, text="Select / 选择", command=confirm).pack(pady=10)
    listing.bind("<Double-Button-1>", lambda _: confirm())
    top.protocol("WM_DELETE_WINDOW", top.destroy)
    top.grab_set()
    root.wait_window(top)
    return answer[0]


def ask_text(label: str, gui=None, secret: bool = False) -> str:
    if gui is not None:
        value = simpledialog.askstring(APP_NAME, label, parent=gui, show="*" if secret else None)
        if value is None:
            raise RuntimeError("用户取消填写")
        return value.strip()
    if not sys.stdin.isatty():
        raise RuntimeError(f"无法交互填写 {label}，请使用图形化会话或交互终端")
    return (getpass.getpass(label + ": ") if secret else input(label + ": ")).strip()


def pick_one(title: str, options: list[str], gui=None) -> int:
    if not options:
        raise ValueError("No choices")
    if len(options) == 1:
        return 0
    chosen = choose_dialog(title, options, gui)
    if chosen is not None:
        return chosen
    if not sys.stdin.isatty():
        raise RuntimeError("无法交互选择 WordPress；请指定 --wp 和 --wp-path")
    print(title)
    for n, name in enumerate(options, 1):
        print(f"  {n}. {name}")
    while True:
        v = ask_text("输入编号", None)
        if v.isdigit() and 1 <= int(v) <= len(options):
            return int(v) - 1


def find_wp_executables() -> list[str]:
    candidates = []
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        p = Path(entry) / "wp"
        if p.is_file() and os.access(p, os.X_OK):
            candidates.append(str(p.resolve()))
    for p in (Path("/usr/local/bin/wp"), Path("/usr/bin/wp"),
              Path.home() / ".local/bin/wp", Path.home() / ".config/composer/vendor/bin/wp"):
        if p.is_file() and os.access(p, os.X_OK):
            candidates.append(str(p.resolve()))
    return list(dict.fromkeys(candidates))


def find_wp_roots(explicit: str | None) -> list[str]:
    candidates = [Path(explicit)] if explicit else [
        Path.cwd(), Path("/var/www/html/wordpress"), Path("/var/www/html"),
        Path.home() / "public_html", Path.home() / "wordpress"
    ]
    result = []
    for p in candidates:
        try:
            p = p.expanduser().resolve()
            if (p / "wp-load.php").is_file():
                result.append(str(p))
        except OSError:
            continue
    return list(dict.fromkeys(result))


class WpCliBackend:
    def __init__(self, binary: str, wp_path: str, logger: logging.Logger):
        self.binary, self.wp_path, self.log = binary, wp_path, logger
        self._post_cache: dict[str, int] = {}

    def call(self, *args: str) -> str:
        cmd = [self.binary, f"--path={self.wp_path}", *args]
        self.log.debug("WP-CLI call: %r", cmd)
        run = subprocess.run(cmd, capture_output=True, text=True,
                             timeout=1200 if "media" in args else 180)
        if run.returncode:
            raise RuntimeError("WP-CLI failed: " + run.stderr[-2500:])
        return run.stdout.strip()

    def validate(self) -> None:
        self.call("core", "is-installed")

    def post_for_day(self, when: dt.datetime) -> int:
        key = when.date().isoformat()
        if key in self._post_cache:
            return self._post_cache[key]
        posts = json.loads(self.call("post", "list", "--post_type=post", "--post_status=any",
                                     "--posts_per_page=-1", "--fields=ID,post_title", "--format=json"))
        matches = [int(p["ID"]) for p in posts if is_same_day_title(p["post_title"], when)]
        if len(matches) > 1:
            raise RuntimeError(f"Multiple diary posts match {when.date()}: {matches}")
        if matches:
            self._post_cache[key] = matches[0]
            return matches[0]
        created = self.call("post", "create", "--post_type=post", "--post_status=publish",
                            "--post_title=" + post_title(when), "--post_date=" + when.strftime("%Y-%m-%d 12:00:00"),
                            "--porcelain")
        if not created.isdecimal():
            raise RuntimeError("Unexpected post create response: " + created)
        self._post_cache[key] = int(created)
        return self._post_cache[key]

    def upload(self, path: Path, post_id: int, mime: str) -> tuple[int, str]:
        # Do not bypass WordPress file-type security: the processor archives
        # unsupported content to .zip/.tar.gz before invoking this method.
        answer = self.call("media", "import", str(path),
                           f"--post_id={post_id}", "--porcelain")
        if not answer.isdecimal():
            raise RuntimeError("Unexpected media import response: " + answer)
        media_id = int(answer)
        try:
            url = self.call("eval", f"echo wp_get_attachment_url({media_id});")
        except Exception:
            url = self.call("post", "get", str(media_id), "--field=guid")
        if not url.startswith(("https://", "http://")):
            raise RuntimeError("Invalid uploaded attachment URL: " + url)
        return media_id, url

    def get_content(self, post_id: int) -> str:
        return self.call("post", "get", str(post_id), "--field=post_content")

    def set_content(self, post_id: int, content: str) -> None:
        # Large WordPress posts must not be passed through argv. `--post_content=@file`
        # is NOT a WP-CLI content-file syntax; use wp eval-file and read file in PHP.
        import tempfile
        with tempfile.TemporaryDirectory(prefix="wpi-post-") as temp:
            base = Path(temp)
            php = base / "update.php"
            data = base / "content.html"
            php.write_text("""<?php
$post_id = (int) $args[0];
$body = file_get_contents($args[1]);
if ($body === false) { fwrite(STDERR, "content read failed\n"); exit(2); }
$result = wp_update_post(array('ID' => $post_id, 'post_content' => $body), true);
if (is_wp_error($result)) { fwrite(STDERR, $result->get_error_message()); exit(3); }
echo (string) $result;
""" , encoding="utf-8")
            data.write_text(content, encoding="utf-8")
            os.chmod(data, 0o600)
            self.call("eval-file", str(php), str(post_id), str(data))


class RestBackend:
    def __init__(self, url: str, username: str, password: str, logger: logging.Logger,
                 allow_insecure_cert: bool = False):
        parsed = urllib.parse.urlsplit(url.strip().rstrip("/"))
        if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("WordPress site URL must be http(s)://hostname[/wordpress], without credentials")
        if parsed.scheme != "https" and parsed.hostname not in ("localhost", "127.0.0.1", "::1") and not parsed.hostname.endswith(".local"):
            raise ValueError("Remote WordPress must use HTTPS to protect the Application Password")
        self.base = url.strip().rstrip("/") + "/wp-json/wp/v2"
        self.username, self.password, self.log = username, password, logger
        self.allow_insecure_cert = allow_insecure_cert
        self._post_cache: dict[str, int] = {}

    def request(self, method: str, endpoint: str, payload: Any = None,
                upload: Path | None = None, content_type: str = "application/json") -> Any:
        url = self.base + endpoint
        parts = urllib.parse.urlsplit(url)
        path = parts.path + ("?" + parts.query if parts.query else "")
        conn_class = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
        kwargs: dict[str, Any] = {"timeout": 120}
        if parts.scheme == "https" and self.allow_insecure_cert:
            kwargs["context"] = ssl._create_unverified_context()  # explicit opt-in only
        conn = conn_class(parts.hostname, parts.port, **kwargs)
        token = base64.b64encode(f"{self.username}:{self.password}".encode()).decode("ascii")
        headers = {"Authorization": "Basic " + token, "Accept": "application/json",
                   "User-Agent": "WordPress-Inbox-Watcher/0.1"}
        self.log.debug("REST %s %s", method, url)
        try:
            if upload is not None:
                size = upload.stat().st_size
                # WP's media endpoint expects filename in Content-Disposition.
                encoded_name = urllib.parse.quote(upload.name, safe=".-_()")
                headers.update({"Content-Type": content_type, "Content-Length": str(size),
                                "Content-Disposition": f'attachment; filename="{encoded_name}"'})
                conn.putrequest(method, path)
                for k, v in headers.items():
                    conn.putheader(k, v)
                conn.endheaders()
                with upload.open("rb") as input_file:
                    while part := input_file.read(1024 * 1024):
                        conn.send(part)
            else:
                body = (json.dumps(payload, ensure_ascii=False).encode("utf-8")
                        if payload is not None else None)
                if body is not None:
                    headers["Content-Type"] = "application/json"
                conn.request(method, path, body=body, headers=headers)
            response = conn.getresponse()
            raw = response.read()
            try:
                result = json.loads(raw.decode("utf-8")) if raw else {}
            except (ValueError, UnicodeError):
                raise RuntimeError(f"WordPress returned non-JSON HTTP {response.status}: {raw[:150]!r}")
            if response.status >= 400:
                reason = result.get("message", str(result)) if isinstance(result, dict) else str(result)
                raise RuntimeError(f"WordPress HTTP {response.status}: {reason[:1500]}")
            return result
        finally:
            conn.close()

    def validate(self) -> None:
        self.request("GET", "/users/me?context=edit")

    def post_for_day(self, when: dt.datetime) -> int:
        key = when.date().isoformat()
        if key in self._post_cache:
            return self._post_cache[key]
        matches: list[int] = []
        for page in range(1, 21):
            search = urllib.parse.urlencode({"search": when.strftime("%B"), "per_page": 100,
                                            "page": page, "context": "edit", "status": "publish,future,draft,private"})
            try:
                posts = self.request("GET", "/posts?" + search)
            except RuntimeError as ex:
                if "HTTP 400" in str(ex) and page > 1:  # WP pagination is exhausted
                    break
                raise
            for p in posts:
                title = p.get("title", {}).get("raw") or p.get("title", {}).get("rendered", "")
                if is_same_day_title(title, when):
                    matches.append(int(p["id"]))
            if len(posts) < 100:
                break
        if len(matches) > 1:
            raise RuntimeError(f"Multiple diary posts match {when.date()}: {matches}")
        if matches:
            self._post_cache[key] = matches[0]
            return matches[0]
        result = self.request("POST", "/posts", {"title": post_title(when), "status": "publish",
                                                   "date": when.strftime("%Y-%m-%dT12:00:00")})
        self._post_cache[key] = int(result["id"])
        return self._post_cache[key]

    def upload(self, path: Path, post_id: int, mime: str) -> tuple[int, str]:
        result = self.request("POST", "/media", upload=path, content_type=mime)
        media_id = int(result["id"])
        self.request("POST", f"/media/{media_id}", {"post": post_id})
        return media_id, str(result["source_url"])

    def get_content(self, post_id: int) -> str:
        result = self.request("GET", f"/posts/{post_id}?context=edit")
        return result["content"]["raw"]

    def set_content(self, post_id: int, content: str) -> None:
        self.request("POST", f"/posts/{post_id}", {"content": content})


def configured_backend(args, root: Path, gui, log: logging.Logger):
    binaries = [args.wp] if args.wp else find_wp_executables()
    roots = find_wp_roots(args.wp_path)
    choices = [(binary, install) for binary in binaries for install in roots]
    if choices and not args.rest_url:
        valid: list[tuple[str, str, WpCliBackend]] = []
        for binary, install in choices:
            candidate = WpCliBackend(binary, install, log)
            try:
                candidate.validate()
            except Exception as ex:
                log.debug("WP-CLI 候选未通过检测: %s --path=%s: %s", binary, install, ex)
            else:
                valid.append((binary, install, candidate))
        if valid:
            idx = pick_one("发现可用 WordPress WP-CLI 配置，请选择（若有多个）",
                           [f"{b}   --path={p}" for b, p, _ in valid], gui)
            binpath, path, backend = valid[idx]
            log.info("WP-CLI 可用: %s --path=%s", binpath, path)
            return backend
        log.warning("已找到 WP-CLI 文件但没有可用的 WordPress 安装，改用 REST")
    else:
        log.info("没有选择 WP-CLI（可能不存在），使用 WordPress REST + Application Password")
    settings = root / "work" / "settings.json"
    config = json.loads(settings.read_text("utf-8")) if settings.exists() else {}
    url = args.rest_url or config.get("rest_url")
    if not url:
        url = ask_text("WordPress 网站 URL（例 https://andrew.local）", gui)
        if not url:
            raise RuntimeError("未填写 WordPress URL")
    if config.get("rest_url") != url:
        write_json(settings, {"rest_url": url})
    key = root / "key.txt"
    if key.is_symlink():
        raise RuntimeError("key.txt 不得为符号链接")
    if key.is_file():
        lines = key.read_text("utf-8").splitlines()
        if len(lines) < 2 or not lines[0].strip() or not lines[1].strip():
            raise RuntimeError("key.txt 需要第一行用户名、第二行 Application Password")
        user, password = lines[0].strip(), lines[1].strip()
        if stat.S_IMODE(key.stat().st_mode) & 0o077:
            os.chmod(key, 0o600)
    else:
        user = ask_text("WordPress 用户名", gui)
        password = ask_text("WordPress Application Password（非普通登录密码）", gui, secret=True)
        if not user or not password or "\n" in password:
            raise RuntimeError("用户名或 Application Password 无效")
        fd = os.open(key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(user + "\n" + password + "\n")
        log.info("已创建 key.txt（权限 600；本地明文敏感文件，不得公开）")
    backend = RestBackend(url, user, password, log, args.allow_insecure_cert)
    backend.validate()
    log.info("REST WordPress 登录验证成功: %s", url)
    return backend


class InboxProcessor:
    """Single worker. Owns in-flight movement, checkpointing and WordPress writes."""
    def __init__(self, root: Path, backend, log: logging.Logger, archive_format: str = 'zip'):
        self.root, self.backend, self.log = root, backend, log
        if archive_format not in ('zip', 'tar.gz'):
            raise ValueError('archive_format must be zip or tar.gz')
        self.archive_format = archive_format
        self.archives = root / 'work' / 'archives'
        self.work = root / "work"
        self.inflight = self.work / "inflight"
        self.jobs = self.work / "jobs"
        self.trash = root / "trash"
        self.inflight.mkdir(exist_ok=True)
        self.jobs.mkdir(exist_ok=True)
        self.archives.mkdir(exist_ok=True)
        self.queue: queue.Queue[str | None] = queue.Queue()
        self.pending: set[str] = set()
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.loop, name="wp-upload-worker", daemon=True)

    def start(self):
        self.thread.start()

    def enqueue(self, path: Path) -> None:
        with self.lock:
            identifier = "new:" + path.name
            if identifier not in self.pending:
                self.pending.add(identifier)
                self.queue.put(identifier)
                self.log.info("已加入队列: %s", path.name)

    def recover(self) -> None:
        for file in sorted(self.jobs.glob("*.json")):
            try:
                job = json.loads(file.read_text("utf-8"))
            except Exception:
                self.log.exception("损坏的任务记录: %s", file)
                continue
            if job.get("status") != "done":
                identifier = "job:" + job["id"]
                with self.lock:
                    if identifier not in self.pending:
                        self.pending.add(identifier)
                        self.queue.put(identifier)
                        self.log.info("重试/恢复待处理任务: %s", job.get("original"))

    def loop(self):
        while not self.stop.is_set():
            try:
                item = self.queue.get(timeout=0.25)
            except queue.Empty:
                continue
            if item is None:
                self.queue.task_done()
                break
            try:
                if item.startswith("new:"):
                    self.accept(self.root / item[4:])
                else:
                    self.process(item[4:])
            except Exception as exc:
                filename = item[4:] if item.startswith("new:") else item
                self.log.error("处理失败: %s。%s；保留在 work，点击“重试”可恢复",
                               filename, upload_error_hint(exc, filename, self.backend), exc_info=True)
            finally:
                with self.lock:
                    self.pending.discard(item)
                self.queue.task_done()

    def accept(self, path: Path) -> None:
        if path.name in IGNORED_NAMES or not path.exists():
            return
        if path.is_symlink():
            raise RuntimeError(f"拒绝处理符号链接: {path}")
        if not (path.is_dir() or path.is_file()):
            raise RuntimeError(f"不支持的目录项: {path}")
        job_id = uuid.uuid4().hex
        stamped = local_time(path.stat().st_mtime).isoformat()
        job = {"id": job_id, "original": path.name, "captured_mtime": stamped,
               "root_mtime": path.stat().st_mtime, "payload": path.name,
               "status": "claimed", "uploaded": {}, "done": [],
               "archive_format": self.archive_format}
        receipt = self.jobs / (job_id + ".json")
        write_json(receipt, job)
        task_dir = self.inflight / job_id
        task_dir.mkdir(exist_ok=False)
        dest = task_dir / job["payload"]
        try:
            path.rename(dest)
        except OSError:
            # Cross-device rename is rare for two paths below the same root; do not copy incomplete inputs.
            raise
        self.log.debug("Moved %s -> %s (mtime %s)", path, dest, stamped)
        job["status"] = "processing"
        write_json(receipt, job)
        self.process(job_id)

    def process(self, job_id: str) -> None:
        if not re.fullmatch(r"[a-f0-9]{32}", job_id):
            raise RuntimeError("非法的任务 ID")
        receipt = self.jobs / (job_id + ".json")
        job = json.loads(receipt.read_text("utf-8"))
        if (job.get("id") != job_id or not isinstance(job.get("payload"), str)
                or job["payload"] in ("", ".", "..")
                or Path(job["payload"]).name != job["payload"]
                or job.get("original") != job["payload"]):
            raise RuntimeError("任务记录损坏或包含目录穿越")
        if job.get("status") == "done" and (self.trash / job_id / job["payload"]).exists():
            shutil.rmtree(self.archives / job_id, ignore_errors=True)
            return
        task_dir = self.inflight / job_id
        if task_dir.is_symlink():
            raise RuntimeError("任务目录不得为符号链接")
        task_dir.mkdir(exist_ok=True)
        payload = task_dir / job["payload"]
        if not payload.exists():
            # Recover after receipt creation but before moving the original.
            original = self.root / job["original"]
            if original.exists() and not original.is_symlink():
                original.rename(payload)
            elif job.get("status") == "done":
                return
            elif (self.trash / job_id / job["payload"]).exists():
                job["status"] = "done"
                write_json(receipt, job)
                shutil.rmtree(self.archives / job_id, ignore_errors=True)
                self.log.info("已修复中断的归档任务: %s", job["original"])
                return
            else:
                raise RuntimeError(f"无法恢复任务，源文件与 work 均缺失: {job_id}")
        if payload.is_symlink():
            raise RuntimeError("拒绝处理符号链接任务")
        package_format = job.get("archive_format", self.archive_format)
        if package_format not in ("zip", "tar.gz"):
            raise RuntimeError(f"任务记录中的压缩格式不合法: {package_format}")

        # New folders are uploaded AS ONE archive, including empty directories.
        # Old partially processed folder jobs keep their per-file checkpoints,
        # preventing re-upload of files which were already attached by v0.2.
        legacy_folder = payload.is_dir() and (
            any("/" in key for key in job.get("uploaded", {}))
            or any("/" in key for key in job.get("done", []))
        )
        if payload.is_file() or not legacy_folder:
            files = [payload]
        else:
            self.log.warning("恢复旧版逐文件处理的文件夹任务: %s", job["original"])
            files = sorted((f for f in payload.rglob("*") if f.is_file() or f.is_symlink()),
                           key=lambda p: (p.lstat().st_mtime, str(p)))
            if not files:
                self.log.info("旧任务中的空文件夹，直接移至 trash: %s", job["original"])

        for file in files:
            if file.is_symlink():
                raise RuntimeError(f"文件夹中有符号链接，拒绝上传: {file}")
            rel = ((job["original"] + "/" + file.relative_to(payload).as_posix())
                   if legacy_folder else job["original"])
            if rel in job["done"]:
                continue
            stamp = (file.stat().st_mtime if legacy_folder else job["root_mtime"])
            when = local_time(stamp)
            post_id = self.backend.post_for_day(when)
            category, mime = classify(file) if file.is_file() else ("file", "application/zip")
            already = job["uploaded"].get(rel)
            if already:
                media_id, url = int(already["id"]), str(already["url"])
                upload_name = already.get("filename", file.name)
                upload_category = already.get("category", category)
                self.log.info("继续先前已上传的附件: %s → %s", rel, upload_name)
            else:
                packaged = file.is_dir() or file.suffix.lower() in PREPACK_SUFFIXES
                upload_path, upload_category, upload_mime = file, category, mime
                upload_dir = self.archives / job_id

                def pack() -> tuple[Path, str, str]:
                    # Preserve relative path in staging to avoid basename collisions
                    # when recovering a legacy folder with two same-named files.
                    dest = (upload_dir / rel).with_name(
                        archive_filename(file.name, package_format))
                    self.log.info("打包 %s → %s（保留原名称和后缀）", rel, dest.name)
                    create_upload_archive(file, dest, package_format)
                    archive_mime = ("application/zip" if package_format == "zip"
                                    else "application/x-gzip")
                    self.log.debug("Archive prepared source=%s archive=%s size=%d bytes",
                                   file, dest, dest.stat().st_size)
                    return dest, "file", archive_mime

                if packaged:
                    upload_path, upload_category, upload_mime = pack()
                self.log.info("上传 %s [%s, %s] → %s (Post %s)",
                              upload_path.name, upload_category, when.isoformat(),
                              when.date(), post_id)
                try:
                    media_id, url = self.backend.upload(upload_path, post_id, upload_mime)
                except Exception as exc:
                    if packaged or not rejected_file_type(exc):
                        raise
                    # A site can restrict additional types: retry with a standard
                    # archive, not a dangerous global upload_mimes exemption.
                    self.log.warning("WordPress 不允许直接上传 %s，改为压缩包后重试: %s",
                                     rel, str(exc)[:500])
                    upload_path, upload_category, upload_mime = pack()
                    media_id, url = self.backend.upload(upload_path, post_id, upload_mime)
                upload_name = upload_path.name
                job["uploaded"][rel] = {"id": media_id, "url": url,
                                        "filename": upload_name, "category": upload_category}
                write_json(receipt, job)
                self.log.debug("WordPress uploaded %s attachment_id=%s url=%s",
                               upload_name, media_id, url)
            token = hashlib.sha256((job_id + ":" + rel).encode("utf-8")).hexdigest()
            marker = "wpi-" + token[:32]
            current = self.backend.get_content(post_id)
            if marker in current:
                self.log.info("检测到已追加的 WordPress 区块，跳过重复追加: %s", rel)
            else:
                title = rel if upload_name == file.name else f"{rel} → {upload_name}"
                block = gutenberg_block(upload_category, media_id, url, upload_name,
                                        token, when, title)
                self.backend.set_content(post_id, append_blocks(current, block))
                verify = self.backend.get_content(post_id)
                if marker not in verify:
                    raise RuntimeError(f"WordPress 写入后回读未找到 marker: {marker}")
                self.log.debug("WordPress content write-readback verified: post=%s marker=%s",
                               post_id, marker)
            job["done"].append(rel)
            write_json(receipt, job)
            self.log.info("已完成 %s | 已上传 %s | 附件 %s", rel, upload_name, media_id)
        target = self.trash / job_id
        if target.exists():
            raise RuntimeError(f"trash 中已有同名任务目标: {target}")
        task_dir.rename(target)
        job["status"] = "done"
        job["archived_at"] = dt.datetime.now().astimezone().isoformat()
        write_json(receipt, job)
        shutil.rmtree(self.archives / job_id, ignore_errors=True)
        self.log.info("任务完成，已移至 trash: %s", job["original"])

    def shutdown(self):
        self.stop.set()
        self.queue.put(None)
        self.thread.join(timeout=5)


def signature(path: Path) -> tuple | None:
    """Cheap stability signature; folders include all descendant names, sizes and mtimes."""
    if path.is_symlink():
        return None
    try:
        if path.is_file():
            s = path.stat()
            return (s.st_size, s.st_mtime_ns)
        if path.is_dir():
            entries = []
            for child in path.rglob("*"):
                s = child.lstat() if child.is_symlink() else child.stat()
                entries.append((str(child.relative_to(path)), s.st_size, s.st_mtime_ns, s.st_mode))
            return tuple(sorted(entries))
    except (OSError, FileNotFoundError):
        return None
    return None


class PollWatcher:
    """Poll only the inbox root; work/trash and their descendants are never considered."""
    def __init__(self, root: Path, processor: InboxProcessor, log: logging.Logger,
                 interval: float = 2, quiet: float = 4):
        self.root, self.processor, self.log = root, processor, log
        self.interval, self.quiet = interval, quiet
        self.seen: dict[str, tuple[tuple, float]] = {}
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.thread = threading.Thread(target=self.loop, name="inbox-monitor", daemon=True)

    def rescan(self):
        self.wake.set()

    def start(self):
        self.thread.start()

    def scan(self) -> None:
        candidates = []
        try:
            for p in self.root.iterdir():
                if p.name in IGNORED_NAMES or p.name.startswith(".wpi-"):
                    continue
                if p.name.endswith(TEMP_SUFFIXES):
                    continue
                if p.is_symlink():
                    self.log.warning("忽略符号链接: %s", p.name)
                    continue
                if p.is_file() or p.is_dir():
                    candidates.append(p)
        except OSError:
            self.log.exception("监视目录扫描失败")
            return
        names = {p.name for p in candidates}
        for old in set(self.seen) - names:
            del self.seen[old]
        now = time.monotonic()
        for p in sorted(candidates, key=lambda x: (x.stat().st_mtime, x.name)):
            current = signature(p)
            if current is None:
                continue
            prev = self.seen.get(p.name)
            if prev is None or current != prev[0]:
                self.seen[p.name] = (current, now)
                self.log.debug("Observed new/changed inbox entry: %s", p)
            elif now - prev[1] >= self.quiet:
                self.processor.enqueue(p)
                self.seen.pop(p.name, None)

    def loop(self):
        while not self.stop.is_set():
            self.scan()
            self.wake.wait(self.interval)
            self.wake.clear()

    def shutdown(self):
        self.stop.set()
        self.wake.set()
        self.thread.join(timeout=5)


class StatusWindow:
    def __init__(self, root, inbox: Path, watcher: PollWatcher, processor: InboxProcessor,
                 events: queue.Queue, logger: logging.Logger):
        self.root, self.watcher, self.processor, self.events, self.log = root, watcher, processor, events, logger
        root.deiconify()
        root.title(APP_NAME + " — 最新消息")
        root.geometry("820x500")
        root.minsize(570, 360)
        ttk.Label(root, text=f"正在监视: {inbox}", wraplength=740).pack(anchor="w", padx=12, pady=(10, 6))
        ttk.Label(root, text="最新消息", font=("Sans", 12, "bold")).pack(anchor="w", padx=12)
        self.latest = tk.StringVar(value="正在启动监视…")
        ttk.Label(root, textvariable=self.latest, wraplength=760, font=("Sans", 12)).pack(
            anchor="w", padx=12, pady=10)
        self.display = scrolledtext.ScrolledText(root, height=15, state="disabled", wrap="word")
        self.display.pack(fill="both", expand=True, padx=12, pady=5)
        bar = ttk.Frame(root)
        bar.pack(fill="x", padx=12, pady=10)
        ttk.Button(bar, text="立即扫描", command=self.watcher.rescan).pack(side="left", padx=4)
        ttk.Button(bar, text="重试 work 中失败任务", command=self.processor.recover).pack(side="left", padx=4)
        ttk.Button(bar, text="退出", command=self.close).pack(side="right", padx=4)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(200, self.tick)

    def tick(self):
        for _ in range(150):
            try:
                level, message = self.events.get_nowait()
            except queue.Empty:
                break
            self.latest.set(message)
            self.display.configure(state="normal")
            self.display.insert("end", message + "\n")
            self.display.see("end")
            self.display.configure(state="disabled")
            if level in ("ERROR", "CRITICAL"):
                self.root.bell()
                self.root.deiconify()
                self.root.lift()
            elif "任务完成，已移至 trash" in message:
                self.root.lift()
        self.root.after(200, self.tick)

    def close(self):
        self.log.info("用户正在关闭监视器（正在进行的上传会尽力完成）")
        self.watcher.shutdown()
        self.processor.shutdown()
        self.root.destroy()


def build_parser():
    p = argparse.ArgumentParser(description=INSTRUCTIONS)
    p.add_argument("directory", nargs="?", help="要监视的收件目录；缺省时用 GUI 文件夹选择器")
    p.add_argument("--no-gui", action="store_true", help="只在终端运行；缺少目录时终端询问")
    p.add_argument("--wp", help="WP-CLI 可执行文件路径，未指定时自动发现")
    p.add_argument("--wp-path", help="WordPress 安装目录（含 wp-load.php）")
    p.add_argument("--rest-url", help="WordPress 站点 URL；指定时使用 REST")
    p.add_argument("--allow-insecure-cert", action="store_true", help="仅在本地可信站点临时跳过 HTTPS 证书验证")
    p.add_argument("--interval", type=float, default=2.0, help="扫描间隔秒数，默认 2")
    p.add_argument("--quiet", type=float, default=4.0, help="文件连续不变的秒数，默认 4")
    p.add_argument("--archive-format", choices=("zip", "tar.gz"), default="zip",
                   help="文件夹或被 WordPress 拒绝的文件的打包格式，默认 zip")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.interval <= 0 or args.quiet <= 0:
        raise SystemExit("--interval / --quiet must be positive")
    if not args.no_gui and tk is None:
        ensure_tkinter(list(sys.argv[1:] if argv is None else argv))
    print(INSTRUCTIONS, flush=True)
    ui = None
    if not args.no_gui and tk:
        try:
            ui = tk.Tk()
            ui.withdraw()
        except tk.TclError as exc:
            print(f"图形环境不可用，采用命令行模式: {exc}", file=sys.stderr)
    if args.directory:
        inbox = Path(args.directory).expanduser().resolve()
    elif ui is not None:
        messagebox.showinfo(APP_NAME + " 使用说明", INSTRUCTIONS + "\n\n请在下一步选择一个文件夹。", parent=ui)
        selected = filedialog.askdirectory(parent=ui, title="选择要监视的文件夹（需要读写权限）", mustexist=True)
        if not selected:
            print("取消选择文件夹", file=sys.stderr)
            ui.destroy()
            return 2
        inbox = Path(selected).resolve()
    else:
        inbox = Path(ask_text(INSTRUCTIONS + "\n请输入要监视的文件夹")).expanduser().resolve()
    try:
        verify_inbox(inbox)
    except Exception as ex:
        print(f"目录读写权限检查失败：{ex}", file=sys.stderr)
        if ui:
            messagebox.showerror(APP_NAME, str(ex), parent=ui)
            ui.destroy()
        return 2
    events: queue.Queue = queue.Queue()
    log = make_logger(inbox / "work", events)
    log.info("监视目录: %s；work/debug.log 已启用", inbox)
    log.debug("Runtime args (secret-safe): directory=%s wp=%s wp-path=%s rest-url=%s", inbox, args.wp, args.wp_path, args.rest_url)
    try:
        backend = configured_backend(args, inbox, ui, log)
    except Exception as ex:
        log.exception("WordPress 后端初始化失败: %s", ex)
        if ui:
            messagebox.showerror(APP_NAME + " 配置失败", str(ex), parent=ui)
            ui.destroy()
        return 3
    processor = InboxProcessor(inbox, backend, log, archive_format=args.archive_format)
    log.info("打包规则：文件夹整体打包；被拒绝的文件自动打包；格式=%s；保留完整原始名称及后缀",
             args.archive_format)
    watcher = PollWatcher(inbox, processor, log, interval=args.interval, quiet=args.quiet)
    processor.start()
    processor.recover()
    watcher.start()
    log.info("已启动：首次扫描 + 目录持续变更监视；每次仅一个工作线程写入 WordPress")
    if ui:
        StatusWindow(ui, inbox, watcher, processor, events, log)
        try:
            ui.mainloop()
        finally:
            watcher.shutdown()
            processor.shutdown()
    else:
        try:
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            log.info("收到 Ctrl+C：退出")
        finally:
            watcher.shutdown()
            processor.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
