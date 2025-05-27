import PyInstaller.__main__
import os

# 获取当前目录
current_dir = os.path.dirname(os.path.abspath(__file__))
icon_path = os.path.join(current_dir, 'img', 'owl.ico')

PyInstaller.__main__.run([
    'mian.py',
    '--name=Pilatus 2M 图像拼接工具',
    '--noconsole',
    f'--icon={icon_path}',
    '--clean',
    '--noupx',
    '--onedir',
    '--add-data', f'{icon_path};img',
    '--hidden-import', 'numpy',
    '--hidden-import', 'scipy.ndimage',
    '--hidden-import', 'fabio',
    '--hidden-import', 'fabio.tifimage',
    '--collect-submodules', 'fabio',
    '--exclude-module', 'matplotlib',
    '--exclude-module', 'PyQt5',
    '--exclude-module', 'tkinter',
    '--exclude-module', 'PIL.ImageQt',
]) 