import os
import sys
import time
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                           QLabel, QLineEdit, QPushButton, QFileDialog, QProgressBar, 
                           QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox, 
                           QMessageBox, QGroupBox, QFormLayout, QTextEdit, QSplitter,
                           QTabWidget, QDialog, QSpinBox, QDoubleSpinBox, QScrollArea)
from PyQt5.QtCore import Qt, pyqtSignal, QThread
from PyQt5.QtGui import QDragEnterEvent, QDropEvent, QFont, QIntValidator, QIcon

from midi_processor import MidiProcessor

# 导入Excel导出相关库
try:
    import pandas as pd
    EXCEL_EXPORT_AVAILABLE = True
except ImportError:
    EXCEL_EXPORT_AVAILABLE = False

class WorkerThread(QThread):
    """处理MIDI文件的工作线程"""
    update_progress = pyqtSignal(int, int)  # 当前进度，总数
    update_result = pyqtSignal(dict)        # 处理结果
    update_log = pyqtSignal(str)            # 日志信息
    finished = pyqtSignal()                 # 处理完成信号
    
    def __init__(self, processor, files=None, input_dir=None, output_dir=None, 
                target_bpm=120.0, remove_cc=True, set_velocity=True, velocity_percent=80,
                skip_matched=True, keep_original_tempo=False, check_overlap=False, fix_overlap=False,
                multitrack_overlap=False):
        super().__init__()
        self.processor = processor
        self.files = files or []
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.target_bpm = target_bpm
        self.remove_cc = remove_cc
        self.set_velocity = set_velocity
        self.velocity_percent = velocity_percent
        self.skip_matched = skip_matched
        self.keep_original_tempo = keep_original_tempo
        self.check_overlap = check_overlap
        self.fix_overlap = fix_overlap
        self.multitrack_overlap = multitrack_overlap
        
        # 重定向标准输出
        self.old_stdout = sys.stdout
        sys.stdout = self
        
    def write(self, text):
        """处理标准输出的重定向"""
        if text and text.strip():
            self.update_log.emit(text)
    
    def flush(self):
        """标准输出刷新"""
        pass
        
    def run(self):
        try:
            # 处理单个文件列表
            if self.files:
                total = len(self.files)
                for i, file_path in enumerate(self.files):
                    # 记录日志
                    self.update_log.emit(f"正在处理: {os.path.basename(file_path)}")
                    
                    # 确保输出目录存在
                    if not os.path.exists(self.output_dir):
                        os.makedirs(self.output_dir, exist_ok=True)
                    
                    # 处理文件
                    result = self.processor.process_file(
                        file_path, 
                        self.output_dir, 
                        self.target_bpm, 
                        self.remove_cc, 
                        self.set_velocity,
                        self.velocity_percent,
                        self.skip_matched,
                        self.keep_original_tempo,
                        self.check_overlap,
                        self.fix_overlap,
                        self.multitrack_overlap
                    )
                    
                    # 发送进度和结果信号
                    self.update_progress.emit(i + 1, total)
                    self.update_result.emit(result)
                    
                    # 记录处理结果
                    self.update_log.emit(f"处理完成: {result['filename']} - 状态: {result['status']}")
            
            # 处理整个目录
            elif self.input_dir:
                self.update_log.emit(f"扫描目录: {self.input_dir}")
                results = self.processor.process_directory(
                    self.input_dir,
                    self.output_dir,
                    self.target_bpm,
                    self.remove_cc,
                    self.set_velocity,
                    self.velocity_percent,
                    self.skip_matched,
                    self.keep_original_tempo,
                    self.check_overlap,
                    self.fix_overlap,
                    self.multitrack_overlap
                )
                
                # 发送进度和结果信号
                for i, result in enumerate(results):
                    self.update_progress.emit(i + 1, len(results))
                    self.update_result.emit(result)
        finally:
            # 恢复标准输出
            sys.stdout = self.old_stdout
            
            # 发送完成信号
            self.finished.emit()


