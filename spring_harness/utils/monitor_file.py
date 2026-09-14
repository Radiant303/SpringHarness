import fnmatch
import os
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from threading import Lock

import pathspec
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


class FileStatus(Enum):
    """文件状态枚举"""
    MODIFIED = "修改"
    CREATED = "新建"
    DELETED = "删除"


@dataclass
class FileChange:
    """文件变化的数据结构"""
    filepath: Path
    status: FileStatus

    def get_relative_path(self, base_dir: Path) -> Path:
        """获取相对路径"""
        try:
            return self.filepath.relative_to(base_dir)
        except ValueError:
            return self.filepath


class DirectoryMonitor:
    """
    目录监控器类 - 监控指定目录下所有文件的变化
    返回变化的数据而不是直接打印
    """

    def __init__(self, directory_path, file_pattern="*",
                 exclude_dot_dirs=True, use_gitignore=True):
        """
        初始化目录监控器

        参数：
            directory_path: 要监控的目录路径
            file_pattern: 文件匹配模式（如 "*.py" 只监控Python文件）
            exclude_dot_dirs: 是否排除以 . 开头的文件夹（如 .git、.idea）
            use_gitignore: 是否按 gitignore 语法排除最近的 .gitignore
                （从监控目录向上查找）中的规则
        """
        self.directory = Path(directory_path).resolve()
        self.file_pattern = file_pattern
        self.exclude_dot_dirs = exclude_dot_dirs
        self.use_gitignore = use_gitignore

        # 解析后的 .gitignore 规则（None 表示未启用或未找到）
        self._gitignore_spec: pathspec.GitIgnoreSpec | None = None
        # .gitignore 所在目录（监控目录本身或其某个祖先目录）
        self._gitignore_root: Path = self.directory
        # .gitignore 文件路径与修改时间，用于会话期间变更后自动重读
        self._gitignore_path: Path | None = None
        self._gitignore_mtime: float | None = None

        # 保存初始文件内容 {文件路径: 文件内容}
        self.old_contents: dict[Path, list[str]] = {}

        # 记录变化的文件集合
        self.changed_files = set()
        self.created_files = set()
        self.deleted_files = set()

        # watchdog 观察者对象
        self.observer = None

        # 监控状态
        self._running = False
        self._closed = False
        self._lock = Lock()

        # 验证目录是否存在
        if not self.directory.exists():
            raise ValueError(f"目录不存在: {self.directory}")
        if not self.directory.is_dir():
            raise ValueError(f"路径不是目录: {self.directory}")

    def _load_gitignore(self):
        """从监控目录向上查找最近的 .gitignore 并解析（找不到则跳过）

        向上遍历时遇到 .git（仓库边界）或文件系统根即停止。
        支持完整 gitignore 语法：通配符（*、**、?）、! 取反、/ 锚定、
        目录规则（dir/）和 # 注释。
        """
        self._gitignore_spec = None
        self._gitignore_root = self.directory
        self._gitignore_path = None
        self._gitignore_mtime = None
        if not self.use_gitignore:
            return
        current = self.directory
        while True:
            gitignore = current / ".gitignore"
            if gitignore.is_file():
                try:
                    lines = gitignore.read_text(encoding="utf-8").splitlines()
                    mtime = gitignore.stat().st_mtime
                except OSError:
                    return
                self._gitignore_spec = pathspec.GitIgnoreSpec.from_lines(lines)
                self._gitignore_root = current
                self._gitignore_path = gitignore
                self._gitignore_mtime = mtime
                return
            # 到达仓库边界或文件系统根就停止（仓库根的 .gitignore 已检查过）
            if (current / ".git").exists() or current.parent == current:
                return
            current = current.parent

    def _reload_gitignore_if_changed(self):
        """.gitignore 在会话期间被修改或删除时重新加载"""
        if self._gitignore_path is None:
            return
        try:
            mtime = self._gitignore_path.stat().st_mtime
        except OSError:
            mtime = None  # 文件已被删除
        if mtime != self._gitignore_mtime:
            self._load_gitignore()

    def _match_gitignore(self, relative: Path, is_dir: bool = False) -> bool:
        if self._gitignore_spec is None:
            return False
        path = (self.directory.relative_to(self._gitignore_root) / relative).as_posix()
        return bool(
            self._gitignore_spec.check_file(path).include
            or (is_dir and self._gitignore_spec.check_file(path + "/").include)
        )

    def _is_excluded(self, filepath):
        self._reload_gitignore_if_changed()
        try:
            relative = Path(filepath).resolve().relative_to(self.directory)
        except (ValueError, OSError, RuntimeError):
            return True
        return self._relative_excluded(relative)

    def _relative_excluded(self, relative: Path) -> bool:
        return (
            self.exclude_dot_dirs and any(part.startswith(".") for part in relative.parts[:-1])
        ) or self._match_gitignore(relative)

    def _get_all_files(self):
        self._reload_gitignore_if_changed()
        files = []
        pending = [self.directory]
        while pending:
            directory = pending.pop()
            try:
                relative_parent = directory.resolve().relative_to(self.directory)
                with os.scandir(directory) as entries:
                    for entry in entries:
                        path = directory / entry.name
                        relative = relative_parent / entry.name
                        if entry.is_dir():
                            if self.exclude_dot_dirs and entry.name.startswith("."):
                                continue
                            if not entry.is_symlink() and not self._match_gitignore(relative, is_dir=True):
                                pending.append(path)
                        elif fnmatch.fnmatch(entry.name, self.file_pattern):
                            if entry.is_symlink():
                                try:
                                    relative = path.resolve().relative_to(self.directory)
                                except (ValueError, OSError, RuntimeError):
                                    continue
                            if not self._relative_excluded(relative):
                                files.append(path)
            except (ValueError, OSError, RuntimeError):
                continue
        return files

    def _read_file(self, filepath):
        """读取文件内容"""
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                return f.readlines()
        except (OSError, PermissionError):
            return None

    def _read_stable_file(self, filepath, retries=5, interval=0.05):
        """稳定地读取文件"""
        previous = None
        for _ in range(retries):
            current = self._read_file(filepath)
            if current is None:
                time.sleep(interval)
                continue
            if current == previous:
                return current
            previous = current
            time.sleep(interval)
        return previous

    def _snapshot_directory(self, stable_check: bool = False):
        """获取目录当前状态的快照

        参数：
            stable_check: True 时对监控期间报告过变化的文件做稳定性重读
                （防止读到写入中途的内容），其余文件只读一遍
        """
        snapshot = {}
        changed = self.changed_files | self.created_files
        for file_path in self._get_all_files():
            if stable_check and file_path in changed:
                content = self._read_stable_file(file_path)
            else:
                content = self._read_file(file_path)
            if content is not None:
                snapshot[file_path] = content
        return snapshot

    def _on_file_change(self, filepath):
        """文件变化时的处理"""
        if not self._running:
            return

        if not self._matches_pattern(filepath):
            return

        with self._lock:
            self.changed_files.add(filepath)

    def _matches_pattern(self, filepath):
        """检查文件是否匹配模式且不在排除范围内"""
        if self._is_excluded(filepath):
            return False
        if self.file_pattern == "*":
            return True
        return fnmatch.fnmatch(Path(filepath).name, self.file_pattern)

    def start(self):
        with self._lock:
            if self._running or self._closed:
                return
            try:
                self._start()
            except BaseException:
                self._stop_observer()
                self._clear()
                raise

    def _start(self):
        self._load_gitignore()
        self.changed_files.clear()
        self.created_files.clear()
        self.deleted_files.clear()
        monitor = self

        class DirectoryHandler(FileSystemEventHandler):
            def on_modified(self, event):
                if not event.is_directory:
                    monitor._on_file_change(Path(os.fsdecode(event.src_path)))

            def on_created(self, event):
                path = Path(os.fsdecode(event.src_path))
                if not event.is_directory and monitor._running and monitor._matches_pattern(path):
                    with monitor._lock:
                        monitor.created_files.add(path)
                        monitor.changed_files.add(path)

            def on_deleted(self, event):
                path = Path(os.fsdecode(event.src_path))
                if not event.is_directory and monitor._running and monitor._matches_pattern(path):
                    with monitor._lock:
                        monitor.deleted_files.add(path)

            def on_moved(self, event):
                if event.is_directory or not monitor._running:
                    return
                src = Path(os.fsdecode(event.src_path))
                dest = Path(os.fsdecode(event.dest_path))
                with monitor._lock:
                    if monitor._matches_pattern(src):
                        monitor.deleted_files.add(src)
                    if monitor._matches_pattern(dest):
                        monitor.created_files.add(dest)
                        monitor.changed_files.add(dest)

        self.observer = Observer()
        self.observer.schedule(DirectoryHandler(), str(self.directory), recursive=True)
        self._running = True
        self.observer.start()

    def _stop_observer(self):
        self._running = False
        if self.observer is not None:
            self.observer.stop()
            if self.observer.is_alive():
                self.observer.join()
            self.observer = None

    def _clear(self):
        self.old_contents.clear()
        self.changed_files.clear()
        self.created_files.clear()
        self.deleted_files.clear()

    def close(self):
        with self._lock:
            self._closed = True
            self._stop_observer()
            self._clear()

    def stop(self) -> list[FileChange]:
        # 允许操作系统内核与 watchdog 线程将缓冲区中的最后事件排空
        time.sleep(0.05)
        with self._lock:
            if not self._running:
                return []
            self._stop_observer()
            changes = self._changes()
            self._clear()
            return changes

    def _changes(self) -> list[FileChange]:
        changes = []
        all_candidates = sorted(self.changed_files | self.created_files | self.deleted_files)

        for filepath in all_candidates:
            exists = filepath.exists()
            was_created = filepath in self.created_files
            was_deleted = filepath in self.deleted_files

            if exists:
                if was_created and not was_deleted:
                    changes.append(FileChange(filepath=filepath, status=FileStatus.CREATED))
                else:
                    changes.append(FileChange(filepath=filepath, status=FileStatus.MODIFIED))
            else:
                if not was_created and was_deleted:
                    changes.append(FileChange(filepath=filepath, status=FileStatus.DELETED))

        return changes

    def changes_to_string(self, changes: list[FileChange]) -> str | None:
        """将文件变化格式化为适合发送给大模型的文本。

        输出包含变化摘要、相对路径及变化状态（新建/修改/删除），不再包含具体的 diff 内容。
        相对路径可避免将本机绝对路径传给大模型；没有变化时返回 `None`。
        """
        if not changes:
            return None

        lines = [f"检测到 {len(changes)} 个文件变化："]
        for change in changes:
            relative_path = change.get_relative_path(self.directory)
            lines.append(f"- [{change.status.value}] {relative_path}")

        return "\n".join(lines)
