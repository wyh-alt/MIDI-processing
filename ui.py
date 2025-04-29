import os
import sys
import time
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                           QLabel, QLineEdit, QPushButton, QFileDialog, QProgressBar, 
                           QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox, 
                           QMessageBox, QGroupBox, QFormLayout, QTextEdit, QSplitter,
                           QTabWidget, QDialog)
from PyQt5.QtCore import Qt, pyqtSignal, QThread
from PyQt5.QtGui import QDragEnterEvent, QDropEvent, QFont, QIntValidator

from midi_processor import MidiProcessor

class WorkerThread(QThread):
    """处理MIDI文件的工作线程"""
    update_progress = pyqtSignal(int, int)  # 当前进度，总数
    update_result = pyqtSignal(dict)        # 处理结果
    update_log = pyqtSignal(str)            # 日志信息
    finished = pyqtSignal()                 # 处理完成信号
    
    def __init__(self, processor, files=None, input_dir=None, output_dir=None, 
                target_bpm=120, remove_cc=True, set_velocity=True, velocity_percent=80):
        super().__init__()
        self.processor = processor
        self.files = files or []
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.target_bpm = target_bpm
        self.remove_cc = remove_cc
        self.set_velocity = set_velocity
        self.velocity_percent = velocity_percent
        
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
                        self.velocity_percent
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
                    self.velocity_percent
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
        self.setWindowTitle("MIDI 速度转换工具")
        self.setMinimumSize(800, 600)
        
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
        
        # 创建输入区域
        input_group = QGroupBox("输入设置")
        input_layout = QFormLayout()
        
        # 创建目录选择区域
        dir_layout = QHBoxLayout()
        self.input_dir_edit = DragDropLineEdit()
        self.input_dir_edit.setPlaceholderText("输入目录 (拖放MIDI文件或文件夹到这里)")
        self.input_dir_edit.paths_dropped.connect(self.set_input_directory)
        browse_input_btn = QPushButton("浏览...")
        browse_input_btn.clicked.connect(self.browse_input_directory)
        dir_layout.addWidget(self.input_dir_edit)
        dir_layout.addWidget(browse_input_btn)
        input_layout.addRow("MIDI文件目录:", dir_layout)
        
        # 创建输出目录选择区域
        output_dir_layout = QHBoxLayout()
        self.output_dir_edit = DragDropLineEdit()
        self.output_dir_edit.setPlaceholderText("输出目录 (拖放目标文件夹到这里)")
        self.output_dir_edit.paths_dropped.connect(self.set_output_directory)
        browse_output_btn = QPushButton("浏览...")
        browse_output_btn.clicked.connect(self.browse_output_directory)
        output_dir_layout.addWidget(self.output_dir_edit)
        output_dir_layout.addWidget(browse_output_btn)
        input_layout.addRow("输出目录:", output_dir_layout)
        
        # 目标BPM输入
        self.target_bpm_edit = QLineEdit("120")
        self.target_bpm_edit.setValidator(QIntValidator(1, 999))
        input_layout.addRow("目标BPM:", self.target_bpm_edit)
        
        # 添加选项复选框
        options_layout = QHBoxLayout()
        self.remove_cc_checkbox = QCheckBox("删除所有控制信息 (CC/PC/压力等)")
        self.remove_cc_checkbox.setChecked(True)
        self.set_velocity_checkbox = QCheckBox("统一音符力度")
        self.set_velocity_checkbox.setChecked(True)
        options_layout.addWidget(self.remove_cc_checkbox)
        options_layout.addWidget(self.set_velocity_checkbox)
        input_layout.addRow("选项:", options_layout)
        
        # 添加力度百分比选择
        velocity_layout = QHBoxLayout()
        self.velocity_edit = QLineEdit("80")
        self.velocity_edit.setValidator(QIntValidator(1, 100))
        self.velocity_edit.setMaximumWidth(50)
        velocity_layout.addWidget(self.velocity_edit)
        velocity_layout.addWidget(QLabel("%"))
        velocity_layout.addStretch()
        input_layout.addRow("力度百分比:", velocity_layout)
        
        input_group.setLayout(input_layout)
        main_layout.addWidget(input_group)
        
        # 添加进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)
        
        # 添加开始按钮
        self.start_button = QPushButton("开始处理")
        self.start_button.clicked.connect(self.start_processing)
        main_layout.addWidget(self.start_button)
        
        # 创建分割器，分别显示表格和日志
        splitter = QSplitter(Qt.Vertical)
        
        # 创建表格显示处理结果
        self.result_table = QTableWidget(0, 6)
        self.result_table.setHorizontalHeaderLabels([
            "文件名", "原始速度(BPM)", "目标速度(BPM)", "音符力度", "删除CC控制", "状态"
        ])
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.result_table.setAlternatingRowColors(True)
        splitter.addWidget(self.result_table)
        
        # 添加日志显示框
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setPlaceholderText("处理日志将显示在这里...")
        font = QFont("Consolas", 9)
        self.log_edit.setFont(font)
        self.log_edit.setStyleSheet("background-color: #f0f0f0;")
        splitter.addWidget(self.log_edit)
        
        # 设置分割器初始大小
        splitter.setSizes([300, 200])
        
        main_layout.addWidget(splitter)
        
        # 设置中心部件
        self.setCentralWidget(central_widget)
    
    def set_input_directory(self, paths):
        # 先检查是否包含目录
        directories = [p for p in paths if os.path.isdir(p)]
        
        if directories:
            # 如果有目录，使用第一个目录
            self.input_directory = directories[0]
            self.midi_files = []
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
            
            # 如果还没有设置输出目录，将其设置为输入目录下的"处理结果"子目录
            if not self.output_directory:
                self.output_directory = os.path.join(directory, "处理结果")
                self.output_dir_edit.setText(self.output_directory)
    
    def browse_output_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if directory:
            self.output_directory = directory
            self.output_dir_edit.setText(directory)
    
    def start_processing(self):
        # 验证输入
        if not self.midi_files and not self.input_directory:
            QMessageBox.warning(self, "错误", "请选择MIDI文件或目录")
            return
        
        if not self.output_directory:
            QMessageBox.warning(self, "错误", "请选择输出目录")
            return
        
        try:
            target_bpm = int(self.target_bpm_edit.text())
            if target_bpm <= 0:
                raise ValueError("BPM必须大于0")
            
            # 验证力度百分比
            velocity_percent = int(self.velocity_edit.text())
            if velocity_percent <= 0 or velocity_percent > 100:
                raise ValueError("力度百分比必须在1-100之间")
        except ValueError as e:
            QMessageBox.warning(self, "错误", str(e))
            return
        
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
            remove_cc=self.remove_cc_checkbox.isChecked(),
            set_velocity=self.set_velocity_checkbox.isChecked(),
            velocity_percent=velocity_percent
        )
        
        # 连接信号
        self.worker.update_progress.connect(self.update_progress)
        self.worker.update_result.connect(self.add_result)
        self.worker.update_log.connect(self.add_log)
        self.worker.finished.connect(self.processing_finished)
        
        # 禁用界面元素
        self.start_button.setEnabled(False)
        self.start_button.setText("处理中...")
        
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
        
        # 显示所有原始速度
        if "tempo_changes" in result and result["tempo_changes"]:
            tempos = []
            for tempo_info in result["tempo_changes"]:
                bpm = tempo_info["bpm"]
                if isinstance(bpm, (int, float)):
                    tempos.append(f"{bpm:.1f}")
            
            if tempos:
                tempo_text = ", ".join(tempos) + " BPM"
            else:
                tempo_text = str(result["original_bpm"]) + " BPM"
        else:
            tempo_text = str(result["original_bpm"]) + " BPM"
        
        self.result_table.setItem(row, 1, QTableWidgetItem(tempo_text))
        
        self.result_table.setItem(row, 2, QTableWidgetItem(str(result["target_bpm"])))
        
        # 根据实际设置显示力度和CC状态
        if result["velocity_modified"]:
            # 显示百分比和实际MIDI值
            percent = self.velocity_edit.text()
            midi_value = min(127, max(1, int(127 * int(percent) / 100)))
            self.result_table.setItem(row, 3, QTableWidgetItem(f"{percent}% ({midi_value})"))
        else:
            self.result_table.setItem(row, 3, QTableWidgetItem("原始"))
        
        self.result_table.setItem(row, 4, QTableWidgetItem("是" if result["cc_removed"] else "否"))
        self.result_table.setItem(row, 5, QTableWidgetItem(result["status"]))
        
        # 设置状态单元格的颜色
        status_item = self.result_table.item(row, 5)
        if "错误" in result["status"]:
            status_item.setBackground(Qt.red)
            status_item.setForeground(Qt.white)
        else:
            status_item.setBackground(Qt.green)
            status_item.setForeground(Qt.black)
        
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
        
        # 添加完成日志
        self.log_edit.append("===== 处理完成 =====")
        
        # 显示完成消息
        QMessageBox.information(self, "完成", "MIDI文件处理完成")
        
        # 打开输出目录
        if os.path.exists(self.output_directory):
            os.startfile(self.output_directory)  # 仅适用于Windows 