class DragDropLineEdit(QLineEdit):
    """支持拖放功能的LineEdit"""
    paths_dropped = pyqtSignal(list)  # 修改为发送列表信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setReadOnly(True)
    
    def dragEnterEvent(self, event: QDragEnterEvent):
        # 接受任意数量的文件/文件夹拖放
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
    
    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            paths = [url.toLocalFile() for url in urls]
            
            # 显示拖入的文件数量或目录
            if len(paths) == 1:
                file_path = paths[0]
                if os.path.isdir(file_path):
                    self.setText(file_path)  # 显示目录路径
                else:
                    self.setText(f"已选择: {os.path.basename(file_path)}")
            else:
                self.setText(f"已选择 {len(paths)} 个文件")
                
            # 发送所有路径
            self.paths_dropped.emit(paths)


class MainWindow(QMainWindow):
    """主窗口"""
    def __init__(self):
        super().__init__()
        
        # 设置基本窗口属性
        self.setWindowTitle("MIDI处理工具")
        self.setMinimumSize(1000, 700)
        
        # 设置窗口图标
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icon.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        # 初始化处理器
        self.processor = MidiProcessor()
        
        # 初始化界面
        self.init_ui()
        
        # 文件和目录路径
        self.midi_files = []
        self.input_directory = ""
        self.output_directory = ""
        
        # 存储处理结果
        self.processed_results = []
    
    def init_ui(self):
        # 创建中心部件和主布局
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        
        # 创建文件选择区域 (不使用GroupBox)
        file_widget = QWidget()
        file_layout = QFormLayout(file_widget)
        file_layout.setContentsMargins(10, 10, 10, 10)
        
        # 创建目录选择区域
        dir_layout = QHBoxLayout()
        self.input_dir_edit = DragDropLineEdit()
        self.input_dir_edit.setPlaceholderText("输入目录 (拖放MIDI文件或文件夹到这里)")
        self.input_dir_edit.paths_dropped.connect(self.set_input_directory)
        browse_input_btn = QPushButton("浏览...")
        browse_input_btn.clicked.connect(self.browse_input_directory)
        dir_layout.addWidget(self.input_dir_edit)
        dir_layout.addWidget(browse_input_btn)
        file_layout.addRow("MIDI文件目录:", dir_layout)
        
        # 创建输出目录选择区域
        output_dir_layout = QHBoxLayout()
        self.output_dir_edit = DragDropLineEdit()
        self.output_dir_edit.setPlaceholderText("输出目录 (拖放目标文件夹到这里)")
        self.output_dir_edit.paths_dropped.connect(self.set_output_directory)
        browse_output_btn = QPushButton("浏览...")
        browse_output_btn.clicked.connect(self.browse_output_directory)
        output_dir_layout.addWidget(self.output_dir_edit)
        output_dir_layout.addWidget(browse_output_btn)
        file_layout.addRow("输出目录:", output_dir_layout)
        
        # 优化选项部分的布局 - 使用网格布局使其更紧凑
        options_widget = QWidget()
        options_layout = QHBoxLayout(options_widget)
        options_layout.setContentsMargins(0, 0, 0, 0)
        
        # 优化选项部分的布局 - 重新设计布局
        options_widget = QWidget()
        options_layout = QVBoxLayout(options_widget)
        options_layout.setContentsMargins(0, 0, 0, 0)
        
        # 第一行：BPM和力度设置
        first_row_layout = QHBoxLayout()
        
        # BPM设置
        bpm_layout = QHBoxLayout()
        self.target_bpm_label = QLabel("目标BPM:")
        self.target_bpm_spinbox = QDoubleSpinBox()
        self.target_bpm_spinbox.setRange(1.0, 999.99)
        self.target_bpm_spinbox.setDecimals(2)
        self.target_bpm_spinbox.setValue(120.0)
        self.target_bpm_spinbox.setSuffix(" BPM")
        bpm_layout.addWidget(self.target_bpm_label)
        bpm_layout.addWidget(self.target_bpm_spinbox)
        first_row_layout.addLayout(bpm_layout)
        
        # 添加一些间距
        first_row_layout.addSpacing(20)
        
        # MIDI速度转换复选框 - 放在BPM后面
        self.keep_original_tempo_checkbox = QCheckBox("MIDI速度转换")
        self.keep_original_tempo_checkbox.setChecked(True)
        self.keep_original_tempo_checkbox.setToolTip("勾选时根据设定的目标BPM处理MIDI文件，取消勾选时保持原始速度")
        first_row_layout.addWidget(self.keep_original_tempo_checkbox)
        
        # 添加一些间距
        first_row_layout.addSpacing(20)
        
        # 力度设置
        velocity_layout = QHBoxLayout()
        self.velocity_label = QLabel("力度百分比:")
        self.velocity_spinbox = QSpinBox()
        self.velocity_spinbox.setRange(1, 100)
        self.velocity_spinbox.setValue(80)
        self.velocity_spinbox.setToolTip("设置音符力度的百分比 (1-100)")
        velocity_layout.addWidget(self.velocity_label)
        velocity_layout.addWidget(self.velocity_spinbox)
        first_row_layout.addLayout(velocity_layout)
        
        # 添加一些间距
        first_row_layout.addSpacing(20)
        
        # 统一力度复选框 - 放在力度百分比后面
        self.set_velocity_checkbox = QCheckBox("统一音符力度")
        self.set_velocity_checkbox.setChecked(True)
        self.set_velocity_checkbox.setToolTip("统一所有音符的力度值")
        first_row_layout.addWidget(self.set_velocity_checkbox)
        
        # 添加弹性空间
        first_row_layout.addStretch()
        
        options_layout.addLayout(first_row_layout)
        
        # 第二行：其他选项横向排列
        second_row_layout = QHBoxLayout()
        
        # 去除控制消息复选框
        self.remove_cc_checkbox = QCheckBox("移除控制消息")
        self.remove_cc_checkbox.setChecked(True)
        self.remove_cc_checkbox.setToolTip("移除所有CC控制消息（如延音踏板、弯音等）。取消勾选时，控制信息的时间位置会随速度变化同步调整")
        second_row_layout.addWidget(self.remove_cc_checkbox)
        
        # 添加一些间距
        second_row_layout.addSpacing(20)
        
        # 跳过匹配文件复选框
        self.skip_matched_checkbox = QCheckBox("跳过匹配文件")
        self.skip_matched_checkbox.setChecked(True)
        self.skip_matched_checkbox.setToolTip("如果MIDI文件已经符合设置条件则跳过处理")
        second_row_layout.addWidget(self.skip_matched_checkbox)
        
        # 添加一些间距
        second_row_layout.addSpacing(20)
        
        # MIDI重叠检测复选框
        self.check_overlap_checkbox = QCheckBox("检测音符重叠")
        self.check_overlap_checkbox.setChecked(False)
        self.check_overlap_checkbox.setToolTip("检测MIDI文件中的音符重叠情况")
        second_row_layout.addWidget(self.check_overlap_checkbox)
        
        # 添加一些间距
        second_row_layout.addSpacing(20)
        
        # 重叠音符处理复选框
        self.fix_overlap_checkbox = QCheckBox("重叠音符处理")
        self.fix_overlap_checkbox.setChecked(False)
        self.fix_overlap_checkbox.setEnabled(False)  # 默认禁用
        self.fix_overlap_checkbox.setToolTip("处理检测到的重叠音符：前后重叠时裁剪前一个音符，完全重叠时保留更早的音符")
        second_row_layout.addWidget(self.fix_overlap_checkbox)
        
        # 添加一些间距
        second_row_layout.addSpacing(20)
        
        # 多轨MIDI重叠处理复选框
        self.multitrack_overlap_checkbox = QCheckBox("跨轨道重叠处理")
        self.multitrack_overlap_checkbox.setChecked(False)
        self.multitrack_overlap_checkbox.setEnabled(False)  # 默认禁用
        self.multitrack_overlap_checkbox.setToolTip("处理跨轨道的音符重叠。默认情况下，多轨MIDI仅处理各轨道内部的重叠，跨轨道重叠被视为正常编曲（如和弦）。启用此选项将处理所有重叠。")
        second_row_layout.addWidget(self.multitrack_overlap_checkbox)
        
        # 添加弹性空间
        second_row_layout.addStretch()
        
        options_layout.addLayout(second_row_layout)
        
        file_layout.addRow("选项:", options_widget)
        
        main_layout.addWidget(file_widget)
        
        # 添加进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)
        
        # 操作按钮布局
        button_layout = QHBoxLayout()
        
        # 添加开始按钮
        self.start_button = QPushButton("开始处理")
        self.start_button.clicked.connect(self.start_processing)
        button_layout.addWidget(self.start_button)
        
        # 添加导出按钮
        self.export_button = QPushButton("导出结果")
        self.export_button.clicked.connect(self.export_results)
        self.export_button.setEnabled(False)  # 初始状态禁用
        button_layout.addWidget(self.export_button)
        
        main_layout.addLayout(button_layout)
        
        # 创建选项卡部件，包含结果表格和日志
        self.tabs = QTabWidget()
        
        # 结果表格选项卡
        results_widget = QWidget()
        results_layout = QVBoxLayout(results_widget)
        
        # 创建表格显示处理结果
        self.result_table = QTableWidget(0, 8)  # 修改为8列，添加重叠音符处理列
        self.result_table.setHorizontalHeaderLabels([
            "文件名", "原始速度", "目标速度", "音符力度", "删除控制信息", "重叠检测", "重叠处理", "状态"
        ])
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.result_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)  # 文件名列自适应
        self.result_table.setAlternatingRowColors(True)
        results_layout.addWidget(self.result_table)
        
        self.tabs.addTab(results_widget, "处理结果")
        
        # 日志选项卡
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        
        # 添加日志显示框
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setPlaceholderText("处理日志将显示在这里...")
        font = QFont("Consolas", 9)
        self.log_edit.setFont(font)
        self.log_edit.setStyleSheet("background-color: #f0f0f0;")
        log_layout.addWidget(self.log_edit)
        
        self.tabs.addTab(log_widget, "运行日志")
        
        main_layout.addWidget(self.tabs)
        
        # 设置中心部件
        self.setCentralWidget(central_widget)
        
        # 连接复选框信号
        self.keep_original_tempo_checkbox.stateChanged.connect(self.on_keep_original_tempo_changed)
        self.set_velocity_checkbox.stateChanged.connect(self.on_set_velocity_changed)
        self.check_overlap_checkbox.stateChanged.connect(self.on_check_overlap_changed)
        self.fix_overlap_checkbox.stateChanged.connect(self.on_fix_overlap_changed)
        self.multitrack_overlap_checkbox.stateChanged.connect(self.on_multitrack_overlap_changed)
        
        # 初始化界面状态
        self.update_ui_state()
    
    def set_input_directory(self, paths):
        # 先检查是否包含目录
        directories = [p for p in paths if os.path.isdir(p)]
        
        if directories:
            # 如果有目录，使用第一个目录
            self.input_directory = directories[0]
            self.midi_files = []
            self.input_dir_edit.setText(self.input_directory)
        else:
            # 收集所有MIDI文件
            midi_files = []
            for path in paths:
                if os.path.isfile(path) and path.lower().endswith(('.mid', '.midi')):
                    midi_files.append(path)
            
            if not midi_files:
                QMessageBox.warning(self, "错误", "未找到有效的MIDI文件")
                self.input_dir_edit.clear()
                return
                
            # 设置文件列表和目录
            self.midi_files = midi_files
            
            # 使用第一个文件的目录作为输入目录
            first_dir = os.path.dirname(midi_files[0])
            self.input_directory = first_dir
            
            # 更新显示
            if len(midi_files) == 1:
                self.input_dir_edit.setText(f"已选择: {os.path.basename(midi_files[0])}")
            else:
                self.input_dir_edit.setText(f"已选择 {len(midi_files)} 个MIDI文件")
    
    def set_output_directory(self, paths):
        if paths and os.path.isdir(paths[0]):
            self.output_directory = paths[0]
            self.output_dir_edit.setText(self.output_directory)
        else:
            QMessageBox.warning(self, "错误", "请选择有效的输出目录")
            self.output_dir_edit.clear()
    
    def browse_input_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "选择MIDI文件目录")
        if directory:
            self.input_directory = directory
            self.input_dir_edit.setText(directory)
            self.midi_files = []  # 清空文件列表，使用目录模式
    
    def browse_output_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if directory:
            self.output_directory = directory
            self.output_dir_edit.setText(directory)
    
    def start_processing(self):
        """开始处理所有文件"""
        if not self.midi_files and not self.input_directory:
            QMessageBox.warning(self, "警告", "请先添加MIDI文件或选择目录")
            return

        if not self.output_directory:
            QMessageBox.warning(self, "警告", "请先选择输出目录")
            return

        # 获取处理参数
        target_bpm = self.target_bpm_spinbox.value()
        remove_cc = self.remove_cc_checkbox.isChecked()
        set_velocity = self.set_velocity_checkbox.isChecked()
        velocity_percent = self.velocity_spinbox.value()
        skip_matched = self.skip_matched_checkbox.isChecked()
        keep_original_tempo = self.keep_original_tempo_checkbox.isChecked()
        check_overlap = self.check_overlap_checkbox.isChecked()
        fix_overlap = self.fix_overlap_checkbox.isChecked()
        multitrack_overlap = self.multitrack_overlap_checkbox.isChecked()

        # 切换到结果选项卡
        self.tabs.setCurrentIndex(0)
        
        # 清空结果表格和日志
        self.result_table.setRowCount(0)
        self.log_edit.clear()
        self.log_edit.append("===== 开始处理MIDI文件 =====")
        
        # 存储处理结果
        self.processed_results = []
        
        # 创建并启动工作线程
        self.worker = WorkerThread(
            self.processor,
            files=self.midi_files,
            input_dir=self.input_directory,
            output_dir=self.output_directory,
            target_bpm=target_bpm,
            remove_cc=remove_cc,
            set_velocity=set_velocity,
            velocity_percent=velocity_percent,
            skip_matched=skip_matched,
            keep_original_tempo=keep_original_tempo,
            check_overlap=check_overlap,
            fix_overlap=fix_overlap,
            multitrack_overlap=multitrack_overlap
        )
        
        # 连接信号
        self.worker.update_progress.connect(self.update_progress)
        self.worker.update_result.connect(self.add_result)
        self.worker.update_log.connect(self.add_log)
        self.worker.finished.connect(self.processing_finished)
        
        # 禁用界面元素
        self.start_button.setEnabled(False)
        self.start_button.setText("处理中...")
        self.export_button.setEnabled(False)
        
        # 启动线程
        self.worker.start()
    
    def update_progress(self, current, total):
        """更新进度条"""
        percentage = int(current / total * 100) if total > 0 else 0
        self.progress_bar.setValue(percentage)
    
    def add_result(self, result):
        """添加处理结果到表格"""
        # 存储完整结果
        self.processed_results.append(result)
        
        row = self.result_table.rowCount()
        self.result_table.insertRow(row)
        
        # 填充表格数据
        self.result_table.setItem(row, 0, QTableWidgetItem(result["filename"]))
        
        # 显示原始速度 - 优化多速度显示格式
        if "tempo_changes" in result and result["tempo_changes"]:
            tempos = []
            for tempo_info in result["tempo_changes"]:
                bpm = tempo_info["bpm"]
                if isinstance(bpm, (int, float)):
                    tempos.append(f"{bpm:.1f}")
            
            if tempos:
                # 检查是否为变速MIDI
                is_multi_tempo = result.get("is_multi_tempo", False)
                prefix = "[变速] " if is_multi_tempo else ""
                
                if len(tempos) > 1:
                    # 如果有多个速度，使用格式: "120.0→140.0→90.5"
                    tempo_text = prefix + " → ".join(tempos) + " BPM"
                else:
                    tempo_text = prefix + tempos[0] + " BPM"
            else:
                tempo_text = str(result["original_bpm"]) + " BPM"
        else:
            tempo_text = str(result["original_bpm"]) + " BPM"
            
        self.result_table.setItem(row, 1, QTableWidgetItem(tempo_text))
        
        # 目标速度
        target_bpm_str = f"{result['target_bpm']:.2f}" if isinstance(result['target_bpm'], (int, float)) else str(result['target_bpm'])
        self.result_table.setItem(row, 2, QTableWidgetItem(target_bpm_str + " BPM"))
        
        # 音符力度状态
        if "velocity_status" in result:
            velocity_status = result["velocity_status"]
        else:
            velocity_status = "已处理" if result["velocity_modified"] else "未处理"
        self.result_table.setItem(row, 3, QTableWidgetItem(velocity_status))
        
        # CC状态
        if "cc_status" in result:
            cc_status = result["cc_status"]
        else:
            cc_status = "已处理" if result["cc_removed"] else "未处理"
        self.result_table.setItem(row, 4, QTableWidgetItem(cc_status))
        
        # 重叠检测状态
        if "overlap_status" in result:
            overlap_status = result["overlap_status"]
            # 如果有重叠详细信息，添加到显示中
            if "overlap_details" in result and result["overlap_details"]:
                overlap_display = f"{overlap_status}\n{result['overlap_details']}"
            else:
                overlap_display = overlap_status
        else:
            overlap_display = "未检测"
        
        overlap_item = QTableWidgetItem(overlap_display)
        # 检查是否有重叠（包括多轨重叠格式）
        if ("存在重叠" in overlap_status or "轨道内重叠" in overlap_status or 
            "多轨全局重叠" in overlap_status or "跨轨道重叠" in overlap_status):
            overlap_item.setForeground(Qt.red)
        self.result_table.setItem(row, 5, overlap_item)
        
        # 重叠音符处理状态
        if "fix_overlap_status" in result:
            fix_overlap_status = result["fix_overlap_status"]
        else:
            fix_overlap_status = "未处理"
        
        fix_overlap_item = QTableWidgetItem(fix_overlap_status)
        if "已处理" in fix_overlap_status:
            fix_overlap_item.setForeground(Qt.blue)
        self.result_table.setItem(row, 6, fix_overlap_item)
        
        # 处理状态
        status_item = QTableWidgetItem(result["status"])
        self.result_table.setItem(row, 7, status_item)
        
        # 设置状态单元格的颜色
        if "错误" in result["status"]:
            status_item.setBackground(Qt.red)
            status_item.setForeground(Qt.white)
        elif result["status"] == "成功":
            status_item.setBackground(Qt.green)
            status_item.setForeground(Qt.black)
        # 对于"无需处理"状态，不设置颜色
        
        # 滚动到最新的行
        self.result_table.scrollToBottom()
    
    def add_log(self, text):
        """添加日志信息"""
        self.log_edit.append(text)
        # 滚动到底部
        self.log_edit.verticalScrollBar().setValue(self.log_edit.verticalScrollBar().maximum())
    
    def processing_finished(self):
        """处理完成后的操作"""
        self.start_button.setEnabled(True)
        self.start_button.setText("开始处理")
        
        # 启用导出按钮(如果有处理结果)
        if self.processed_results:
            self.export_button.setEnabled(True)
        
        # 添加完成日志
        self.log_edit.append("===== 处理完成 =====")
        
        # 显示完成消息
        QMessageBox.information(self, "完成", "MIDI文件处理完成")
        
        # 打开输出目录
        if os.path.exists(self.output_directory):
            try:
                os.startfile(self.output_directory)  # 仅适用于Windows
            except:
                pass
    
    def export_results(self):
        """导出处理结果到Excel文件"""
        if not self.processed_results:
            QMessageBox.warning(self, "错误", "没有可导出的处理结果")
            return
            
        if not EXCEL_EXPORT_AVAILABLE:
            QMessageBox.warning(self, "错误", "导出Excel功能需要安装pandas库")
            return
            
        try:
            # 创建一个默认的文件名
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            default_file = os.path.join(
                self.output_directory, 
                f"MIDI处理结果_{timestamp}.xlsx"
            )
            
            # 让用户选择保存位置
            export_path, _ = QFileDialog.getSaveFileName(
                self, "导出结果", 
                default_file,
                "Excel Files (*.xlsx);;All Files (*)"
            )
            
            if not export_path:
                return
                
            # 准备数据
            data = []
            for result in self.processed_results:
                # 获取原始速度字符串
                if "tempo_changes" in result and result["tempo_changes"]:
                    tempos = []
                    for tempo_info in result["tempo_changes"]:
                        bpm = tempo_info["bpm"]
                        if isinstance(bpm, (int, float)):
                            tempos.append(f"{bpm:.1f}")
                    
                    if tempos:
                        # 检查是否为变速MIDI
                        is_multi_tempo = result.get("is_multi_tempo", False)
                        prefix = "[变速] " if is_multi_tempo else ""
                        
                        if len(tempos) > 1:
                            tempo_text = prefix + " → ".join(tempos) + " BPM"
                        else:
                            tempo_text = prefix + tempos[0] + " BPM"
                    else:
                        tempo_text = str(result["original_bpm"]) + " BPM"
                else:
                    tempo_text = str(result["original_bpm"]) + " BPM"
                
                # 获取音符力度状态
                if "velocity_status" in result:
                    velocity_status = result["velocity_status"]
                else:
                    velocity_status = "已处理" if result["velocity_modified"] else "未处理"
                
                # 获取CC状态
                if "cc_status" in result:
                    cc_status = result["cc_status"]
                else:
                    cc_status = "已处理" if result["cc_removed"] else "未处理"
                
                # 获取重叠检测状态
                if "overlap_status" in result:
                    overlap_status = result["overlap_status"]
                    # 如果有重叠详细信息，添加到导出中
                    if "overlap_details" in result and result["overlap_details"]:
                        # 使用分号分隔，避免Excel中的换行符问题
                        overlap_export = f"{overlap_status}; {result['overlap_details']}"
                    else:
                        overlap_export = overlap_status
                else:
                    overlap_export = "未检测"
                
                # 获取重叠音符处理状态
                if "fix_overlap_status" in result:
                    fix_overlap_export = result["fix_overlap_status"]
                else:
                    fix_overlap_export = "未处理"
                
                data.append({
                    "文件名": result["filename"],
                    "原始速度": tempo_text,
                    "目标速度": f"{result['target_bpm']:.2f} BPM" if isinstance(result['target_bpm'], (int, float)) else str(result['target_bpm']) + " BPM",
                    "音符力度": velocity_status,
                    "删除控制信息": cc_status,
                    "重叠检测": overlap_export,
                    "重叠处理": fix_overlap_export,
                    "状态": result["status"],
                    "文件路径": result["path"],
                    "音符数量": result["note_count"]
                })
            
            # 创建DataFrame并导出
            df = pd.DataFrame(data)
            df.to_excel(export_path, index=False)
            
            QMessageBox.information(self, "导出成功", f"处理结果已成功导出到:\n{export_path}")
            
            # 尝试打开导出的文件
            try:
                os.startfile(export_path)
            except:
                pass
                
        except Exception as e:
            QMessageBox.warning(self, "导出错误", f"导出Excel时出错: {str(e)}")
    
    def on_keep_original_tempo_changed(self, state):
        """当保持原始速度复选框状态改变时的响应"""
        self.update_ui_state()
    
    def on_set_velocity_changed(self, state):
        """当统一音符力度复选框状态改变时的响应"""
        self.update_ui_state()
    
    def on_check_overlap_changed(self, state):
        """当检测音符重叠复选框状态改变时的响应"""
        self.update_ui_state()
    
    def on_fix_overlap_changed(self, state):
        """当重叠音符处理复选框状态改变时的响应"""
        self.update_ui_state()
    
    def on_multitrack_overlap_changed(self, state):
        """当多轨道重叠处理复选框状态改变时的响应"""
        # 多轨道重叠处理不需要特殊处理，只是传递参数
        pass
    
    def update_ui_state(self):
        """更新界面状态，根据复选框状态启用/禁用相关控件"""
        # 根据MIDI速度转换复选框状态控制目标BPM
        # 勾选时启用速度转换（目标BPM可用），取消勾选时保持原始速度（目标BPM禁用）
        enable_speed_conversion = self.keep_original_tempo_checkbox.isChecked()
        self.target_bpm_spinbox.setEnabled(enable_speed_conversion)
        self.target_bpm_label.setEnabled(enable_speed_conversion)
        
        # 根据统一音符力度复选框状态控制力度百分比
        set_velocity = self.set_velocity_checkbox.isChecked()
        self.velocity_spinbox.setEnabled(set_velocity)
        self.velocity_label.setEnabled(set_velocity)
        
        # 根据检测音符重叠复选框状态控制重叠音符处理选项
        check_overlap = self.check_overlap_checkbox.isChecked()
        self.fix_overlap_checkbox.setEnabled(check_overlap)
        
        # 根据重叠音符处理复选框状态控制多轨道重叠处理选项
        fix_overlap = self.fix_overlap_checkbox.isChecked()
        self.multitrack_overlap_checkbox.setEnabled(check_overlap and fix_overlap)
        
        # 设置禁用状态的样式
        disabled_style = "color: #888888; background-color: #f0f0f0;"
        enabled_style = ""
        
        # 更新目标BPM的样式
        if not enable_speed_conversion:
            self.target_bpm_spinbox.setStyleSheet(disabled_style)
            self.target_bpm_label.setStyleSheet("color: #888888;")
        else:
            self.target_bpm_spinbox.setStyleSheet(enabled_style)
            self.target_bpm_label.setStyleSheet("")
        
        # 更新力度百分比的样式
        if not set_velocity:
            self.velocity_spinbox.setStyleSheet(disabled_style)
            self.velocity_label.setStyleSheet("color: #888888;")
        else:
            self.velocity_spinbox.setStyleSheet(enabled_style)
            self.velocity_label.setStyleSheet("")
        
        # 更新重叠音符处理选项的样式
        if not check_overlap:
            self.fix_overlap_checkbox.setStyleSheet("color: #888888;")
            self.multitrack_overlap_checkbox.setStyleSheet("color: #888888;")
        else:
            self.fix_overlap_checkbox.setStyleSheet("")
            if not fix_overlap:
                self.multitrack_overlap_checkbox.setStyleSheet("color: #888888;")
            else:
                self.multitrack_overlap_checkbox.setStyleSheet("") 
