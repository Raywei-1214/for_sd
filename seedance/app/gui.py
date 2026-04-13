import logging
import sys
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass

from PySide6.QtCore import QObject, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from seedance.core.config import DEFAULT_MAX_WORKERS, DEFAULT_TOTAL_COUNT, LOG_FILE, MAX_WORKERS, MIN_WORKERS, REPORT_DIR, SUCCESS_DIR, TEMP_EMAIL_PROVIDERS
from seedance.core.logger import get_logger
from seedance.core.models import BatchSummary
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
  font-family: "Microsoft JhengHei UI", "Segoe UI", "Microsoft YaHei UI", "PingFang SC";
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

QLabel#Title {
  font-family: "DFKai-SB", "STKaiti", "Kaiti SC", "Microsoft JhengHei UI", "Microsoft YaHei UI", "PingFang SC";
  font-size: 32px;
  font-weight: 700;
  color: #2C2C24;
}

QLabel#SectionTitle {
  font-family: "DFKai-SB", "STKaiti", "Kaiti SC", "Microsoft JhengHei UI", "Microsoft YaHei UI", "PingFang SC";
  font-size: 19px;
  font-weight: 700;
  color: #2C2C24;
}

QLabel#SectionNote {
  font-size: 11px;
  color: #78786C;
}

QLabel#ValueHero {
  font-family: "Microsoft JhengHei UI", "Segoe UI", "Microsoft YaHei UI", "PingFang SC";
  font-size: 18px;
  font-weight: 700;
  color: #2C2C24;
}

QLabel#ValueCard {
  font-family: "Microsoft JhengHei UI", "Segoe UI", "Microsoft YaHei UI", "PingFang SC";
  font-size: 15px;
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
QPlainTextEdit {
  background: rgba(255, 255, 255, 0.75);
  color: #2C2C24;
  border: 1px solid #DED8CF;
  border-radius: 24px;
  padding: 10px 12px;
}

QSpinBox,
QComboBox {
  min-height: 42px;
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
QPlainTextEdit:focus {
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
  min-height: 44px;
  border-radius: 24px;
  padding: 0 18px;
  font-weight: 700;
}

QPushButton#PrimaryButton {
  background: #5D7052;
  color: #F3F4F1;
  border: 1px solid rgba(93, 112, 82, 0.68);
}

QPushButton#PrimaryButton:hover {
  background: #6A7D5F;
}

QPushButton#SecondaryButton {
  background: rgba(255, 255, 255, 0.18);
  color: #C18C5D;
  border: 2px solid rgba(193, 140, 93, 0.72);
}

QPushButton#SecondaryButton:hover {
  background: rgba(230, 220, 205, 0.48);
}

QPushButton:disabled {
  color: rgba(74, 74, 64, 0.46);
  background: rgba(240, 235, 229, 0.72);
  border: 1px solid rgba(222, 216, 207, 0.82);
}

