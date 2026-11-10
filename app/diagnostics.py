"""On-demand desktop performance statistics using platform-native Qt controls."""
from collections import deque
import math
import os
import platform
import sys
import time
from html import escape
import psutil

from PySide6.QtCore import Qt, QTimer, QPointF, QRectF
from PySide6.QtGui import QFont, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout,
                               QHBoxLayout, QScrollArea, QDialogButtonBox, QCheckBox,
                               QFrame, QGridLayout, QSizePolicy, QToolButton, QToolTip)

from performance_metrics import (PlaybackStatistics, ProcessStatistics,
                                 byte_text, frame_cache_statistics, process_paging_rows)
from diagnostic_identity import HardwareProbe, desktop_status, cli_status, desktop_summary
from version import platform_version
from performance_ui import Columns, configure_window


def resource_help(platform_name):
    if platform_name != 'win32':
        return ''
    return ('这里的主进程运行内存 (RAM)，包含桌宠独占的部分，也包含它使用的共享组件。'
            '任务管理器默认的“内存”列只算独占部分，所以数值会更小。\n\n'
            '“桌宠运行内存 (RAM)”还加上了 FFmpeg 的占用，共享部分未去重。\n\n'
            '要对照，请在任务管理器“详细信息”中找到相同 PID，查看“工作集（内存）”列。'
            '这里每秒更新一次，两边刷新时间不同也会产生差异。')


class FPSGraph(QWidget):
    def __init__(self):
        super().__init__()
        self.values = deque(maxlen=60)
        self.setMinimumHeight(100)
        self.setAccessibleName('最近 60 次 FPS 采样，每秒一次')

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        painter.fillRect(self.rect(), palette.brush(QPalette.ColorRole.Base))
        metrics = self.fontMetrics()
        plot = QRectF(self.rect()).adjusted(12, metrics.height() + 8, -12, -metrics.height() - 8)
        ceiling = max(30, math.ceil(max(self.values, default=0) / 10) * 10)
        painter.setPen(palette.color(QPalette.ColorRole.Mid))
        for step in range(3):
            y = plot.bottom() - plot.height() * step / 2
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
        painter.setPen(palette.color(QPalette.ColorRole.Text))
        painter.drawText(12, metrics.ascent() + 3, f'{ceiling} FPS')
        painter.drawText(12, self.height() - 5, '最近 60 次采样 · 每秒一次')
        path = QPainterPath()
        for index, value in enumerate(self.values):
            point = QPointF(plot.left() + plot.width() * index / 59,
                            plot.bottom() - plot.height() * value / ceiling)
            if index == 0:
                path.moveTo(point)
            else:
                path.lineTo(point)
        painter.setPen(QPen(palette.color(QPalette.ColorRole.Highlight), 2))
        painter.drawPath(path)


class ElidedValue(QLabel):
    """One visible line; QLabel retains the complete accessible text."""
    def __init__(self):
        super().__init__()
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(self.palette().color(QPalette.ColorRole.WindowText))
        text = self.fontMetrics().elidedText(self.text().replace('\n', ' · '),
                                            Qt.TextElideMode.ElideRight, self.width())
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)


