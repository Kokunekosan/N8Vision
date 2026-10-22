"""Add-only directory watcher. Existing images are never opened or re-statted."""
import os
import threading
import time
import uuid
from pathlib import Path


class NewNoticer:
    def __init__(self, root, recursive, extensions):
        self.root = Path(root)
        self.epoch = uuid.uuid4().hex
        self.recursive = recursive
        self.extensions = extensions
        self.dirs = {}
        self.files = {}
        self.events = []
        self.changed = []
        self.lock = threading.RLock()
        self.last_check = 0
        self.intake_cursor = 0
        self.recheck_cursor = 0
        self.dirty = set()
        self._start_native_watch()

    def _mark_change(self, name):
        with self.lock:
            self.dirty.add(str((self.root / name).parent))

    def _start_native_watch(self):
        if os.name != 'nt':
            return
        import ctypes
        from ctypes import wintypes
        api = ctypes.WinDLL('kernel32', use_last_error=True)
        api.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        api.CreateFileW.restype = wintypes.HANDLE
        api.ReadDirectoryChangesW.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p, ctypes.c_void_p]
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = api.CreateFileW(str(self.root), 1, 7, None, 3, 0x02000000, None)
        if handle == ctypes.c_void_p(-1).value:
            return  # Timestamp checks and rotating safety listings remain available.
        def listen():
            buffer = ctypes.create_string_buffer(65536)
            count = wintypes.DWORD()
            try:
                while api.ReadDirectoryChangesW(handle, buffer, len(buffer), self.recursive, 1 | 2 | 8 | 16, ctypes.byref(count), None, None):
                    if not count.value:
                        with self.lock:
                            self.dirty.update(self.dirs)
                        continue
                    offset = 0
                    while offset + 12 <= count.value:
                        data = buffer.raw
                        following = int.from_bytes(data[offset:offset+4], 'little')
                        length = int.from_bytes(data[offset+8:offset+12], 'little')
                        name = data[offset+12:offset+12+length].decode('utf-16-le')
                        self._mark_change(name)
                        if not following:
                            break
                        offset += following
            finally:
                api.CloseHandle(handle)
        threading.Thread(target=listen, name='n8-directory-events', daemon=True).start()

    def sweep(self):
        with self.lock:
            changed = []
            pending = list(self.dirs) or [str(self.root)]
            # One safety listing per sweep catches coarse/stale filesystem stamps.
            forced = None
            if self.dirs and time.monotonic() - self.last_check >= 9:
                forced = pending[self.recheck_cursor % len(pending)]
                self.recheck_cursor += 1
            visited = set()
            dirty = self.dirty
            self.dirty = set()
            while pending:
                raw = pending.pop()
                if raw in visited:
                    continue
                visited.add(raw)
                try:
                    stamp = os.stat(raw).st_mtime_ns
                    if self.dirs.get(raw) == stamp and raw != forced and raw not in dirty:
                        continue
                    # Cache the pre-list stamp: a concurrent creation triggers a retry.
                    retry = False
                    with os.scandir(raw) as entries:
                        for entry in entries:
                            if entry.is_dir(follow_symlinks=False):
                                if self.recursive and entry.name not in ('.N8VisionCache', '.N8VisionExport') and entry.path not in self.dirs:
                                    self.dirs[entry.path] = None
                                    pending.append(entry.path)
                            elif Path(entry.name).suffix.lower() in self.extensions and entry.path not in self.files:
                                if not entry.is_file(follow_symlinks=False):
                                    continue
                                try:
                                    stat = entry.stat(follow_symlinks=False)
                                except OSError:
                                    retry = True
                                    continue
                                # Zero-byte outputs are retried after their writer finishes.
                                if not stat.st_size:
                                    retry = True
                                    continue
                                record = dict(name=entry.name, path=entry.path, size=stat.st_size, mtime=stat.st_mtime)
                                self.files[entry.path] = record
                                self.events.append(record)
                    self.dirs[raw] = None if retry else stamp
                    changed.append(raw)
                except OSError:
                    # Keep the previous stamp so transient failures are retried.
                    continue
            self.changed = changed
            self.last_check = time.monotonic()
            return changed

    def record_file(self, path):
        """Authoritative completed-output intake, independent of directory timestamps."""
        path=Path(path).resolve()
        try:relative=path.relative_to(self.root.resolve())
        except ValueError:return False
        if not self.recursive and len(relative.parts)!=1:return False
        if path.suffix.lower() not in self.extensions:return False
        try:
            stat=path.stat()
            if not path.is_file() or not stat.st_size:return False
        except OSError:return False
        raw=str(path)
        with self.lock:
            previous=self.files.get(raw)
            if previous and previous.get('size')==stat.st_size and previous.get('mtime')==stat.st_mtime:return False
            record=dict(name=path.name,path=raw,size=stat.st_size,mtime=stat.st_mtime)
            self.files[raw]=record;self.events.append(record)
            self.dirty.add(str(path.parent))
        return True

    def packet(self, since, limit=500):
        with self.lock:
            since = min(max(0, since), len(self.events))
            records = self.events[since:since + limit]
            return dict(files=[dict(x) for x in records], epoch=self.epoch, cursor=since + len(records), more=since + len(records) < len(self.events), changed_directories=list(self.changed))
