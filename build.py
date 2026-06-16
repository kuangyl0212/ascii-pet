#!/usr/bin/env python3
"""将 ascii-pet-win.py 打包为 Windows exe"""

import subprocess
import sys
from pathlib import Path

def main():
    script = Path(__file__).parent / 'ascii-pet-win.py'
    if not script.exists():
        print(f'错误: 找不到 {script}')
        sys.exit(1)

    # 结束正在运行的旧进程
    subprocess.run(['taskkill', '/f', '/im', 'ascii-pet-win.exe'],
                   capture_output=True, check=False)

    # 检查 PyInstaller 是否可用
    try:
        subprocess.run([sys.executable, '-m', 'PyInstaller', '--version'],
                       capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print('PyInstaller 未安装，正在安装...')
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'pyinstaller'], check=True)

    icon = Path(__file__).parent / 'pet_icon.ico'
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--onefile',
        '--noconsole',
        '--name', 'ascii-pet-win',
        '--distpath', 'dist',
        '--workpath', 'build',
        '--specpath', 'build',
    ]
    if icon.exists():
        cmd.extend(['--icon', str(icon)])
    cmd.append(str(script))

    print(f'执行: {" ".join(cmd)}')
    subprocess.run(cmd, check=True)
    print(f'\n打包完成: dist/ascii-pet-win.exe')

if __name__ == '__main__':
    main()
