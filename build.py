import os
import sys
import subprocess
import shutil
import pkg_resources

def install_requirements():
    """
    安装所有必要的依赖
    """
    print("检查并安装依赖...")
    
    # 从requirements.txt读取依赖
    requirements_file = "requirements.txt"
    if os.path.exists(requirements_file):
        with open(requirements_file, 'r', encoding='utf-8') as f:
            requirements = [line.strip() for line in f.readlines() if line.strip() and not line.startswith('#')]
    else:
        # 默认依赖列表
        requirements = ['pyqt5>=5.15.0', 'mido>=1.2.10', 'python-rtmidi>=1.4.9']
    
    # 添加打包必需的依赖
    build_requirements = ['pyinstaller>=5.0', 'pillow>=8.0.0']
    all_requirements = requirements + build_requirements
    
    for package in all_requirements:
        package_name = package.split('>=')[0].split('==')[0].split('<')[0]
        try:
            pkg_resources.get_distribution(package_name)
            print(f"✓ {package_name} 已安装")
        except pkg_resources.DistributionNotFound:
            print(f"正在安装 {package}...")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", package], 
                                     stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                print(f"✓ {package} 安装成功")
            except subprocess.CalledProcessError as e:
                print(f"✗ 安装 {package} 失败: {e}")
                return False
    return True

