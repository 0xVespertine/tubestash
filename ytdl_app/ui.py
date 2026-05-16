"""The single-window UI."""
from __future__ import annotations

import os
import subprocess

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import (
    QAction, QColor, QGuiApplication, QIcon, QPainter, QPixmap, QPolygonF,
)
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMenu, QMessageBox, QProgressBar,
    QPushButton, QSizePolicy, QStackedWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from . import config, history
from .worker import DownloadWorker, EngineUpdater, InfoWorker

QUALITIES = ["Best (MP4)", "1080p", "720p", "Audio only (MP3)"]

STYLE = """
QWidget { background:#16181d; color:#e6e8ec;
          font-family:'Segoe UI'; font-size:13px; }
QLabel#h1 { font-size:20px; font-weight:600; color:#fff; }
QLabel#sub { color:#9aa0a6; }
QLabel#ptitle { font-size:14px; font-weight:600; color:#fff; }
QLabel#empty { color:#5b616b; font-size:13px; }
QLineEdit, QComboBox {
    background:#23262e; border:1px solid #343844; border-radius:8px;
    padding:9px 10px; selection-background-color:#3b82f6; }
QLineEdit:focus, QComboBox:focus { border:1px solid #3b82f6; }
QComboBox::drop-down { border:0; width:22px; }
QComboBox QAbstractItemView {
    background:#23262e; border:1px solid #343844;
    selection-background-color:#3b82f6; outline:0; }
QPushButton {
    background:#2a2e38; border:1px solid #3a3f4b; border-radius:8px;
    padding:9px 16px; }
QPushButton:hover { background:#333845; }
QPushButton:disabled { color:#6b7280; background:#22252c; }
QPushButton#primary {
    background:#3b82f6; border:0; font-weight:600; color:#fff; }
QPushButton#primary:hover { background:#2f6fe0; }
QPushButton#danger:hover { background:#7f1d1d; }
QProgressBar {
    background:#23262e; border:0; border-radius:6px; height:10px;
    text-align:center; }
QProgressBar::chunk { background:#3b82f6; border-radius:6px; }
QCheckBox::indicator {
    width:16px; height:16px; border:1px solid #3a3f4b;
    border-radius:4px; background:#23262e; }
QCheckBox::indicator:checked { background:#3b82f6; border:1px solid #3b82f6; }
QTableWidget {
    background:#1b1e24; border:1px solid #2a2e38; border-radius:8px;
    gridline-color:#2a2e38; }
QTableWidget::item { padding:6px; }
QTableWidget::item:selected { background:#2f3a52; }
QHeaderView::section {
    background:#23262e; color:#9aa0a6; border:0;
    padding:7px; font-weight:600; }
QFrame#card, QFrame#preview {
    background:#1b1e24; border:1px solid #2a2e38; border-radius:12px; }
QMenu { background:#23262e; border:1px solid #343844; padding:4px; }
QMenu::item { padding:6px 22px; border-radius:6px; }
QMenu::item:selected { background:#3b82f6; }
"""

# Arabic / RTL character ranges, for natural title alignment.
_RTL = tuple(range(0x0590, 0x0700)) + tuple(range(0xFB50, 0xFE00))


def _is_rtl(text: str) -> bool:
    return any(ord(c) in _RTL for c in text[:40])


def make_app_icon() -> QIcon:
    """Draw a rounded red tile with a white play triangle — no asset file."""
    pm = QPixmap(256, 256)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#ef4444"))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(8, 8, 240, 240, 52, 52)
    p.setBrush(QColor("#ffffff"))
    tri = QPolygonF([QPointF(102, 80), QPointF(102, 176), QPointF(184, 128)])
    p.drawPolygon(tri)
    p.end()
    return QIcon(pm)


