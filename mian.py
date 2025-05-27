import os
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
os.environ["QT_SCALE_FACTOR"] = "1"

import sys
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QLabel, QMessageBox)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QIcon, QDragEnterEvent, QDropEvent
# import resources_rc

def get_resource_path(relative_path):
    """获取资源文件的绝对路径"""
    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class StitchThread(QThread):
    finished = Signal(str)
    error = Signal(str)
    progress = Signal(str)
    
    def __init__(self, img_files):
        super().__init__()
        self.img_files = img_files
        self._gap_mask = None
        self.is_running = False

    @property
    def gap_mask(self):
        """延迟加载掩模数据"""
        if self._gap_mask is None:
            try:
                self._gap_mask = self.get_gap_mask()
            except Exception as e:
                raise Exception(f"加载GAP模板失败: {str(e)}")
        return self._gap_mask

    @staticmethod
    def get_gap_mask():
        """返回内置的gap掩模数据"""
        try:
            import base64
            import numpy as np
            from gap_base64 import GAP_TEMPLATE_DATA
            
            decoded_bytes = base64.b64decode(GAP_TEMPLATE_DATA)
            decoded_data = np.frombuffer(decoded_bytes, dtype=np.uint8)
            return decoded_data.reshape(1679, 1475, 4)
            
        except Exception as e:
            raise Exception(f"无法加载GAP模板: {str(e)}")

    def run(self):
        self.is_running = True
        try:
            import fabio
            import fabio.tifimage
            import numpy as np
            from scipy.ndimage import map_coordinates
            
            gap_mask = np.array(self.gap_mask).astype(bool)
            
            # 读取三张图片
            try:
                self.progress.emit(f"正在读取图片: {os.path.basename(self.img_files[0])}")
                img1 = fabio.open(self.img_files[0]).data
                self.progress.emit(f"正在读取图片: {os.path.basename(self.img_files[1])}")
                img2 = fabio.open(self.img_files[1]).data
                self.progress.emit(f"正在读取图片: {os.path.basename(self.img_files[2])}")
                img3 = fabio.open(self.img_files[2]).data
            except Exception as e:
                raise Exception(f"读取图片失败: {str(e)}")
            
            #获取拼接后的文件保存地址
            first_img_path = self.img_files[0]
            save_dir = os.path.dirname(os.path.abspath(first_img_path))
            base_name = os.path.splitext(os.path.basename(first_img_path))[0]
            
            try:
                #第一次拼接
                self.progress.emit("正在进行第一次拼接...")
                xoffset = 17.5
                yoffset = -24
                yy, xx, _ = np.where(gap_mask)
                py = yy + yoffset
                px = xx + xoffset
                fix01 = np.copy(img1)
                fix01[gap_mask[..., 0]] = map_coordinates(img2, np.asarray([py, px]), order=1)
            except Exception as e:
                raise Exception(f"第一次拼接失败: {str(e)}")
            
            try:
                self.progress.emit("正在保存第一次拼接结果...")
                fix01_path = os.path.join(save_dir, f"{base_name}_fix01.tif")
                tif = fabio.tifimage.TifImage(data=fix01.astype(np.uint32))
                tif.write(fix01_path)
            except Exception as e:
                raise Exception(f"保存第一次拼接结果失败: {str(e)}")

            try:
                self.progress.emit("正在进行第二次拼接...")
                xoffset = -35
                yoffset = 48
                yy, xx, _ = np.where(gap_mask)
                py = yy + yoffset
                px = xx + xoffset
                fix02 = np.copy(img3)
                fix02[gap_mask[..., 0]] = map_coordinates(fix01, np.asarray([py, px]), order=1)
            except Exception as e:
                raise Exception(f"第二次拼接失败: {str(e)}")
            
            try:
                self.progress.emit("正在保存最终结果...")
                fix02_path = os.path.join(save_dir, f"{base_name}_fix02.tif")
                tif = fabio.tifimage.TifImage(data=fix02.astype(np.uint32))
                tif.write(fix02_path)
            except Exception as e:
                raise Exception(f"保存最终结果失败: {str(e)}")

            if not os.path.exists(fix01_path) or not os.path.exists(fix02_path):
                raise Exception("文件未成功保存")
                
            self.progress.emit("拼接完成！")
            self.finished.emit(f"{fix01_path}\n{fix02_path}")
            
        except Exception as e:
            self.error.emit(f"处理出错: {str(e)}")
        finally:
            self.is_running = False

