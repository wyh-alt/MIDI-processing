#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MIDI速度转换程序打包脚本
使用PyInstaller将程序打包为exe文件
"""

import os
import sys
import subprocess
import shutil

def install_pyinstaller():
    """安装PyInstaller"""
    print("正在安装PyInstaller...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        print("PyInstaller安装成功！")
        return True
    except subprocess.CalledProcessError:
        print("PyInstaller安装失败！")
        return False

def create_spec_file():
    """创建PyInstaller的spec配置文件"""
    spec_content = '''# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('icon.ico', '.'),
        ('icon_16x16.png', '.'),
        ('icon_32x32.png', '.'),
        ('icon_48x48.png', '.'),
        ('icon_64x64.png', '.'),
        ('icon_128x128.png', '.'),
        ('icon_256x256.png', '.'),
    ],
    hiddenimports=[
        'PyQt5.QtCore',
        'PyQt5.QtGui', 
        'PyQt5.QtWidgets',
        'mido',
        'mido.backends.rtmidi',
        'rtmidi',
        'pandas',
        'openpyxl',
        'openpyxl.cell',
        'openpyxl.workbook',
        'openpyxl.worksheet',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='MIDI速度转换工具',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico'
)
'''
    
    with open('MIDI速度转换工具.spec', 'w', encoding='utf-8') as f:
        f.write(spec_content)
    
    print("已创建spec配置文件")

def build_exe():
    """使用PyInstaller打包程序"""
    print("开始打包程序...")
    
    # 检查是否存在spec文件
    if not os.path.exists('MIDI速度转换工具.spec'):
        create_spec_file()
    
    try:
        # 使用spec文件打包
        subprocess.check_call([
            sys.executable, "-m", "PyInstaller", 
            "--clean",  # 清理临时文件
            "MIDI速度转换工具.spec"
        ])
        print("程序打包成功！")
        return True
    except subprocess.CalledProcessError as e:
        print(f"程序打包失败：{e}")
        return False

def copy_output_files():
    """复制输出文件到当前目录"""
    dist_dir = "dist"
    if os.path.exists(dist_dir):
        # 复制exe文件到当前目录
        for file in os.listdir(dist_dir):
            if file.endswith('.exe'):
                src = os.path.join(dist_dir, file)
                dst = os.path.join('.', file)
                shutil.copy2(src, dst)
                print(f"已复制exe文件：{file}")
        
        # 复制整个dist目录（包含所有依赖）
        dist_copy_dir = "MIDI速度转换工具_完整版"
        if os.path.exists(dist_copy_dir):
            shutil.rmtree(dist_copy_dir)
        shutil.copytree(dist_dir, dist_copy_dir)
        print(f"已创建完整版目录：{dist_copy_dir}")
        
        return True
    else:
        print("未找到dist目录")
        return False

def clean_build_files():
    """清理构建文件"""
    dirs_to_clean = ['build', '__pycache__']
    files_to_clean = ['MIDI速度转换工具.spec']
    
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name)
            print(f"已清理目录：{dir_name}")
    
    for file_name in files_to_clean:
        if os.path.exists(file_name):
            os.remove(file_name)
            print(f"已清理文件：{file_name}")

def main():
    """主函数"""
    print("=== MIDI速度转换程序打包工具 ===")
    print()
    
    # 检查并安装PyInstaller
    try:
        import PyInstaller
        print("PyInstaller已安装")
    except ImportError:
        if not install_pyinstaller():
            return
    
    # 打包程序
    if build_exe():
        # 复制输出文件
        copy_output_files()
        
        print()
        print("=== 打包完成 ===")
        print("生成的文件：")
        print("1. MIDI速度转换工具.exe - 主程序")
        print("2. MIDI速度转换工具_完整版/ - 包含所有依赖的完整版本")
        print()
        print("注意：")
        print("- 主程序exe文件可以直接运行")
        print("- 完整版目录包含所有依赖，可以分发给其他用户")
        
        # 询问是否清理构建文件
        try:
            choice = input("是否清理构建文件？(y/n): ").lower().strip()
            if choice in ['y', 'yes', '是']:
                clean_build_files()
                print("构建文件已清理")
        except KeyboardInterrupt:
            print("\n用户取消操作")
    else:
        print("打包失败，请检查错误信息")

if __name__ == "__main__":
    main()
