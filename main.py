import sys
import os
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon
from ui import MainWindow

def main():
    # 创建应用程序
    app = QApplication(sys.argv)
    
    # 设置应用程序样式
    app.setStyle("Fusion")
    
    # 设置样式表
    style_sheet = """
        QMainWindow, QWidget {
            background-color: #f5f5f5;
            color: #333333;
        }
        QPushButton {
            background-color: #3498db;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #2980b9;
        }
        QPushButton:disabled {
            background-color: #bdc3c7;
        }
        QProgressBar {
            border: 1px solid #bdc3c7;
            border-radius: 4px;
            text-align: center;
            height: 20px;
        }
        QProgressBar::chunk {
            background-color: #2ecc71;
            width: 10px;
            margin: 0.5px;
        }
        QTableWidget {
            gridline-color: #d0d0d0;
            selection-background-color: #3498db;
            selection-color: white;
        }
        QTableWidget::item {
            padding: 4px;
        }
        QGroupBox {
            border: 1px solid #bdc3c7;
            border-radius: 4px;
            margin-top: 12px;
            font-weight: bold;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 10px;
            padding: 0 5px;
        }
    """
    app.setStyleSheet(style_sheet)
    
    # 创建主窗口
    window = MainWindow()
    
    # 显示窗口
    window.show()
    
    # 运行应用程序
    sys.exit(app.exec_())

if __name__ == "__main__":
    main() 