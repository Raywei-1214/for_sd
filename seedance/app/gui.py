import html
import logging
import sys
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from threading import Event

from PySide6.QtCore import QEasingCurve, QObject, Qt, QThread, QUrl, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from seedance.core.config import DEFAULT_MAX_WORKERS, DEFAULT_TOTAL_COUNT, LOG_FILE, MAX_WORKERS, MIN_WORKERS, REPORT_DIR, SUCCESS_DIR, TEMP_EMAIL_PROVIDERS
from seedance.core.logger import get_logger
from seedance.core.models import BatchProgress, BatchSummary
from seedance.infra.notion_client import NotionClient
from seedance.orchestration.batch_runner import main as run_batch

# ================================
# Organic / Natural 风格样式表
# 目的: 用自然、有机、柔和的界面语言构建新的桌面工作台
# 边界: 仅负责视觉，不承担业务状态逻辑
# ================================
WINDOW_STYLESHEET = """
QWidget {
  color: #2C2C24;
  font-family: "Inter", "SF Pro Display", "Segoe UI", "Microsoft YaHei UI", "PingFang SC", "Helvetica Neue";
  font-size: 13px;
  selection-background-color: rgba(93, 112, 82, 0.18);
}

QMainWindow {
  background:
    qradialgradient(cx: 0.14, cy: 0.18, radius: 0.38, fx: 0.14, fy: 0.18, stop: 0 rgba(193, 140, 93, 42), stop: 1 rgba(193, 140, 93, 0)),
    qradialgradient(cx: 0.82, cy: 0.1, radius: 0.34, fx: 0.82, fy: 0.1, stop: 0 rgba(93, 112, 82, 45), stop: 1 rgba(93, 112, 82, 0)),
    qradialgradient(cx: 0.78, cy: 0.86, radius: 0.42, fx: 0.78, fy: 0.86, stop: 0 rgba(230, 220, 205, 110), stop: 1 rgba(230, 220, 205, 0)),
    linear-gradient(180deg, #FDFCF8, #F6F1E9);
}

QFrame#Card {
  background: rgba(254, 254, 250, 0.92);
  border: 1px solid rgba(222, 216, 207, 0.78);
  border-radius: 32px;
}

QFrame#HeroCard {
  background:
    qradialgradient(cx: 0.16, cy: 0.28, radius: 0.4, fx: 0.16, fy: 0.28, stop: 0 rgba(230, 220, 205, 180), stop: 1 rgba(230, 220, 205, 0)),
    qradialgradient(cx: 0.88, cy: 0.18, radius: 0.32, fx: 0.88, fy: 0.18, stop: 0 rgba(193, 140, 93, 54), stop: 1 rgba(193, 140, 93, 0)),
    qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, stop: 0 rgba(254, 254, 250, 0.98), stop: 1 rgba(240, 235, 229, 0.94));
  border: 1px solid rgba(222, 216, 207, 0.86);
  border-radius: 38px;
}

QFrame#StatCard {
  background: rgba(255, 252, 247, 0.95);
  border: 1px solid rgba(222, 216, 207, 0.72);
  border-radius: 28px;
}

QProgressBar {
  min-height: 18px;
  max-height: 18px;
  border: 1px solid rgba(222, 216, 207, 0.82);
  border-radius: 9px;
  background: rgba(240, 235, 229, 0.86);
  text-align: center;
  color: #4A4A40;
  font-size: 10px;
}

QProgressBar::chunk {
  border-radius: 8px;
  background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0, stop: 0 #5D7052, stop: 1 #75896A);
}

QLabel#Title {
  font-family: "Inter", "SF Pro Display", "Segoe UI", "Microsoft YaHei UI", "PingFang SC", "Helvetica Neue";
  font-size: 31px;
  font-weight: 700;
  color: #2C2C24;
}

QLabel#SectionTitle {
  font-family: "Inter", "SF Pro Display", "Segoe UI", "Microsoft YaHei UI", "PingFang SC", "Helvetica Neue";
  font-size: 17px;
  font-weight: 700;
  color: #2C2C24;
}

QLabel#SectionNote {
  font-size: 11px;
  color: #78786C;
}

QLabel#ValueHero {
  font-family: "Inter", "SF Pro Display", "Segoe UI", "Microsoft YaHei UI", "PingFang SC", "Helvetica Neue";
  font-size: 17px;
  font-weight: 700;
  color: #2C2C24;
}

QLabel#ValueCard {
  font-family: "Inter", "SF Pro Display", "Segoe UI", "Microsoft YaHei UI", "PingFang SC", "Helvetica Neue";
  font-size: 14px;
  font-weight: 700;
  color: #2C2C24;
}

QLabel#CaptionCard {
  font-size: 11px;
  color: #78786C;
}

QLabel#FieldLabel {
  font-size: 11px;
  font-weight: 700;
  color: #5F5F52;
}

QCheckBox {
  spacing: 8px;
  color: #4A4A40;
  font-size: 12px;
  min-height: 24px;
}

QCheckBox::indicator {
  width: 22px;
  height: 22px;
  border-radius: 11px;
  border: 1px solid #DED8CF;
  background: rgba(255, 255, 255, 0.76);
}

QCheckBox::indicator:checked {
  background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, stop: 0 #5D7052, stop: 1 #75896A);
  border: 1px solid #5D7052;
}

QSpinBox,
QComboBox,
QTextEdit {
  background: rgba(255, 255, 255, 0.75);
  color: #2C2C24;
  border: 1px solid #DED8CF;
  border-radius: 20px;
  padding: 5px 12px;
}

QSpinBox,
QComboBox {
  min-height: 30px;
}

QSpinBox::up-button,
QSpinBox::down-button,
QComboBox::drop-down {
  background: transparent;
}

QSpinBox QLineEdit,
QComboBox QLineEdit,
QSpinBox QWidgetLineControl,
QComboBox QWidgetLineControl {
  color: #2C2C24;
  background: transparent;
  selection-background-color: rgba(230, 220, 205, 0.78);
}

QSpinBox:focus,
QComboBox:focus,
QTextEdit:focus {
  border: 1px solid rgba(93, 112, 82, 0.48);
}

QComboBox::drop-down {
  border: none;
  width: 28px;
}

QComboBox QAbstractItemView {
  background: rgba(253, 252, 248, 0.98);
  color: #2C2C24;
  border: 1px solid #DED8CF;
  border-radius: 18px;
  selection-background-color: rgba(230, 220, 205, 0.78);
}

QPushButton {
  min-height: 40px;
  border-radius: 22px;
  padding: 0 18px;
  font-weight: 700;
}

QPushButton#PrimaryButton {
  background: #5D7052;
  color: #F3F4F1;
  border: 1px solid rgba(93, 112, 82, 0.68);
  border-radius: 22px;
  padding: 0 20px;
}

QPushButton#PrimaryButton:hover {
  background: #6A7D5F;
}

QPushButton#PrimaryButton[busy="true"],
QPushButton#PrimaryButton[busy="true"]:disabled {
  background: #5D7052;
  color: #F3F4F1;
  border: 1px solid rgba(93, 112, 82, 0.68);
}

QPushButton#SecondaryButton {
  background: rgba(255, 255, 255, 0.18);
  color: #C18C5D;
  border: 2px solid rgba(193, 140, 93, 0.72);
}

QPushButton#SecondaryButton:hover {
  background: rgba(230, 220, 205, 0.48);
}

QPushButton#DangerButton {
  background: rgba(168, 84, 72, 0.12);
  color: #A85448;
  border: 2px solid rgba(168, 84, 72, 0.45);
}

QPushButton#DangerButton:hover {
  background: rgba(168, 84, 72, 0.2);
}

QPushButton#DangerButton[busy="true"],
QPushButton#DangerButton[busy="true"]:disabled {
  background: rgba(168, 84, 72, 0.12);
  color: #A85448;
  border: 2px solid rgba(168, 84, 72, 0.45);
}

QPushButton:disabled {
  color: rgba(74, 74, 64, 0.46);
  background: rgba(240, 235, 229, 0.72);
  border: 1px solid rgba(222, 216, 207, 0.82);
}

QTextEdit {
  background: rgba(254, 254, 250, 0.95);
  color: #3A392F;
  font-family: "SF Mono", "JetBrains Mono", "Consolas", "Courier New";
  font-size: 11px;
  border-radius: 34px;
}
"""