QPlainTextEdit {
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

        self.setWindowTitle("拾米 - SD账号注册")
        self.resize(1360, 880)
        self.setMinimumSize(1200, 760)
        self.setStyleSheet(WINDOW_STYLESHEET)
        self.setFont(QFont("Microsoft YaHei UI", 9))

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

        left_panel = QWidget()
        left_panel.setFixedWidth(450)
        left_column = QVBoxLayout(left_panel)
        left_column.setSpacing(14)
        left_column.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(left_panel, 0)

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
        card = self._create_card("运行参数", "线程限制在 1-3 之间，先保留稳定性优先。")
        layout = card.layout()

        self.total_count_spin = QSpinBox()
        self.total_count_spin.setRange(1, 99999)
        self.total_count_spin.setSuffix(" 个")

        self.max_workers_spin = QSpinBox()
        self.max_workers_spin.setRange(MIN_WORKERS, MAX_WORKERS)
        self.max_workers_spin.setSuffix(" 线程")

        self.email_combo = QComboBox()
        for index, provider in enumerate(TEMP_EMAIL_PROVIDERS, start=1):
            self.email_combo.addItem(f"{index} - {provider['name']}", provider["name"])
        self.email_combo.addItem("7 - 随机", None)

        form_grid = QGridLayout()
        form_grid.setHorizontalSpacing(12)
        form_grid.setVerticalSpacing(10)
        form_grid.setColumnMinimumWidth(0, 84)
        form_grid.setColumnStretch(1, 1)
        layout.addLayout(form_grid)

        form_grid.addWidget(self._create_field_label("注册数量"), 0, 0)
        form_grid.addWidget(self.total_count_spin, 0, 1)
        form_grid.addWidget(self._create_field_label("并发线程"), 1, 0)
        form_grid.addWidget(self.max_workers_spin, 1, 1)
        form_grid.addWidget(self._create_field_label("邮箱站点"), 2, 0)
        form_grid.addWidget(self.email_combo, 2, 1)

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
        card = self._create_card("执行控制", "开始前会先做浏览器探测和 Notion 预检；运行过程中可打开报告与备份目录。")
        layout = card.layout()

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        layout.addLayout(button_row)

        self.start_button = QPushButton("开始执行")
        self.start_button.setObjectName("PrimaryButton")
        self.start_button.clicked.connect(self.start_run)

        self.clear_log_button = QPushButton("清空日志")
        self.clear_log_button.setObjectName("SecondaryButton")
        self.clear_log_button.clicked.connect(self.clear_log)

        button_row.addWidget(self.start_button)
        button_row.addWidget(self.clear_log_button)

        tool_layout = QVBoxLayout()
        tool_layout.setSpacing(8)
        tool_layout.setContentsMargins(0, 2, 0, 0)
        layout.addLayout(tool_layout)

        open_report_button = QPushButton("打开报告目录")
        open_report_button.setObjectName("SecondaryButton")
        open_report_button.clicked.connect(lambda: self._open_path(REPORT_DIR))

        open_backup_button = QPushButton("打开账号备份")
        open_backup_button.setObjectName("SecondaryButton")
        open_backup_button.clicked.connect(lambda: self._open_path(SUCCESS_DIR))

        open_log_button = QPushButton("打开日志文件")
        open_log_button.setObjectName("SecondaryButton")
        open_log_button.clicked.connect(lambda: self._open_path(LOG_FILE))

        tool_layout.addWidget(open_report_button)
        tool_layout.addWidget(open_backup_button)
        tool_layout.addWidget(open_log_button)
        return card

    def _build_summary_card(self) -> QFrame:
        card = self._create_card("运行概览", "执行结束后会刷新成功率、报告路径和最近一次状态。")
        layout = card.layout()

        stats_grid = QGridLayout()
        stats_grid.setHorizontalSpacing(8)
        stats_grid.setVerticalSpacing(8)
        layout.addLayout(stats_grid)

        self.total_stat = self._create_stat_card("计划任务", str(DEFAULT_TOTAL_COUNT))
        self.success_stat = self._create_stat_card("成功", "0")
        self.fail_stat = self._create_stat_card("失败", "0")
        self.rate_stat = self._create_stat_card("成功率", "0.0%")

        stats_grid.addWidget(self.total_stat["card"], 0, 0)
        stats_grid.addWidget(self.success_stat["card"], 0, 1)
        stats_grid.addWidget(self.fail_stat["card"], 1, 0)
        stats_grid.addWidget(self.rate_stat["card"], 1, 1)

        detail_layout = QVBoxLayout()
        detail_layout.setSpacing(8)
        detail_layout.setContentsMargins(0, 2, 0, 0)
        layout.addLayout(detail_layout)

        self.run_status_value = QLabel("待命")
        self.run_status_value.setObjectName("ValueHero")
        self.report_path_value = self._create_note_label("尚未生成运行报告")
        self.last_result_value = self._create_note_label("最近一次运行结果将在这里显示")

        detail_layout.addLayout(self._create_value_block("当前状态", self.run_status_value))
        detail_layout.addLayout(self._create_value_block("运行报告", self.report_path_value))
        detail_layout.addLayout(self._create_value_block("结果摘要", self.last_result_value))
        return card

    def _build_log_card(self) -> QFrame:
        card = self._create_card("实时日志")
        layout = card.layout()

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(5000)
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
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(3)
        card.setMinimumHeight(72)

        title = QLabel(title_text)
        title.setObjectName("CaptionCard")
        title.setWordWrap(True)
        title.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        value = QLabel(value_text)
        value.setObjectName("ValueCard")
        value.setWordWrap(True)
        value.setMinimumHeight(24)

        layout.addWidget(title)
        layout.addWidget(value)
        return {"card": card, "value": value}

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

    def append_log(self, message: str) -> None:
        self.log_view.appendPlainText(message)
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
        self.total_count_spin.setDisabled(running)
        self.max_workers_spin.setDisabled(running)
        self.email_combo.setDisabled(running)
        self.show_browser_checkbox.setDisabled(running)
        self.debug_checkbox.setDisabled(running)
        self.notion_checkbox.setDisabled(running)
        self.run_status_value.setText("执行中" if running else "待命")

    def start_run(self) -> None:
        if self.worker_thread and self.worker_thread.isRunning():
            return

        if not self._ensure_notion_ready():
            return

        run_config = self._build_run_config()
        self.total_stat["value"].setText(str(run_config.total_count))
        self.success_stat["value"].setText("0")
        self.fail_stat["value"].setText("0")
        self.rate_stat["value"].setText("0.0%")
        self.report_path_value.setText("运行中，报告生成后会显示在这里")
        self.last_result_value.setText("任务已启动，等待批量结果...")
        self.append_log("=" * 60)
        self.append_log("GUI 已启动批量注册任务")
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
        self.rate_stat["value"].setText(f"{summary.success_rate:.1f}%")
        self.report_path_value.setText(
            f"JSON: {summary.json_report_path}\nCSV: {summary.csv_report_path}"
        )
        self.last_result_value.setText(
            f"总计 {summary.total_count} 个任务，成功 {summary.success_count}，失败 {summary.fail_count}，耗时 {summary.duration_seconds:.2f} 秒。"
        )
        self.append_log("GUI 执行完毕，统计卡片已刷新。")
        self._set_running_state(False)
        self.run_status_value.setText("已完成")

    def _handle_run_failed(self, error_message: str) -> None:
        self.last_result_value.setText(f"启动失败：{error_message}")
        self.append_log(f"GUI 执行失败: {error_message}")
        QMessageBox.critical(self, "执行失败", error_message)
        self._set_running_state(False)
        self.run_status_value.setText("执行失败")

    def _cleanup_worker(self) -> None:
        if self.worker:
            self.worker.deleteLater()
        if self.worker_thread:
            self.worker_thread.deleteLater()
        self.worker = None
        self.worker_thread = None


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = SeedanceMainWindow()
    window.show()
    return app.exec()