class DropArea(QLabel):
    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.setText("将三张tif图片或包含tif图片的文件夹拖拽到这里")
        self.setStyleSheet("""
            QLabel {
                border: 2px dashed #aaa;
                border-radius: 5px;
                padding: 20px;
                background: #f0f0f0;
                min-height: 150px;
            }
        """)
        self.setAcceptDrops(True)
        self.stitch_thread = None
        self.processing = False
        self.current_group = None
        self.pending_groups = []

    def show_warning(self, title, message):
        """显示警告对话框"""
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.exec_()

    def dragEnterEvent(self, event: QDragEnterEvent):
        """允许拖拽进入"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        """允许拖拽移动"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def check_group_validity(self, groups):
        """检查每个分组是否满足三个一组的条件"""
        for prefix, files in groups.items():
            if len(files) >= 3:
                if len(files) % 3 != 0:
                    error_msg = f"前缀为 '{prefix}' 的文件组有 {len(files)} 个文件，不满足三个一组的条件。\n请确保同前缀的文件数量是3的倍数。"
                    self.show_warning("文件组错误", error_msg)
                    return False
        return True

    def group_files_by_prefix(self, files):
        """将文件按前缀分组"""
        groups = {}
        for file_path in files:
            prefix = self.get_file_prefix(file_path)
            if prefix not in groups:
                groups[prefix] = []
            groups[prefix].append(file_path)
        return groups

    def get_file_prefix(self, filename):
        """获取文件名前缀"""
        base_name = os.path.basename(filename)
        parts = base_name.split('_')
        return '_'.join(parts[:-1]) if '_' in base_name else base_name.rstrip('0123456789.tif')

    def process_files(self, files):
        """处理文件或文件夹"""
        try:
            # 重置所有状态
            self.pending_groups = []
            self.processing = False
            self.current_group = None
            if self.stitch_thread:
                self.stitch_thread.wait()
                self.stitch_thread = None
            
            tif_files = []
            for file_path in files:
                if os.path.isdir(file_path):
                    dir_files = []
                    for root, _, filenames in os.walk(file_path):
                        for filename in filenames:
                            if filename.lower().endswith('.tif'):
                                full_path = os.path.join(root, filename)
                                dir_files.append(full_path)

                    if not dir_files:
                        self.setText("未在文件夹中找到任何tif文件")
                        return

                    # 按文件名排序
                    dir_files.sort(key=lambda x: os.path.basename(x))
                    
                    # 按前缀分组
                    groups = self.group_files_by_prefix(dir_files)
                    
                    if not groups:
                        self.setText("未能正确分组文件")
                        return

                    # 检查每个分组是否满足条件
                    if not self.check_group_validity(groups):
                        self.setText("请重新选择文件或文件夹")
                        return

                    # 将所有可处理的组添加到待处理列表
                    for prefix, group_files in groups.items():
                        if len(group_files) >= 3:
                            for i in range(0, len(group_files) - 2, 3):
                                batch = group_files[i:i+3]
                                if len(batch) == 3:
                                    self.pending_groups.append(batch)

                    if not self.pending_groups:
                        self.setText("没有找到可以处理的完整文件组（需要3个文件一组）")
                        return

                    total_groups = len(self.pending_groups)
                    self.setText(f"找到 {total_groups} 个文件组待处理...")
                    
                    # 开始处理第一组
                    self.start_processing()
                
                elif file_path.lower().endswith('.tif'):
                    tif_files.append(file_path)
            
            # 处理直接拖拽的tif文件
            if len(tif_files) == 3:
                self.pending_groups = [tif_files]
                self.start_processing()
            elif len(tif_files) > 0:
                error_msg = "直接拖拽时需要exactly 3张tif图片!"
                self.show_warning("文件数量错误", error_msg)
                self.setText(error_msg)

        except Exception as e:
            self.setText(f"处理出错: {str(e)}")

    def start_processing(self):
        """开始处理队列中的文件组"""
        if not self.processing and self.pending_groups:
            self.process_next_group()

    def process_next_group(self):
        """处理下一组文件"""
        try:
            if self.processing:
                return

            if not self.pending_groups:
                self.setText("所有组处理完成！")
                return

            self.processing = True
            group = self.pending_groups.pop(0)
            self.process_single_group(group)
            
        except Exception as e:
            self.processing = False
            self.setText(f"处理下一组时出错: {str(e)}")
            QTimer.singleShot(1000, self.start_processing)

    def process_single_group(self, files):
        """处理单个文件组"""
        try:
            files.sort(key=lambda x: int(''.join(filter(str.isdigit, os.path.basename(x)))))
            
            self.current_group = files
            self.stitch_thread = StitchThread(files)
            self.stitch_thread.finished.connect(self.on_stitch_complete)
            self.stitch_thread.error.connect(self.on_stitch_error)
            self.stitch_thread.progress.connect(self.on_progress)
            
            remaining = len(self.pending_groups)
            self.setText(f"正在处理: {[os.path.basename(f) for f in files]}\n(剩余 {remaining} 组)")
            
            self.stitch_thread.start()
            
        except Exception as e:
            self.setText(f"处理文件组时出错: {str(e)}")
            self.processing = False
            QTimer.singleShot(1000, self.start_processing)

    def on_progress(self, message):
        """更新处理进度"""
        try:
            current_files = [os.path.basename(f) for f in (self.current_group or [])]
            remaining = len(self.pending_groups)
            status = f"正在处理: {current_files}\n{message}\n剩余组数: {remaining}"
            self.setText(status)
        except Exception:
            pass

    def on_stitch_complete(self, output_path):
        try:
            fix01_path, fix02_path = output_path.split('\n')
            fix01_name = os.path.basename(fix01_path)
            fix02_name = os.path.basename(fix02_path)
            
            if self.pending_groups:
                msg = f"完成一组处理:\n{fix01_name}\n{fix02_name}\n\n剩余 {len(self.pending_groups)} 组待处理..."
            else:
                msg = f"所有处理完成!\n最后一组:\n{fix01_name}\n{fix02_name}\n\n可以继续拖拽文件或文件夹"
            
            self.setText(msg)
            
            # 重置处理状态
            self.processing = False
            self.current_group = None
            
            # 继续处理下一组
            QTimer.singleShot(1000, self.start_processing)
                
        except Exception as e:
            self.setText("处理完成，但更新状态时出错")
            self.processing = False
            QTimer.singleShot(1000, self.start_processing)
        
    def on_stitch_error(self, error_msg):
        self.setText(f"错误:\n{error_msg}\n\n剩余 {len(self.pending_groups)} 组待处理...")
        self.processing = False
        self.current_group = None
        QTimer.singleShot(1000, self.start_processing)

    def dropEvent(self, event: QDropEvent):
        """处理拖拽释放事件"""
        try:
            files = [url.toLocalFile() for url in event.mimeData().urls()]
            self.process_files(files)
        except Exception as e:
            self.setText(f"处理拖拽事件时出错: {str(e)}")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pilatus 2M 图像拼接")
        self.setFixedSize(400, 300)
        
        # 设置窗口图标
        icon_path = get_resource_path(os.path.join("img", "owl.ico"))
        if os.path.exists(icon_path):
            icon = QIcon(icon_path)
            self.setWindowIcon(icon)
            # 同时设置任务栏图标
            if hasattr(self, "setWindowIcon"):
                self.setWindowIcon(icon)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        
        self.drop_area = DropArea()
        layout.addWidget(self.drop_area)
        
        info_label = QLabel(
            "使用说明:\n"
            "1. 一次拖入3张按序号排列的tif图片\n"
            "2. 程序会自动按序号排序并拼接\n"
            "3. 拼接结果将保存在源文件目录下"
        )
        info_label.setAlignment(Qt.AlignCenter)
        info_label.setStyleSheet("color: #666;")
        layout.addWidget(info_label)

        # 添加作者标签
        self.author_label = QLabel("Designed by GP at BL02U2", central_widget)
        self.author_label.setStyleSheet("""
            QLabel {
                color: #A0A0A0;
                font-size: 9pt;
                font-family: "Microsoft YaHei";
            }
        """)
        self.author_label.setGeometry(188, 280, 200, 21)
        self.author_label.setAlignment(Qt.AlignRight)

        # 创建定时器，5秒后隐藏标签
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide_author_label)
        self.timer.start(5000)

    def hide_author_label(self):
        """隐藏作者标签"""
        self.author_label.hide()

def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    # 设置应用程序图标
    icon_path = get_resource_path(os.path.join("img", "owl.ico"))
    if os.path.exists(icon_path):
        icon = QIcon(icon_path)
        app.setWindowIcon(icon)
        # 确保在 Windows 上设置任务栏图标
        if sys.platform == 'win32':
            import ctypes
            myappid = 'pilatus.imagestitching.1.0'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    
    window = MainWindow()
    window.show()
    
    # 将窗口移动到屏幕中央
    screen = QApplication.primaryScreen().geometry()
    x = (screen.width() - window.width()) // 2
    y = (screen.height() - window.height()) // 2
    window.move(x, y)
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()