import os
import sys
import subprocess
import shutil

def build_exe():
    """
    使用PyInstaller打包应用程序为可执行文件
    """
    print("开始打包MIDI速度转换工具为EXE文件...")
    
    # 检查并安装PyInstaller
    try:
        import PyInstaller
        print("PyInstaller已安装")
    except ImportError:
        print("正在安装PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        print("PyInstaller安装完成")
    
    # 应用程序名称
    app_name = "MIDI速度转换工具"
    
    # 删除旧的构建文件(如果存在)
    if os.path.exists("build"):
        print("删除旧的build目录...")
        shutil.rmtree("build")
    if os.path.exists("dist"):
        print("删除旧的dist目录...")
        shutil.rmtree("dist")
    
    # 创建临时的icon文件
    # 注意: 你可以替换为自己的icon文件，或者使用其他方式提供图标
    if not os.path.exists("icon.ico"):
        print("创建应用程序图标...")
        try:
            from PIL import Image
            # 创建一个简单的彩色图片作为图标
            img = Image.new('RGB', (256, 256), color = (0, 120, 212))
            img.save('temp_icon.png')
            
            # 转换为ICO文件
            img.save('icon.ico')
        except ImportError:
            print("PIL库未安装，将使用默认图标")
    
    # 构建命令
    cmd = [
        "pyinstaller",
        "--name={}".format(app_name),
        "--windowed",  # 不显示控制台窗口
        "--onefile",   # 打包成单个文件
        "--clean",     # 清理临时文件
        "--noconfirm", # 不显示确认提示
    ]
    
    # 如果图标存在，添加到命令行
    if os.path.exists("icon.ico"):
        cmd.append("--icon=icon.ico")
    
    # 添加主程序文件
    cmd.append("main.py")
    
    # 运行PyInstaller
    print("正在运行PyInstaller...")
    print(" ".join(cmd))
    subprocess.check_call(cmd)
    
    print("\n打包完成!")
    print(f"可执行文件位于: dist/{app_name}.exe")
    print("你可以将此文件分享给其他Windows用户，无需安装Python即可运行。")

if __name__ == "__main__":
    build_exe() 