class InfoSection(QWidget):
    def __init__(self, title, help_text=''):
        super().__init__()
        self.heading = title
        self.rows = []
        self.labels = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        header = QHBoxLayout()
        name = QLabel(title)
        font = QFont(name.font())
        font.setWeight(QFont.Weight.DemiBold)
        name.setFont(font)
        header.addWidget(name)
        if help_text:
            help_button = QToolButton()
            help_button.setObjectName('resourceHelp')
            help_button.setAutoRaise(True)
            help_button.setText('?')
            help_button.setAccessibleName(title + '说明')
            help_button.setAccessibleDescription(help_text)
            help_button.setToolTip('<qt>' + escape(help_text).replace('\n\n', '<br><br>') + '</qt>')
            help_button.clicked.connect(lambda: QToolTip.showText(
                help_button.mapToGlobal(help_button.rect().bottomLeft()), help_button.toolTip(), help_button))
            header.addWidget(help_button)
        header.addStretch()
        layout.addLayout(header)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(line)
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(6)
        self.grid.setColumnStretch(1, 1)
        layout.addLayout(self.grid)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def set_rows(self, rows, summaries=None):
        self.rows = rows
        if tuple(self.labels) != tuple(name for name, _ in rows):
            while self.grid.count():
                self.grid.takeAt(0).widget().deleteLater()
            self.labels.clear()
            for index, (name, _) in enumerate(rows):
                caption = QLabel(name)
                caption.setMinimumWidth(self.fontMetrics().horizontalAdvance('汉') * 7)
                label = ElidedValue()
                self.labels[name] = label
                self.grid.addWidget(caption, index, 0)
                self.grid.addWidget(label, index, 1)
        for name, value in rows:
            self.labels[name].setText(str((summaries or {}).get(name, value)))
            # Rich-text wrapping handles long paths/names; escaping keeps content literal.
            self.labels[name].setToolTip('<qt>' + escape(str(value)).replace('\n', '<br>') + '</qt>')
            self.labels[name].setAccessibleDescription(str(value))

    def text(self):
        return self.heading + '\n' + '\n'.join(f'{name}：{value}' for name, value in self.rows)