def create_icon():
    """
    创建应用程序图标
    """
    icon_path = "icon.ico"
    if os.path.exists(icon_path):
        print(f"✓ 使用现有图标: {icon_path}")
        return icon_path
    
    try:
        from PIL import Image, ImageDraw, ImageFont
        print("正在创建应用程序图标...")
        
        # 创建多尺寸图标
        sizes = [16, 32, 48, 64, 128, 256]
        images = []
        
        for size in sizes:
            img = Image.new('RGBA', (size, size), color=(0, 120, 215, 255))  # Windows蓝色
            draw = ImageDraw.Draw(img)
            
            # 绘制音符符号
            font_size = max(size // 3, 12)
            try:
                if os.name == 'nt':  # Windows
                    font_paths = [
                        os.path.join(os.environ.get('WINDIR', ''), 'Fonts', 'segoeui.ttf'),
                        os.path.join(os.environ.get('WINDIR', ''), 'Fonts', 'arial.ttf'),
                    ]
                    font = None
                    for font_path in font_paths:
                        if os.path.exists(font_path):
                            font = ImageFont.truetype(font_path, font_size)
                            break
                    if font is None:
                        font = ImageFont.load_default()
                else:
                    font = ImageFont.load_default()
            except:
                font = ImageFont.load_default()
            
            # 绘制音符符号
            text = "♪♫"
            try:
                bbox = draw.textbbox((0, 0), text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
            except:
                try:
                    text_width, text_height = draw.textsize(text, font=font)
                except:
                    text_width, text_height = size // 2, size // 3
            
            x = (size - text_width) // 2
            y = (size - text_height) // 2
            draw.text((x, y), text, fill=(255, 255, 255), font=font)
            
            images.append(img)
        
        # 保存为ICO文件
        images[0].save(icon_path, format='ICO', sizes=[(img.width, img.height) for img in images])
        print(f"✓ 创建图标成功: {icon_path}")
        return icon_path
        
    except ImportError:
        print("警告: PIL库未安装，将不使用自定义图标")
        return None
    except Exception as e:
        print(f"创建图标时出错: {e}")
        return None

def clean_build_files():
    """
    清理构建文件
    """
    print("清理旧的构建文件...")
    directories_to_clean = ["build", "dist", "__pycache__"]
    files_to_clean = ["*.spec"]
    
    for directory in directories_to_clean:
        if os.path.exists(directory):
            try:
                shutil.rmtree(directory)
                print(f"✓ 清理目录: {directory}")
            except Exception as e:
                print(f"警告: 无法清理目录 {directory}: {e}")
    
    # 清理spec文件
    import glob
    for spec_file in glob.glob("*.spec"):
        try:
            os.remove(spec_file)
            print(f"✓ 清理文件: {spec_file}")
        except Exception as e:
            print(f"警告: 无法清理文件 {spec_file}: {e}")

def build_exe():
    """
    使用PyInstaller打包应用程序为可执行文件
    """
    print("="*60)
    print("MIDI处理整合工具 - 可执行文件打包器")
    print("="*60)
    
    # 步骤1: 安装依赖
    if not install_requirements():
        print("✗ 依赖安装失败，无法继续打包")
        return False
    
    # 步骤2: 清理旧文件
    clean_build_files()
    
    # 步骤3: 创建图标
    icon_path = create_icon()
    
    # 步骤4: 配置打包参数
    app_name = "MIDI处理整合工具"
    main_script = "main.py"
    
    if not os.path.exists(main_script):
        print(f"✗ 主脚本文件不存在: {main_script}")
        return False
    
    print(f"\n开始打包: {app_name}")
    print(f"主脚本: {main_script}")
    
    # PyInstaller参数
    pyinstaller_args = [
        main_script,
        f"--name={app_name}",
        "--windowed",                    # 无控制台窗口（GUI应用）
        "--onefile",                     # 单文件执行
        "--clean",                       # 清理临时文件
        "--noconfirm",                   # 不显示确认对话框
        "--log-level=INFO",              # 显示详细信息
        "--hidden-import=mido.backends.rtmidi",    # MIDI后端
        "--hidden-import=mido.backends.portmidi",  # 备用MIDI后端
        "--hidden-import=PyQt5.QtPrintSupport",    # PyQt5打印支持
        "--collect-all=mido",            # 收集所有mido模块
        "--collect-submodules=PyQt5",    # 收集PyQt5子模块
    ]
    
    # 添加图标
    if icon_path and os.path.exists(icon_path):
        pyinstaller_args.append(f"--icon={icon_path}")
        print(f"✓ 使用图标: {icon_path}")
    
    # 添加版本信息（可选）
    version_info = {
        'version': '2.1.0',
        'description': 'MIDI文件处理整合工具',
        'company': 'MIDI Tools',
        'product': 'MIDI处理整合工具',
        'copyright': '© 2024 MIDI Tools'
    }
    
    # 运行PyInstaller
    print("\n开始构建...")
    print(f"命令: pyinstaller {' '.join(pyinstaller_args)}")
    
    try:
        # 执行打包
        result = subprocess.run(
            [sys.executable, "-m", "PyInstaller"] + pyinstaller_args,
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        
        if result.returncode == 0:
            # 检查输出文件
            exe_path = os.path.join("dist", f"{app_name}.exe")
            if os.path.exists(exe_path):
                size_mb = os.path.getsize(exe_path) / (1024 * 1024)
                print(f"\n🎉 打包成功!")
                print(f"✓ 可执行文件: {os.path.abspath(exe_path)}")
                print(f"✓ 文件大小: {size_mb:.2f} MB")
                print(f"\n📋 使用说明:")
                print(f"   1. 将 {app_name}.exe 复制到任意Windows电脑")
                print(f"   2. 双击运行，无需安装Python或其他依赖")
                print(f"   3. 支持Windows 7/10/11等系统")
                print(f"\n⚠️  注意事项:")
                print(f"   - 首次运行可能需要较长时间初始化")
                print(f"   - 某些杀毒软件可能误报，请添加信任")
                print(f"   - 建议在处理重要文件前先备份")
                return True
            else:
                print("\n✗ 打包完成但找不到输出文件")
                print("构建输出:")
                print(result.stdout)
                if result.stderr:
                    print("错误输出:")
                    print(result.stderr)
                return False
        else:
            print(f"\n✗ 打包失败 (返回码: {result.returncode})")
            print("错误输出:")
            print(result.stderr)
            if result.stdout:
                print("标准输出:")
                print(result.stdout)
            return False
            
    except Exception as e:
        print(f"\n✗ 打包过程中出现异常: {e}")
        return False

def main():
    """主函数"""
    try:
        success = build_exe()
        if success:
            print("\n🎯 打包完成! 您的MIDI处理工具已准备就绪!")
            sys.exit(0)
        else:
            print("\n💥 打包失败，请检查上述错误信息")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n⏹️  用户中断了打包过程")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 打包过程中发生未预期的错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main() 