def _card(name: str = "card") -> QFrame:
    f = QFrame()
    f.setObjectName(name)
    return f


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = config.load_settings()
        self.ffmpeg_dir = config.find_ffmpeg()
        self.worker: DownloadWorker | None = None
        self.info_worker: InfoWorker | None = None
        self._last_info_url = ""

        self.setWindowTitle("YouTube Downloader")
        self.setWindowIcon(make_app_icon())
        self.setMinimumSize(720, 680)
        self.setStyleSheet(STYLE)

        self._info_timer = QTimer(self)
        self._info_timer.setSingleShot(True)
        self._info_timer.setInterval(550)
        self._info_timer.timeout.connect(self._fetch_info)

        self._build()
        self._load_history()
        self._prefill_from_clipboard()
        self._start_engine_check()

    # ---------- layout ----------
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(14)

        title = QLabel("YouTube Downloader")
        title.setObjectName("h1")
        root.addWidget(title)

        # --- input card ---
        card = _card()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(18, 16, 18, 16)
        cl.setSpacing(12)

        url_row = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("Paste a YouTube video or playlist link…")
        self.url_edit.returnPressed.connect(self._start)
        self.url_edit.textChanged.connect(self._on_url_changed)
        paste_btn = QPushButton("Paste")
        paste_btn.clicked.connect(self._paste)
        url_row.addWidget(self.url_edit)
        url_row.addWidget(paste_btn)
        cl.addLayout(url_row)

        # --- preview (hidden until a link resolves) ---
        self.preview = _card("preview")
        self.preview.hide()
        pl = QHBoxLayout(self.preview)
        pl.setContentsMargins(12, 12, 12, 12)
        pl.setSpacing(14)
        self.thumb_lbl = QLabel()
        self.thumb_lbl.setFixedSize(160, 90)
        self.thumb_lbl.setStyleSheet("border-radius:8px; background:#23262e;")
        self.thumb_lbl.setAlignment(Qt.AlignCenter)
        pl.addWidget(self.thumb_lbl)
        meta = QVBoxLayout()
        meta.setSpacing(4)
        self.ptitle_lbl = QLabel()
        self.ptitle_lbl.setObjectName("ptitle")
        self.ptitle_lbl.setWordWrap(True)
        self.pmeta_lbl = QLabel()
        self.pmeta_lbl.setObjectName("sub")
        meta.addStretch(1)
        meta.addWidget(self.ptitle_lbl)
        meta.addWidget(self.pmeta_lbl)
        meta.addStretch(1)
        pl.addLayout(meta, 1)
        cl.addWidget(self.preview)

        opt_row = QHBoxLayout()
        self.quality_box = QComboBox()
        self.quality_box.addItems(QUALITIES)
        if self.settings["quality"] in QUALITIES:
            self.quality_box.setCurrentText(self.settings["quality"])
        self.quality_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.playlist_chk = QCheckBox("Whole playlist")
        self.playlist_chk.setChecked(bool(self.settings["playlist"]))
        opt_row.addWidget(QLabel("Quality"))
        opt_row.addWidget(self.quality_box, 1)
        opt_row.addSpacing(10)
        opt_row.addWidget(self.playlist_chk)
        cl.addLayout(opt_row)

        folder_row = QHBoxLayout()
        self.folder_lbl = QLabel(self.settings["download_dir"])
        self.folder_lbl.setObjectName("sub")
        self.folder_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        change_btn = QPushButton("Change…")
        change_btn.clicked.connect(self._choose_folder)
        open_btn = QPushButton("Open")
        open_btn.clicked.connect(
            lambda: self._open_path(self.settings["download_dir"]))
        folder_row.addWidget(QLabel("Save to"))
        folder_row.addWidget(self.folder_lbl, 1)
        folder_row.addWidget(change_btn)
        folder_row.addWidget(open_btn)
        cl.addLayout(folder_row)

        self.action_btn = QPushButton("Download")
        self.action_btn.setObjectName("primary")
        self.action_btn.setMinimumHeight(40)
        self.action_btn.clicked.connect(self._on_action)
        cl.addWidget(self.action_btn)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.hide()
        cl.addWidget(self.progress)

        self.status_lbl = QLabel("")
        self.status_lbl.setObjectName("sub")
        self.status_lbl.hide()
        cl.addWidget(self.status_lbl)

        root.addWidget(card)

        # --- history ---
        hist_head = QHBoxLayout()
        h = QLabel("History")
        h.setObjectName("h1")
        h.setStyleSheet("font-size:15px;")
        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("danger")
        clear_btn.clicked.connect(self._clear_history)
        hist_head.addWidget(h)
        hist_head.addStretch(1)
        hist_head.addWidget(clear_btn)
        root.addLayout(hist_head)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Title", "Quality", "Date"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._history_menu)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.doubleClicked.connect(self._open_selected)

        self.empty_lbl = QLabel("No downloads yet — paste a link above.")
        self.empty_lbl.setObjectName("empty")
        self.empty_lbl.setAlignment(Qt.AlignCenter)

        self.hist_stack = QStackedWidget()
        self.hist_stack.addWidget(self.table)      # index 0
        self.hist_stack.addWidget(self.empty_lbl)  # index 1
        root.addWidget(self.hist_stack, 1)

        hint = QLabel("Double-click to show the file • right-click for more")
        hint.setObjectName("sub")
        root.addWidget(hint)

        self.engine_lbl = QLabel("Engine: checking…")
        self.engine_lbl.setObjectName("sub")
        root.addWidget(self.engine_lbl)

    # ---------- url / preview ----------
    def _paste(self) -> None:
        self.url_edit.setText(QGuiApplication.clipboard().text().strip())

    def _prefill_from_clipboard(self) -> None:
        clip = QGuiApplication.clipboard().text().strip()
        if clip.startswith("http") and (
            "youtu" in clip or "youtube.com" in clip):
            self.url_edit.setText(clip)

    def _on_url_changed(self, _text: str) -> None:
        # Reset transient state when the link changes.
        self.progress.hide()
        self.status_lbl.hide()
        url = self.url_edit.text().strip()
        if not url.startswith("http"):
            self.preview.hide()
            self._last_info_url = ""
            return
        self._info_timer.start()  # debounce

    def _fetch_info(self) -> None:
        url = self.url_edit.text().strip()
        if not url.startswith("http") or url == self._last_info_url:
            return
        if self.info_worker and self.info_worker.isRunning():
            return
        self._last_info_url = url
        self.pmeta_lbl.setText("Loading preview…")
        self.ptitle_lbl.setText("")
        self.thumb_lbl.clear()
        self.preview.show()
        self.info_worker = InfoWorker(url)
        self.info_worker.loaded.connect(self._on_info)
        self.info_worker.failed.connect(lambda: self.preview.hide())
        self.info_worker.start()

    def _on_info(self, data: dict) -> None:
        t = data["title"]
        self.ptitle_lbl.setAlignment(
            Qt.AlignRight if _is_rtl(t) else Qt.AlignLeft)
        self.ptitle_lbl.setText(t)
        bits = [b for b in (data["uploader"], data["duration"]) if b]
        self.pmeta_lbl.setText("  •  ".join(bits))
        if data.get("thumb"):
            pm = QPixmap()
            if pm.loadFromData(data["thumb"]):
                self.thumb_lbl.setPixmap(pm.scaled(
                    160, 90, Qt.KeepAspectRatioByExpanding,
                    Qt.SmoothTransformation))

    # ---------- folder ----------
    def _choose_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(
            self, "Choose download folder", self.settings["download_dir"])
        if d:
            self.settings["download_dir"] = d
            self.folder_lbl.setText(d)
            config.save_settings(self.settings)

    def _open_path(self, path: str) -> None:
        try:
            if path and os.path.isfile(path):
                subprocess.run(["explorer", "/select,", os.path.normpath(path)])
            elif os.path.isdir(path):
                os.startfile(path)  # noqa: S606
            else:
                os.startfile(self.settings["download_dir"])  # noqa: S606
        except OSError:
            pass

    # ---------- engine update ----------
    def _start_engine_check(self) -> None:
        if not self.settings.get("auto_update_engine", True):
            self.engine_lbl.setText("Engine: auto-update off")
            return
        self._updater = EngineUpdater()
        self._updater.result.connect(self.engine_lbl.setText)
        self._updater.start()

    # ---------- download flow ----------
    def _on_action(self) -> None:
        if self.worker and self.worker.isRunning():
            self.action_btn.setEnabled(False)
            self.action_btn.setText("Cancelling…")
            self.worker.cancel()
        else:
            self._start()

    def _start(self) -> None:
        url = self.url_edit.text().strip()
        if not url:
            self.url_edit.setFocus()
            return
        if not (self.worker is None or not self.worker.isRunning()):
            return

        self.settings["quality"] = self.quality_box.currentText()
        self.settings["playlist"] = self.playlist_chk.isChecked()
        config.save_settings(self.settings)

        self._set_busy(True)
        self.progress.setValue(0)
        self.progress.setRange(0, 0)  # indeterminate until first bytes
        self.progress.show()
        self.status_lbl.show()
        self.status_lbl.setText("Starting…")

        self.worker = DownloadWorker(
            url, self.settings["quality"], self.settings["download_dir"],
            self.settings["playlist"], self.ffmpeg_dir)
        self.worker.progress.connect(self._on_progress)
        self.worker.stage.connect(self.status_lbl.setText)
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_progress(self, pct: float, speed: str, eta: str,
                      name: str) -> None:
        if self.progress.maximum() == 0:
            self.progress.setRange(0, 100)
        self.progress.setValue(int(pct))
        title = (name[:60] + "…") if len(name) > 60 else name
        self.status_lbl.setText(
            f"{pct:4.1f}%   •   {speed}/s   •   ETA {eta}   •   {title}")

    def _on_done(self, results: list) -> None:
        for title, url, path, quality in results:
            history.add_entry(title, url, path, quality)
        self._load_history()
        self._set_busy(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        n = len(results)
        self.status_lbl.setText(
            f"✓ Done — {n} file{'s' if n != 1 else ''} saved")

    def _on_failed(self, msg: str) -> None:
        self._set_busy(False)
        self.progress.hide()
        self.status_lbl.setText(f"✕ {msg}")

    def _set_busy(self, busy: bool) -> None:
        self.url_edit.setEnabled(not busy)
        self.quality_box.setEnabled(not busy)
        self.playlist_chk.setEnabled(not busy)
        self.action_btn.setEnabled(True)
        self.action_btn.setObjectName("danger" if busy else "primary")
        self.action_btn.setText("Cancel" if busy else "Download")
        self.action_btn.style().unpolish(self.action_btn)
        self.action_btn.style().polish(self.action_btn)

    # ---------- history ----------
    def _load_history(self) -> None:
        rows = history.load_history()
        self.table.setRowCount(len(rows))
        for r, e in enumerate(rows):
            t = QTableWidgetItem(e.get("title", ""))
            t.setData(Qt.UserRole, e.get("filepath", ""))
            t.setData(Qt.UserRole + 1, e.get("url", ""))
            if _is_rtl(e.get("title", "")):
                t.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(r, 0, t)
            self.table.setItem(r, 1, QTableWidgetItem(e.get("quality", "")))
            self.table.setItem(r, 2, QTableWidgetItem(e.get("date", "")))
        self.hist_stack.setCurrentIndex(0 if rows else 1)

    def _open_selected(self) -> None:
        row = self.table.currentRow()
        if row >= 0:
            self._open_path(self.table.item(row, 0).data(Qt.UserRole))

    def _history_menu(self, pos) -> None:
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        self.table.selectRow(row)
        item = self.table.item(row, 0)
        path = item.data(Qt.UserRole)
        url = item.data(Qt.UserRole + 1)

        menu = QMenu(self)
        act_file = QAction("Open file", self)
        act_file.setEnabled(bool(path) and os.path.isfile(path))
        act_file.triggered.connect(lambda: self._open_file(path))
        act_folder = QAction("Show in folder", self)
        act_folder.triggered.connect(lambda: self._open_path(path))
        act_copy = QAction("Copy link", self)
        act_copy.setEnabled(bool(url))
        act_copy.triggered.connect(
            lambda: QGuiApplication.clipboard().setText(url))
        act_rm = QAction("Remove from history", self)
        act_rm.triggered.connect(lambda: self._remove_entry(row))

        menu.addAction(act_file)
        menu.addAction(act_folder)
        menu.addAction(act_copy)
        menu.addSeparator()
        menu.addAction(act_rm)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _open_file(self, path: str) -> None:
        try:
            os.startfile(path)  # noqa: S606
        except OSError:
            pass

    def _remove_entry(self, row: int) -> None:
        history.remove_entry(row)
        self._load_history()

    def _clear_history(self) -> None:
        if not history.load_history():
            return
        if QMessageBox.question(
            self, "Clear history",
            "Remove all history entries? (Downloaded files are kept.)"
        ) == QMessageBox.Yes:
            history.clear_history()
            self._load_history()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(3000)
        event.accept()


def run() -> None:
    # Make Windows use our window icon in the taskbar (own app id).
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "ksoft.youtube.downloader")
    except Exception:  # noqa: BLE001 - cosmetic only
        pass
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("YouTube Downloader")
    app.setWindowIcon(make_app_icon())
    win = MainWindow()
    win.show()
    app.exec()