class DiagnosticsWindow(QWidget):
    def __init__(self, pet, root):
        super().__init__(None, Qt.WindowType.Window)
        configure_window(self)
        self.pet = pet
        self.root = root
        self.setWindowTitle('性能统计')
        self.setWindowIcon(pet.windowIcon())
        self.resize(960, 740)
        self.setMinimumSize(440, 360)
        self.changing_pin = False
        self.statistics = ProcessStatistics()
        self.hardware = HardwareProbe(self)
        self.hardware.changed.connect(self.update_identity)
        self.frames = PlaybackStatistics(time.monotonic())
        self.previous = None
        self.decoder_previous = None
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.sample)
        QApplication.instance().aboutToQuit.connect(self.timer.stop)
        QApplication.instance().aboutToQuit.connect(self.hardware.stop)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(16)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        content = QVBoxLayout(body)
        content.setContentsMargins(0, 0, 8, 0)
        content.setSpacing(16)
        metrics = QHBoxLayout()
        self.values = []
        for title, scale in (('FPS', 1.333 ** 2), ('最高', 1.333 ** 2), ('最低', 1.333 ** 2)):
            column = QHBoxLayout()
            column.addWidget(QLabel(title))
            value = QLabel('—')
            font = QFont(self.font())
            font.setPointSizeF(self.font().pointSizeF() * scale)
            font.setWeight(QFont.Weight.Medium)
            value.setFont(font)
            value.setAccessibleName(title)
            column.addWidget(value)
            column.addStretch()
            metrics.addLayout(column, 1)
            self.values.append(value)
        content.addLayout(metrics)
        self.graph = FPSGraph()
        content.addWidget(self.graph)
        self.playback = InfoSection('播放')
        self.resources = InfoSection('资源', resource_help(self.statistics.platform))
        self.identity = InfoSection('硬件与版本')
        self.connections = InfoSection('连接与任务')
        left, right = QWidget(), QWidget()
        for column, sections in ((left, (self.playback, self.resources)),
                                 (right, (self.identity, self.connections))):
            group = QVBoxLayout(column)
            group.setContentsMargins(0, 0, 0, 0)
            group.setSpacing(18)
            for section in sections:
                group.addWidget(section)
            group.addStretch()
        self.columns = Columns(left, right)
        content.addWidget(self.columns)
        self.update_identity()
        content.addStretch()
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        footer = QHBoxLayout()
        pin = QCheckBox('置顶显示')
        pin.setChecked(pet.settings.value('diagnosticsPinned', True, type=bool))
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, pin.isChecked())
        pin.toggled.connect(self.toggle_pin)
        footer.addWidget(pin)
        footer.addStretch()
        buttons = QDialogButtonBox()
        copy = buttons.addButton('复制信息', QDialogButtonBox.ButtonRole.ActionRole)
        copy.clicked.connect(self.copy_information)
        footer.addWidget(buttons)
        outer.addLayout(footer)

    def reveal(self):
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

    def showEvent(self, event):
        super().showEvent(event)
        self.hardware.start()
        if not self.timer.isActive():
            self.previous = self.statistics.read()
            self.decoder_previous = None
            self.frames = PlaybackStatistics(self.previous.at)
            self.graph.values.clear(); self.graph.update()
            self.update_text(self.previous)
            self.timer.start()

    def hideEvent(self, event):
        if not self.changing_pin:
            self.timer.stop()
            self.hardware.stop()
        super().hideEvent(event)

    def closeEvent(self, event):
        self.timer.stop()
        self.hardware.stop()
        super().closeEvent(event)

    def toggle_pin(self, enabled):
        self.pet.settings.setValue('diagnosticsPinned', enabled)
        self.changing_pin = True
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, enabled)
        self.show()
        self.changing_pin = False

    def record(self, frame):
        if self.timer.isActive():
            self.frames.record(frame.cacheKey())

    def sample(self):
        current = self.statistics.read()
        fps, draws = self.frames.sample(current.at)
        self.graph.values.append(fps); self.graph.update()
        elapsed = current.at - self.previous.at
        cpu = gpu = None
        if current.cpu is not None and self.previous.cpu is not None:
            cpu = (current.cpu - self.previous.cpu) / elapsed * 100
        if current.gpu and self.previous.gpu:
            group, nanos = current.gpu
            old_group, old_nanos = self.previous.gpu
            if group == old_group and nanos >= old_nanos:
                gpu = (nanos - old_nanos) / 1e9 / elapsed * 100
            else:
                current.gpu_status = '重新建立采样基线'
        self.update_text(current, fps, draws, cpu, gpu)
        self.previous = current

    def update_text(self, process, fps=None, draws=None, cpu=None, gpu=None):
        def number(value):
            return '—' if value is None else f'{value:.1f}'

        for label, value in zip(self.values, (fps, self.frames.high, self.frames.low)):
            label.setText(number(value))
        pet = self.pet
        item = pet.current or {}
        buffered = pet.stream.statistics()
        count = buffered['count']
        frame = pet.frames[0] if pet.frames else None
        resolution = f'{frame.width()}×{frame.height()}' if frame else '未提供'
        state = '隐藏' if pet.desktop_hidden() else ('解码中' if pet.loading else ('播放' if pet.tick.isActive() else '暂停'))
        source_rate = number(buffered['rate'])
        limit = '满帧' if pet.fps_limit == 'full' else f'{pet.fps_limit} FPS'
        self.playback.set_rows([
            ('当前动作', f'{item.get("name") or item.get("id", "未提供")} · {state}'),
            ('解码分辨率', resolution),
            ('运行帧率', f'{source_rate} FPS · 上限 {limit}'),
            ('动画帧', f'{0 if pet.loading else pet.source_index + 1} / {count if count is not None else "—"}'),
            ('累计帧数', self.frames.total),
            ('绘制频率', f'{number(draws)} / 秒')])
        size, _, frames = frame_cache_statistics(pet)
        cpu_text = (f'{number(cpu / self.statistics.cores if cpu is not None else None)}%（总体）'
                    f' · {number(cpu)}%（单核）')
        if process.cpu_error:
            cpu_text = f'CPU 读取失败：{process.cpu_error}'
        ram = byte_text(process.ram) if not process.memory_error else process.memory_error
        gpu_text = f'{gpu:.2f}%' if gpu is not None else process.gpu_status
        decoder_text, decoder_ram = self.decoder_text(buffered['pid'])
        total_ram = (process.ram + decoder_ram
                     if process.ram is not None and decoder_ram is not None else None)
        resources = [
            ('桌宠运行内存 (RAM)', byte_text(total_ram)),
            ('主进程运行内存 (RAM)', ram),
            ('FFmpeg 运行内存 (RAM)', byte_text(decoder_ram)),
            ('主进程 CPU', cpu_text),
            ('FFmpeg', decoder_text)]
        if self.statistics.mac:
            resources += [('GPU（应用组）', gpu_text),
                          ('压缩运行内存 (RAM)', byte_text(process.compressed))]
        resources.extend(process_paging_rows(process, self.statistics.platform))
        resources.append(('帧缓存估算', f'{byte_text(size)} · {frames} 帧'))
        if buffered['preloadWhole']:
            resources.append(('整段预加载', f'{buffered["buffered"]} / {count if count is not None else "—"} 帧'))
        else:
            resources.append(('动画缓冲', f'{buffered["buffered"]} / {buffered["capacity"]} 帧'))
        resources.append(('常用动作缓存', f'{byte_text(buffered.get("warmBytes",0))} / 24 MiB'))
        resources.append(('缓存命中', buffered.get('cacheHits',0)))
        resources.append(('动画计时间隔', f'{pet.tick.interval()} ms'))
        self.resources.set_rows(resources)
        sync = pet.desktop_sync
        watching = '观察中' if sync.timer.isActive() else '已停止'
        worker = pet.chat.worker if pet.chat else None
        desktop = desktop_status()
        cli = cli_status(pet)
        self.connections.set_rows([
            ('桌面端', desktop),
            ('只读同步', f'{watching} · 执行中 {len(sync.running)} · 已观察 {len(sync.known)}'),
            ('连续读取失败', f'{sync.errors} 次'),
            ('内置 CLI', cli),
            ('额度查询', '执行中' if pet.quota_inflight else '空闲'),
            ('内置任务', '执行中' if worker and worker.isRunning() else '空闲')],
            {'桌面端': desktop_summary(desktop), '内置 CLI': cli.splitlines()[0]})

    def update_identity(self):
        self.identity.set_rows([
            ('版本', platform_version()),
            ('进程', f'{os.path.basename(sys.executable)} · PID {os.getpid()}'),
            ('CPU', f'{self.hardware.cpu.strip()} · {self.statistics.cores} 个逻辑核心'),
            ('GPU', self.hardware.gpu),
            ('系统', platform.platform())], {'GPU': self.hardware.gpu.split('、')[0]})

    def decoder_text(self,pid):
        if pid is None:
            self.decoder_previous=None
            return '未运行', 0
        try:
            decoder=psutil.Process(pid)
            with decoder.oneshot():
                times=decoder.cpu_times()
                ram=(self.statistics.mac.process_footprint(pid) if self.statistics.mac
                     else decoder.memory_info().rss)
            now=time.monotonic();seconds=times.user+times.system
            cpu='等待采样'
            if self.decoder_previous and self.decoder_previous[0]==pid:
                _,before,previous=self.decoder_previous
                cpu=f'{(seconds-previous)/(now-before)*100:.1f}%'
            self.decoder_previous=(pid,now,seconds)
            return f'PID {pid} · CPU {cpu}（单核）', ram
        except psutil.NoSuchProcess:
            self.decoder_previous=None
            return '本次解码已结束', None
        except (psutil.AccessDenied, OSError) as error:
            self.decoder_previous=None
            return f'FFmpeg 统计读取失败：{error}', None

    def copy_information(self):
        values = ' · '.join(f'{title} {label.text()}' for title, label in
                            zip(('FPS', '最高', '最低'), self.values))
        QApplication.clipboard().setText('\n\n'.join([
            self.windowTitle(), values, self.playback.text(), self.resources.text(),
            self.identity.text(), self.connections.text()]))
