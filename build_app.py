import os
import sys
import subprocess
import shutil
import pkg_resources

def build_exe():
    """
    使用PyInstaller打包应用程序为可执行文件，
    确保包含所有必要的依赖和文件，以便在任何Windows系统运行
    """
    print("="*60)
    print("开始打包MIDI速度转换工具为可执行文件")
    print("="*60)
    
    # 安装必要的库
    required_packages = ['pyinstaller', 'pillow', 'mido', 'python-rtmidi']
    for package in required_packages:
        try:
            pkg_resources.get_distribution(package)
            print(f"检测到{package}已安装")
        except pkg_resources.DistributionNotFound:
            print(f"正在安装{package}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
    
    # 应用程序名称
    app_name = "MIDI速度转换工具"
    
    # 清理旧的构建文件
    for dir_to_clean in ["build", "dist", f"{app_name}.spec"]:
        if os.path.exists(dir_to_clean):
            print(f"清理 {dir_to_clean}...")
            try:
                if os.path.isdir(dir_to_clean):
                    shutil.rmtree(dir_to_clean)
                else:
                    os.remove(dir_to_clean)
            except Exception as e:
                print(f"警告: 无法清理 {dir_to_clean}: {e}")
    
    # 如果需要创建图标
    icon_path = "icon.ico"
    if not os.path.exists(icon_path):
        try:
            # 尝试使用Pillow创建简单图标
            from PIL import Image, ImageDraw, ImageFont
            img = Image.new('RGBA', (256, 256), color=(0, 87, 174, 255))
            draw = ImageDraw.Draw(img)
            
            # 绘制一些内容到图标
            # 在中心绘制音符符号
            try:
                # 尝试绘制文本
                font_size = 120
                try:
                    # 尝试加载系统字体
                    if os.name == 'nt':  # Windows
                        font_path = os.path.join(os.environ['WINDIR'], 'Fonts', 'Arial.ttf')
                        if os.path.exists(font_path):
                            font = ImageFont.truetype(font_path, font_size)
                        else:
                            font = ImageFont.load_default()
                    else:
                        font = ImageFont.load_default()
                except:
                    font = ImageFont.load_default()
                
                text = "♪"
                # PIL >=10.0.0 版本使用textbbox
                try:
                    text_width, text_height = draw.textbbox((0,0), text, font=font)[2:4]
                except AttributeError:
                    # 旧版本PIL使用不同方法
                    try:
                        text_width, text_height = draw.textsize(text, font=font)
                    except:
                        text_width, text_height = 50, 50  # 默认估计

                position = ((256 - text_width) // 2, (256 - text_height) // 2)
                draw.text(position, text, fill=(255, 255, 255), font=font)
            except Exception as e:
                print(f"无法添加文本到图标: {e}")
                
            # 保存图标
            img.save(icon_path)
            print(f"已创建应用程序图标: {icon_path}")
        except ImportError:
            print("警告: PIL库未安装，将使用默认图标")
            icon_path = None
        except Exception as e:
            print(f"创建图标时出错: {e}")
            icon_path = None
    
    # 确保打包目录存在
    os.makedirs("dist", exist_ok=True)
    
    # 配置PyInstaller选项
    pyinstaller_args = [
        "main.py",
        "--name={}".format(app_name),
        "--windowed",               # 无控制台窗口
        "--onefile",                # 创建单个EXE文件
        "--clean",                  # 清理临时文件
        "--noconfirm",              # 不显示确认对话框
        "--log-level=INFO",         # 显示详细信息
        "--hidden-import=mido.backends.rtmidi",  # 包含MIDI后端
    ]
    
    # 添加图标(如果存在)
    if icon_path and os.path.exists(icon_path):
        pyinstaller_args.append(f"--icon={icon_path}")
    
    # 运行PyInstaller
    print("\n开始构建可执行文件...")
    print(f"使用选项: {' '.join(pyinstaller_args)}")
    
    try:
        # 使用subprocess运行PyInstaller以便捕获输出
        process = subprocess.Popen(
            [sys.executable, "-m", "PyInstaller"] + pyinstaller_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        # 实时显示输出
        for line in process.stdout:
            print(line.strip())
        
        process.wait()
        
        if process.returncode != 0:
            print(f"PyInstaller返回错误代码: {process.returncode}")
            sys.exit(1)
        
        # 检查构建是否成功
        exe_path = os.path.join("dist", f"{app_name}.exe")
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / (1024 * 1024)
            print(f"\n构建成功! 可执行文件大小: {size_mb:.2f} MB")
            print(f"可执行文件位置: {os.path.abspath(exe_path)}")
            print("\n你可以将此文件分享给其他Windows用户，无需安装Python即可运行。")
        else:
            print("\n错误: 构建过程似乎完成，但找不到输出文件。")
    except Exception as e:
        print(f"\n构建过程中出错: {e}")
        raise

if __name__ == "__main__":
    try:
        build_exe()
    except Exception as e:
        print(f"打包过程中出现错误: {e}")
        sys.exit(1) 