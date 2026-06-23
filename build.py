#!/usr/bin/env python3
"""将 ascii-pet-win.py 打包为 Windows exe

支持双版本打包：
  python build.py            默认打包（当前 Python）
  python build.py --win7     用 Python 3.8 打包 Win7 兼容版
  python build.py --all      打包两个版本
"""

import subprocess
import sys
import shutil
from pathlib import Path

# Python 3.8 路径（最后一个支持 Win7 的版本）
PYTHON38 = r"C:\Python38\python.exe"

SCRIPT = Path(__file__).parent / 'ascii-pet-win.py'
ICON = Path(__file__).parent / 'pet_icon.ico'
LOCALES_DIR = Path(__file__).parent / 'locales'


def build(python_exe, name_suffix="", workpath_suffix=""):
    """用指定 Python 打包。"""
    if not SCRIPT.exists():
        print(f'错误: 找不到 {SCRIPT}')
        sys.exit(1)

    python_exe = shutil.which(python_exe) or python_exe
    print(f'\n{"="*60}')
    print(f'打包: {name_suffix or "默认版"}')
    print(f'Python: {python_exe}')
    print(f'{"="*60}')

    # 结束正在运行的旧进程
    subprocess.run(['taskkill', '/f', '/im', 'ascii-pet-win.exe'],
                   capture_output=True, check=False)

    # 检查 PyInstaller
    try:
        subprocess.run([python_exe, '-m', 'PyInstaller', '--version'],
                       capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print('PyInstaller 未安装，正在安装...')
        subprocess.run([python_exe, '-m', 'pip', 'install', 'pyinstaller'], check=True)

    distpath = 'dist'
    workpath = f'build{workpath_suffix}'
    specpath = workpath

    cmd = [
        python_exe, '-m', 'PyInstaller',
        '--onefile',
        '--noconsole',
        '--name', f'ascii-pet-win{name_suffix}',
        '--distpath', distpath,
        '--workpath', workpath,
        '--specpath', specpath,
        '--hidden-import', 'lan',
        '--hidden-import', 'lan_protocol',
        '--hidden-import', 'i18n',
    ]
    if LOCALES_DIR.exists():
        cmd.extend(['--add-data', f'{LOCALES_DIR};locales'])
    if ICON.exists():
        cmd.extend(['--icon', str(ICON)])
    cmd.append(str(SCRIPT))

    print(f'执行: {" ".join(cmd)}')
    subprocess.run(cmd, check=True)
    print(f'\n打包完成: {distpath}/ascii-pet-win{name_suffix}.exe')


def main():
    args = sys.argv[1:]
    build_win7 = '--win7' in args or '--all' in args
    build_default = '--all' in args or not build_win7

    if build_default:
        build(sys.executable)

    if build_win7:
        if not Path(PYTHON38).exists():
            print(f'错误: 找不到 Python 3.8 ({PYTHON38})，无法打包 Win7 版本')
            sys.exit(1)
        build(PYTHON38, name_suffix="-win7", workpath_suffix="-win7")

    print(f'\n{"="*60}')
    print('全部打包完成！')
    if build_default:
        print(f'  默认版: dist/ascii-pet-win.exe')
    if build_win7:
        print(f'  Win7版: dist/ascii-pet-win-win7.exe')
    print(f'{"="*60}')


if __name__ == '__main__':
    main()