logger = get_logger()


@dataclass(frozen=True)
class GuiRunConfig:
    total_count: int
    max_workers: int
    headless: bool
    debug_mode: bool
    notion_enabled: bool
    specified_email: str | None
    stop_event: Event | None


class QtLogHandler(logging.Handler, QObject):
    log_message = Signal(str)

    def __init__(self):
        QObject.__init__(self)
        logging.Handler.__init__(self)
        self.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
        except Exception:
            message = record.getMessage()
        self.log_message.emit(message)


class WorkerStream:
    def __init__(self, emit_callback):
        self.emit_callback = emit_callback

    def write(self, text: str) -> int:
        clean_text = text.strip()
        if clean_text:
            self.emit_callback(clean_text)
        return len(text)

    def flush(self) -> None:
        return None


class BatchWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)
    log_line = Signal(str)
    progress = Signal(object)

    def __init__(self, run_config: GuiRunConfig):
        super().__init__()
        self.run_config = run_config

    def run(self) -> None:
        # ================================
        # 运行器在后台线程执行批量任务
        # 目的: 不阻塞 GUI 主线程
        # 边界: 当前不负责主动中断浏览器任务
        # ================================
        stream = WorkerStream(self.log_line.emit)
        try:
            with redirect_stdout(stream), redirect_stderr(stream):
                summary = run_batch(
                    headless=self.run_config.headless,
                    debug_mode=self.run_config.debug_mode,
                    total_count=self.run_config.total_count,
                    max_workers=self.run_config.max_workers,
                    specified_email=self.run_config.specified_email,
                    notion_enabled=self.run_config.notion_enabled,
                    stop_event=self.run_config.stop_event,
                    progress_callback=self.progress.emit,
                    interactive=False,
                )
            self.finished.emit(summary)
        except Exception as exc:
            self.failed.emit(str(exc))


class SeedanceMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.worker_thread: QThread | None = None
        self.worker: BatchWorker | None = None
        self.last_summary: BatchSummary | None = None
        self.stop_event: Event | None = None
        self._button_animations: dict[QPushButton, QVariantAnimation] = {}

        self.setWindowTitle("拾米 - SD账号注册")
        self.resize(1360, 880)
        self.setMinimumSize(1200, 760)
        self.setStyleSheet(WINDOW_STYLESHEET)
        self.setFont(QFont("Inter", 9))

        self.qt_log_handler = QtLogHandler()
        self.qt_log_handler.log_message.connect(self.append_log)
        logger.addHandler(self.qt_log_handler)

        self._build_ui()
        self._apply_defaults()

    def closeEvent(self, event) -> None:
        if self.worker_thread and self.worker_thread.isRunning():
            reply = QMessageBox.question(
                self,
                "任务仍在运行",
                "当前注册任务还在执行。关闭窗口不会主动终止浏览器流程，确认继续关闭吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                event.ignore()
                return

        logger.removeHandler(self.qt_log_handler)
        super().closeEvent(event)

    def _build_ui(self) -> None:
        central_widget = QWidget()
        central_widget.setContentsMargins(20, 20, 20, 20)
        self.setCentralWidget(central_widget)

        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(14)

        root_layout.addWidget(self._build_header_card())

        content_layout = QHBoxLayout()
        content_layout.setSpacing(14)
        root_layout.addLayout(content_layout, 1)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFixedWidth(470)
        left_scroll.setFrameShape(QFrame.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setLayoutDirection(Qt.RightToLeft)
        left_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        content_layout.addWidget(left_scroll, 0)

        left_panel = QWidget()
        left_panel.setLayoutDirection(Qt.LeftToRight)
        left_column = QVBoxLayout(left_panel)
        left_column.setSpacing(14)
        left_column.setContentsMargins(0, 0, 0, 0)
        left_scroll.setWidget(left_panel)

        right_panel = QWidget()
        right_column = QVBoxLayout(right_panel)
        right_column.setSpacing(14)
        right_column.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(right_panel, 1)

        runtime_card = self._build_runtime_card()
        summary_card = self._build_summary_card()
        action_card = self._build_action_card()

        left_column.addWidget(runtime_card)
        left_column.addWidget(summary_card)
        left_column.addWidget(action_card)
        left_column.addStretch(1)

        right_column.addWidget(self._build_log_card(), 1)

    def _build_header_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("HeroCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        left_layout = QVBoxLayout()
        left_layout.setSpacing(0)
        layout.addLayout(left_layout, 1)

        title = QLabel("拾米 - SD账号注册")
        title.setObjectName("Title")

        left_layout.addWidget(title)
        return card

    def _build_runtime_card(self) -> QFrame:
        card = self._create_card("运行参数")
        card.setMinimumHeight(245)
        layout = card.layout()

        self.total_count_spin = QSpinBox()
        self.total_count_spin.setRange(1, 99999)
        self.total_count_spin.setSuffix(" 个")
        self.total_count_spin.setFixedHeight(34)

        self.max_workers_spin = QSpinBox()
        self.max_workers_spin.setRange(MIN_WORKERS, MAX_WORKERS)
        self.max_workers_spin.setSuffix(" 线程")
        self.max_workers_spin.setFixedHeight(34)

        self.email_combo = QComboBox()
        for index, provider in enumerate(TEMP_EMAIL_PROVIDERS, start=1):
            self.email_combo.addItem(f"{index} - {provider['name']}", provider["name"])
        self.email_combo.addItem("7 - 随机", None)
        self.email_combo.setFixedHeight(34)

        form_grid = QGridLayout()
        form_grid.setHorizontalSpacing(8)
        form_grid.setVerticalSpacing(8)
        form_grid.setColumnStretch(0, 1)
        form_grid.setColumnStretch(1, 1)
        form_grid.setColumnStretch(2, 1)
        layout.addLayout(form_grid)

        form_grid.addWidget(self._create_input_card("注册数量", self.total_count_spin, control_width=126), 0, 0)
        form_grid.addWidget(self._create_input_card("并发线程数", self.max_workers_spin, control_width=118), 0, 1)
        form_grid.addWidget(self._create_input_card("邮箱站点", self.email_combo, control_width=138), 0, 2)

        self.show_browser_checkbox = QCheckBox("显示浏览器窗口")
        self.debug_checkbox = QCheckBox("调试模式（保存截图）")
        self.notion_checkbox = QCheckBox("启用 Notion 同步")

        options_layout = QVBoxLayout()
        options_layout.setSpacing(6)
        options_layout.setContentsMargins(0, 8, 0, 0)
        options_layout.addWidget(self.show_browser_checkbox)
        options_layout.addWidget(self.debug_checkbox)
        options_layout.addWidget(self.notion_checkbox)
        layout.addLayout(options_layout)
        return card

    def _build_action_card(self) -> QFrame:
        card = self._create_card("执行控制")
        card.setMinimumHeight(220)
        layout = card.layout()

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        layout.addLayout(button_row)

        self.start_button = QPushButton("开始执行")
        self.start_button.setObjectName("PrimaryButton")
        self.start_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.start_button.setFixedSize(116, 44)
        self.start_button.clicked.connect(self.start_run)

        self.stop_button = QPushButton("打断结束")
        self.stop_button.setObjectName("DangerButton")
        self.stop_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.stop_button.setMinimumWidth(132)
        self.stop_button.setMaximumWidth(156)
        self.stop_button.setFixedHeight(44)
        self.stop_button.setDisabled(True)
        self.stop_button.clicked.connect(self.stop_run)

        button_row.addWidget(self.start_button)
        button_row.addWidget(self.stop_button)
        button_row.addStretch(1)

        tool_layout = QVBoxLayout()
        tool_layout.setSpacing(8)
        tool_layout.setContentsMargins(0, 2, 0, 0)
        layout.addLayout(tool_layout)

        self.clear_log_button = QPushButton("清空日志")
        self.clear_log_button.setObjectName("SecondaryButton")
        self.clear_log_button.clicked.connect(self.clear_log)

        open_report_button = QPushButton("打开报告目录")
        open_report_button.setObjectName("SecondaryButton")
        open_report_button.clicked.connect(lambda: self._open_path(REPORT_DIR))

        open_backup_button = QPushButton("打开账号备份")
        open_backup_button.setObjectName("SecondaryButton")
        open_backup_button.clicked.connect(lambda: self._open_path(SUCCESS_DIR))

        open_log_button = QPushButton("打开日志文件")
        open_log_button.setObjectName("SecondaryButton")
        open_log_button.clicked.connect(lambda: self._open_path(LOG_FILE))

        tool_layout.addWidget(self.clear_log_button)
        tool_layout.addWidget(open_report_button)
        tool_layout.addWidget(open_backup_button)
        tool_layout.addWidget(open_log_button)
        return card

    def _build_summary_card(self) -> QFrame:
        card = self._create_card("运行概览")
        card.setMinimumHeight(260)
        layout = card.layout()

        stats_grid = QGridLayout()
        stats_grid.setHorizontalSpacing(8)
        stats_grid.setVerticalSpacing(8)
        layout.addLayout(stats_grid)

        self.total_stat = self._create_stat_card("计划任务", str(DEFAULT_TOTAL_COUNT))
        self.success_stat = self._create_stat_card("成功", "0")
        self.fail_stat = self._create_stat_card("失败", "0")
        self.elapsed_stat = self._create_stat_card("已耗时", "0秒")
        self.rate_stat = self._create_stat_card("成功率", "0.0%")
        self.available_rate_stat = self._create_stat_card("可用率", "0.0%")

        stats_grid.addWidget(self.total_stat["card"], 0, 0)
        stats_grid.addWidget(self.success_stat["card"], 0, 1)
        stats_grid.addWidget(self.fail_stat["card"], 0, 2)
        stats_grid.addWidget(self.elapsed_stat["card"], 1, 0)
        stats_grid.addWidget(self.rate_stat["card"], 1, 1)
        stats_grid.addWidget(self.available_rate_stat["card"], 1, 2)

        detail_layout = QVBoxLayout()
        detail_layout.setSpacing(8)
        detail_layout.setContentsMargins(0, 2, 0, 0)
        layout.addLayout(detail_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, DEFAULT_TOTAL_COUNT)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("0 / %m")

        self.progress_detail_value = self._create_note_label(
            f"已完成 0 / {DEFAULT_TOTAL_COUNT}，运行中 0，待开始 {DEFAULT_TOTAL_COUNT}"
        )
        self.run_status_value = QLabel("待命")
        self.run_status_value.setObjectName("ValueHero")
        self.report_path_value = self._create_note_label("尚未生成运行报告")
        self.last_result_value = self._create_note_label("最近一次运行结果将在这里显示")

        detail_layout.addLayout(self._create_value_block("当前进度", self.progress_bar))
        detail_layout.addWidget(self.progress_detail_value)
        detail_layout.addLayout(self._create_value_block("运行报告", self.report_path_value))
        detail_layout.addLayout(self._create_value_block("结果摘要", self.last_result_value))
        return card

    def _build_log_card(self) -> QFrame:
        card = self._create_card("实时日志")
        layout = card.layout()

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.document().setMaximumBlockCount(5000)
        layout.addWidget(self.log_view, 1)
        return card

    def _create_card(self, title_text: str, note_text: str | None = None) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        title = QLabel(title_text)
        title.setObjectName("SectionTitle")

        layout.addWidget(title)
        if note_text:
            note = QLabel(note_text)
            note.setObjectName("SectionNote")
            note.setWordWrap(True)
            layout.addWidget(note)
        return card

    def _create_stat_card(self, title_text: str, value_text: str) -> dict:
        card = QFrame()
        card.setObjectName("StatCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(1)
        card.setFixedHeight(44)

        title = QLabel(title_text)
        title.setObjectName("CaptionCard")
        title.setWordWrap(True)
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        value = QLabel(value_text)
        value.setObjectName("ValueCard")
        value.setWordWrap(True)
        value.setMinimumHeight(16)

        layout.addWidget(title)
        layout.addWidget(value)
        return {"card": card, "value": value}

    def _create_input_card(self, title_text: str, input_widget: QWidget, control_width: int | None = None) -> QFrame:
        card = QFrame()
        card.setObjectName("StatCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(5)
        card.setFixedHeight(74)

        title = QLabel(title_text)
        title.setObjectName("CaptionCard")
        title.setWordWrap(True)
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        layout.addWidget(title)

        control_row = QHBoxLayout()
        control_row.setContentsMargins(0, 0, 0, 0)
        control_row.setSpacing(0)
        if control_width is not None:
            input_widget.setFixedWidth(control_width)
        control_row.addWidget(input_widget, 0, Qt.AlignLeft | Qt.AlignVCenter)
        control_row.addStretch(1)
        layout.addLayout(control_row)
        return card

    def _create_field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("FieldLabel")
        label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        return label

    def _create_note_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SectionNote")
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        return label

    def _create_value_block(self, label_text: str, value_widget: QWidget) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setSpacing(4)
        layout.addWidget(self._create_field_label(label_text))
        layout.addWidget(value_widget)
        return layout

    def _apply_defaults(self) -> None:
        self.total_count_spin.setValue(DEFAULT_TOTAL_COUNT)
        self.max_workers_spin.setValue(DEFAULT_MAX_WORKERS)
        self.email_combo.setCurrentIndex(len(TEMP_EMAIL_PROVIDERS))
        self.show_browser_checkbox.setChecked(False)
        self.debug_checkbox.setChecked(False)
        self.notion_checkbox.setChecked(True)
        self.total_stat["value"].setText(str(DEFAULT_TOTAL_COUNT))
        self.success_stat["value"].setText("0")
        self.fail_stat["value"].setText("0")
        self.elapsed_stat["value"].setText("0秒")
        self.rate_stat["value"].setText("0.0%")
        self.available_rate_stat["value"].setText("0.0%")
        self.progress_bar.setRange(0, DEFAULT_TOTAL_COUNT)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat(f"0 / {DEFAULT_TOTAL_COUNT}")
        self.progress_detail_value.setText(f"已完成 0 / {DEFAULT_TOTAL_COUNT}，运行中 0，待开始 {DEFAULT_TOTAL_COUNT}")

    def _start_button_breathing(self, button: QPushButton) -> None:
        effect = button.graphicsEffect()
        if not isinstance(effect, QGraphicsDropShadowEffect):
            effect = QGraphicsDropShadowEffect(button)
            effect.setOffset(0, 0)
            button.setGraphicsEffect(effect)

        animation = self._button_animations.get(button)
        if animation is None:
            animation = QVariantAnimation(button)
            animation.setDuration(1400)
            animation.setStartValue(0.0)
            animation.setEndValue(1.0)
            animation.setEasingCurve(QEasingCurve.InOutSine)
            animation.setLoopCount(-1)
            animation.valueChanged.connect(
                lambda value, target_button=button: self._update_button_glow(target_button, float(value))
            )
            self._button_animations[button] = animation

        animation.start()

    def _stop_button_breathing(self, button: QPushButton) -> None:
        animation = self._button_animations.get(button)
        if animation is not None:
            animation.stop()

        effect = button.graphicsEffect()
        if isinstance(effect, QGraphicsDropShadowEffect):
            effect.setBlurRadius(0)
            effect.setColor(QColor(0, 0, 0, 0))

    def _update_button_glow(self, button: QPushButton, phase: float) -> None:
        effect = button.graphicsEffect()
        if not isinstance(effect, QGraphicsDropShadowEffect):
            return

        if button.objectName() == "DangerButton":
            base_color = QColor("#A85448")
            alpha = int(36 + phase * 54)
        else:
            base_color = QColor("#5D7052")
            alpha = int(42 + phase * 68)

        glow_color = QColor(base_color)
        glow_color.setAlpha(alpha)
        effect.setColor(glow_color)
        effect.setBlurRadius(10 + phase * 14)
        effect.setOffset(0, 0)

    def _set_button_busy_state(self, button: QPushButton, busy: bool) -> None:
        button.setProperty("busy", busy)
        button.style().unpolish(button)
        button.style().polish(button)
        if busy:
            self._start_button_breathing(button)
        else:
            self._stop_button_breathing(button)

    def _refresh_progress_view(self, progress: BatchProgress) -> None:
        self.total_stat["value"].setText(str(progress.planned_total))
        self.success_stat["value"].setText(str(progress.success_count))
        self.fail_stat["value"].setText(str(progress.fail_count))
        self.elapsed_stat["value"].setText(f"{progress.elapsed_seconds:.0f}秒")
        self.rate_stat["value"].setText(f"{progress.success_rate:.1f}%")
        self.available_rate_stat["value"].setText(f"{progress.available_rate:.1f}%")
        self.progress_bar.setRange(0, max(progress.planned_total, 1))
        self.progress_bar.setValue(progress.completed_count)
        self.progress_bar.setFormat(f"{progress.completed_count} / {progress.planned_total}")
        self.progress_detail_value.setText(
            f"已完成 {progress.completed_count} / {progress.planned_total}，"
            f"运行中 {progress.active_count}，待开始 {progress.pending_count}"
        )
        self.last_result_value.setText(
            f"运行中，已成功 {progress.success_count}，失败 {progress.fail_count}，已耗时 {progress.elapsed_seconds:.2f} 秒。"
        )
        if progress.stop_requested:
            self.last_result_value.setText(
                f"停止中，已完成 {progress.completed_count} / {progress.planned_total}，"
                f"成功 {progress.success_count}，失败 {progress.fail_count}。"
            )

    def _get_log_color(self, message: str) -> str:
        # ================================
        # 这里只负责实时日志配色
        # 目的: 让“注册成功”和“Notion 写入成功”在界面上更醒目
        # 边界: 仅影响 GUI 展示，不改变原始日志内容
        # ================================
        if "已写入 Notion" in message:
            return "#C18C5D"
        if "注册成功" in message:
            return "#5D7052"
        return "#3A392F"

    def append_log(self, message: str) -> None:
        safe_message = html.escape(message)
        color = self._get_log_color(message)
        self.log_view.append(f'<span style="color: {color};">{safe_message}</span>')
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

    def clear_log(self) -> None:
        self.log_view.clear()

    def _open_path(self, path) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _build_run_config(self) -> GuiRunConfig:
        selected_provider = self.email_combo.currentData()
        return GuiRunConfig(
            total_count=self.total_count_spin.value(),
            max_workers=self.max_workers_spin.value(),
            headless=not self.show_browser_checkbox.isChecked(),
            debug_mode=self.debug_checkbox.isChecked(),
            notion_enabled=self.notion_checkbox.isChecked(),
            specified_email=selected_provider,
            stop_event=self.stop_event,
        )

    def _ensure_notion_ready(self) -> bool:
        # ================================
        # Notion 预检在任务启动前执行
        # 目的: 连不通时给用户一个“关闭后继续”的明确开关
        # 边界: 这里只做连接检查，不做账号写入
        # ================================
        if not self.notion_checkbox.isChecked():
            return True

        notion_client = NotionClient()
        try:
            notion_client.get_database_metadata()
            return True
        except Exception as exc:
            reply = QMessageBox.warning(
                self,
                "Notion 无法连接",
                f"当前无法连接 Notion：\n{exc}\n\n是否关闭 Notion 后继续执行？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.Yes:
                self.notion_checkbox.setChecked(False)
                self.append_log("Notion 预检失败，已按用户选择关闭 Notion 后继续。")
                return True
            return False

    def _set_running_state(self, running: bool) -> None:
        self.start_button.setDisabled(running)
        self.stop_button.setDisabled(not running)
        self.total_count_spin.setDisabled(running)
        self.max_workers_spin.setDisabled(running)
        self.email_combo.setDisabled(running)
        self.show_browser_checkbox.setDisabled(running)
        self.debug_checkbox.setDisabled(running)
        self.notion_checkbox.setDisabled(running)
        self.run_status_value.setText("执行中" if running else "待命")

    def stop_run(self) -> None:
        if not self.worker_thread or not self.worker_thread.isRunning() or not self.stop_event:
            return

        if self.stop_event.is_set():
            return

        self.stop_event.set()
        self.stop_button.setText("等待收尾中")
        self.stop_button.setDisabled(True)
        self._set_button_busy_state(self.stop_button, True)
        self.append_log("已收到打断结束请求：不再启动新任务，正在等待进行中的线程收尾。")
        self.run_status_value.setText("停止中")

    def start_run(self) -> None:
        if self.worker_thread and self.worker_thread.isRunning():
            return

        if not self._ensure_notion_ready():
            return

        self.stop_event = Event()
        run_config = self._build_run_config()
        self.total_stat["value"].setText(str(run_config.total_count))
        self.success_stat["value"].setText("0")
        self.fail_stat["value"].setText("0")
        self.elapsed_stat["value"].setText("0秒")
        self.rate_stat["value"].setText("0.0%")
        self.available_rate_stat["value"].setText("0.0%")
        self.progress_bar.setRange(0, run_config.total_count)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat(f"0 / {run_config.total_count}")
        self.progress_detail_value.setText(f"已完成 0 / {run_config.total_count}，运行中 0，待开始 {run_config.total_count}")
        self.report_path_value.setText("运行中，报告生成后会显示在这里")
        self.last_result_value.setText("任务已启动，等待批量结果...")
        self.start_button.setText("正在执行")
        self._set_button_busy_state(self.start_button, True)
        self._set_button_busy_state(self.stop_button, False)
        self.stop_button.setText("打断结束")
        self.append_log("=" * 60)
        self.append_log("GUI 已启动批量注册任务")
        self.append_log(f"当前日志文件: {LOG_FILE}")
        self._set_running_state(True)

        self.worker_thread = QThread(self)
        self.worker = BatchWorker(run_config)
        self.worker.moveToThread(self.worker_thread)

        # ================================
        # GUI 与后台任务通过信号桥接
        # 目的: 实时展示日志并在完成后刷新统计卡片
        # 边界: 不直接从工作线程操作界面控件
        # ================================
        self.worker.log_line.connect(self.append_log)
        self.worker.progress.connect(self._handle_progress_update)
        self.worker.finished.connect(self._handle_run_finished)
        self.worker.failed.connect(self._handle_run_failed)
        self.worker.finished.connect(lambda _summary: self.worker_thread.quit())
        self.worker.failed.connect(lambda _message: self.worker_thread.quit())
        self.worker_thread.started.connect(self.worker.run)
        self.worker_thread.finished.connect(self._cleanup_worker)
        self.worker_thread.start()

    def _handle_run_finished(self, summary: BatchSummary) -> None:
        self.last_summary = summary
        self.success_stat["value"].setText(str(summary.success_count))
        self.fail_stat["value"].setText(str(summary.fail_count))
        self.elapsed_stat["value"].setText(f"{summary.duration_seconds:.0f}秒")
        self.rate_stat["value"].setText(f"{summary.success_rate:.1f}%")
        self.available_rate_stat["value"].setText(f"{summary.available_rate:.1f}%")
        self.progress_bar.setRange(0, max(summary.total_count, 1))
        self.progress_bar.setValue(summary.total_count)
        self.progress_bar.setFormat(f"{summary.total_count} / {summary.total_count}")
        self.progress_detail_value.setText(f"已完成 {summary.total_count} / {summary.total_count}，运行中 0，待开始 0")
        self.report_path_value.setText(
            f"JSON: {summary.json_report_path}\nCSV: {summary.csv_report_path}"
        )
        summary_text = (
            f"总计 {summary.total_count} 个任务，成功 {summary.success_count}，失败 {summary.fail_count}，耗时 {summary.duration_seconds:.2f} 秒。"
        )
        if summary.stop_requested:
            summary_text = (
                f"运行已打断，已完成 {summary.total_count} 个任务，成功 {summary.success_count}，失败 {summary.fail_count}，耗时 {summary.duration_seconds:.2f} 秒。"
            )
        self.last_result_value.setText(summary_text)
        self.append_log("GUI 执行完毕，统计卡片已刷新。")
        self._set_running_state(False)
        self.start_button.setText("开始执行")
        self._set_button_busy_state(self.start_button, False)
        self.run_status_value.setText("已打断" if summary.stop_requested else "已完成")
        self.stop_button.setText("打断结束")
        self._set_button_busy_state(self.stop_button, False)

    def _handle_progress_update(self, progress: BatchProgress) -> None:
        self._refresh_progress_view(progress)

    def _handle_run_failed(self, error_message: str) -> None:
        self.last_result_value.setText(f"启动失败：{error_message}")
        self.append_log(f"GUI 执行失败: {error_message}")
        QMessageBox.critical(self, "执行失败", error_message)
        self._set_running_state(False)
        self.start_button.setText("开始执行")
        self._set_button_busy_state(self.start_button, False)
        self.run_status_value.setText("执行失败")
        self.stop_button.setText("打断结束")
        self._set_button_busy_state(self.stop_button, False)

    def _cleanup_worker(self) -> None:
        if self.worker:
            self.worker.deleteLater()
        if self.worker_thread:
            self.worker_thread.deleteLater()
        self.worker = None
        self.worker_thread = None
        self.stop_event = None
        self.start_button.setText("开始执行")
        self._set_button_busy_state(self.start_button, False)
        self.stop_button.setText("打断结束")
        self._set_button_busy_state(self.stop_button, False)


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = SeedanceMainWindow()
    window.show()
    return app.exec()
