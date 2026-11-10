"""Cross-platform performance controls using the system font and palette."""
from PySide6.QtCore import Qt, QRectF, QSignalBlocker
from PySide6.QtGui import QPainter, QPalette
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
                               QComboBox, QLineEdit, QSlider, QCheckBox, QDialogButtonBox,
                               QWidget, QStyle, QStyleOptionFocusRect)
from performance_ui import Columns, configure_window
from performance_preferences import (MIN_BUFFER_FRAMES, MAX_BUFFER_FRAMES,
                                     DEFAULT_RESOLUTION, DEFAULT_BUFFER_FRAMES, DEFAULT_FPS_LIMIT,
                                     PERFORMANCE_PRESETS)


class ToggleSwitch(QCheckBox):
    def __init__(self):
        super().__init__()
        self.setFixedSize(46, 26)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def hitButton(self, position):
        return self.rect().contains(position)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        palette = self.palette()
        painter.setBrush(palette.color(QPalette.ColorRole.Highlight if self.isChecked()
                                       else QPalette.ColorRole.Mid))
        painter.drawRoundedRect(QRectF(3, 3, 40, 20), 10, 10)
        painter.setBrush(Qt.GlobalColor.white)
        painter.drawEllipse(QRectF(25 if self.isChecked() else 5, 5, 16, 16))
        if self.hasFocus():
            option = QStyleOptionFocusRect()
            option.initFrom(self)
            self.style().drawPrimitive(QStyle.PrimitiveElement.PE_FrameFocusRect, option, painter, self)


class PerformanceSettings(QDialog):
    def __init__(self, pet):
        super().__init__(pet, Qt.WindowType.Window)
        configure_window(self)
        self.pet = pet
        self.setWindowTitle('性能设置')
        self.resize(740, 310)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(20)
        presets = QHBoxLayout()
        presets.addWidget(QLabel('性能档位'))
        self.preset = QComboBox()
        self.preset.setAccessibleName('性能档位')
        for label, values in PERFORMANCE_PRESETS:
            self.preset.addItem(label, values)
        self.preset.addItem('自定义', None)
        presets.addWidget(self.preset)
        presets.addStretch()
        layout.addLayout(presets)
        playback = QWidget()
        buffer = QWidget()
        forms = [QFormLayout(group) for group in (playback, buffer)]
        for form in forms:
            form.setContentsMargins(0, 0, 0, 0)
            form.setVerticalSpacing(12)
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.quality = QComboBox()
        for label, value in (('原画 720×720', 720), ('较高 512×512', 512),
                             ('中 384×384', 384), ('低 256×256', 256), ('跟随桌宠大小与屏幕', 0)):
            self.quality.addItem(label, value)
        self.quality.setCurrentIndex(self.quality.findData(pet.resolution))
        self.fps = QComboBox()
        for label, value in (('素材原帧率', 'full'), ('20 FPS', '20'), ('15 FPS', '15')):
            self.fps.addItem(label, value)
        self.fps.setCurrentIndex(self.fps.findData(pet.fps_limit))
        self.capacity = QLineEdit(str(pet.buffer_capacity))
        self.capacity.setFixedWidth(self.fontMetrics().horizontalAdvance('0000') + 16)
        self.capacity.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.capacity.setAccessibleName('输入动画缓冲帧数')
        self.buffer_slider = QSlider(Qt.Orientation.Horizontal)
        self.buffer_slider.setRange(MIN_BUFFER_FRAMES, MAX_BUFFER_FRAMES)
        self.buffer_slider.setSingleStep(1)
        self.buffer_slider.setPageStep(6)
        self.buffer_slider.setTickPosition(QSlider.TickPosition.NoTicks)
        self.buffer_slider.setValue(pet.buffer_capacity)
        self.buffer_slider.setAccessibleName('动画缓冲帧数')
        self.buffer_controls = QWidget()
        controls = QHBoxLayout(self.buffer_controls)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(8)
        controls.addWidget(self.capacity)
        controls.addWidget(QLabel('帧'))
        controls.addWidget(self.buffer_slider, 1)
        self.preload = ToggleSwitch()
        self.preload.setAccessibleName('整段动画预加载（不推荐）')
        self.preload.setChecked(pet.preload_whole)
        self.quality.setAccessibleName('分辨率')
        self.fps.setAccessibleName('运行帧率')
        forms[0].addRow('分辨率', self.quality)
        forms[0].addRow('运行帧率', self.fps)
        forms[1].addRow('预加载帧数（6–240）', self.buffer_controls)
        toggle_row = QHBoxLayout()
        toggle_row.addWidget(self.preload)
        self.preload_state = QLabel()
        toggle_row.addWidget(self.preload_state)
        toggle_row.addStretch()
        forms[1].addRow('整段动画预加载（不推荐）', toggle_row)
        # Match both control rows even when a platform's slider is shorter.
        row_height = max(self.quality.sizeHint().height(), self.fps.sizeHint().height(),
                         self.capacity.sizeHint().height(), self.preload.height())
        for control in (self.quality, self.fps, self.buffer_controls):
            control.setMinimumHeight(row_height)
        toggle_row.setContentsMargins(0, max(0, (row_height - self.preload.height()) // 2), 0, 0)
        self.columns = Columns(playback, buffer)
        layout.addWidget(self.columns)
        layout.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.RestoreDefaults)
        reset = buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults)
        reset.setText('恢复默认')
        reset.setAutoDefault(False)
        reset.clicked.connect(self.reset_defaults)
        layout.addWidget(buttons)
        for before, after in zip((self.quality, self.fps, self.capacity, self.buffer_slider, self.preload),
                                 (self.fps, self.capacity, self.buffer_slider, self.preload, reset)):
            self.setTabOrder(before, after)
        self.quality.currentIndexChanged.connect(self.apply)
        self.fps.currentIndexChanged.connect(self.apply)
        self.capacity.editingFinished.connect(self.commit_capacity)
        self.buffer_slider.valueChanged.connect(self.slider_changed)
        self.preload.toggled.connect(self.apply)
        self.preset.currentIndexChanged.connect(self.apply_preset)
        self.refresh()

    def capacity_value(self):
        try:
            value = int(self.capacity.text().strip())
        except ValueError:
            return DEFAULT_BUFFER_FRAMES
        return value if MIN_BUFFER_FRAMES <= value <= MAX_BUFFER_FRAMES else DEFAULT_BUFFER_FRAMES

    def commit_capacity(self):
        value = self.capacity_value()
        self.capacity.setText(str(value))
        with QSignalBlocker(self.buffer_slider):
            self.buffer_slider.setValue(value)
        self.apply()

    def slider_changed(self, value):
        self.capacity.setText(str(value))
        self.apply()

    def refresh(self):
        self.preload_state.setText('已开启' if self.preload.isChecked() else '已关闭')
        self.buffer_controls.setEnabled(not self.preload.isChecked())
        selected = (self.quality.currentData(), self.buffer_slider.value(),
                    self.fps.currentData(), self.preload.isChecked())
        index = next((i for i, (_, values) in enumerate(PERFORMANCE_PRESETS)
                      if selected == values), len(PERFORMANCE_PRESETS))
        with QSignalBlocker(self.preset):
            self.preset.setCurrentIndex(index)

    def apply_preset(self, index):
        values = self.preset.itemData(index)
        if values is None:
            return
        resolution, capacity, fps, preload = values
        with (QSignalBlocker(self.quality), QSignalBlocker(self.buffer_slider),
              QSignalBlocker(self.fps), QSignalBlocker(self.preload)):
            self.quality.setCurrentIndex(self.quality.findData(resolution))
            self.capacity.setText(str(capacity))
            self.buffer_slider.setValue(capacity)
            self.fps.setCurrentIndex(self.fps.findData(fps))
            self.preload.setChecked(preload)
        self.apply()

    def apply(self):
        selected = (self.quality.currentData(), self.buffer_slider.value(),
                    self.fps.currentData(), self.preload.isChecked())
        saved = (self.pet.resolution, self.pet.buffer_capacity, self.pet.fps_limit, self.pet.preload_whole)
        if selected != saved:
            self.pet.apply_performance(*selected)
        self.refresh()

    def reset_defaults(self):
        # 一次恢复全部设置，避免每个控件的信号分别重启当前动画。
        with (QSignalBlocker(self.quality), QSignalBlocker(self.buffer_slider),
              QSignalBlocker(self.fps), QSignalBlocker(self.preload)):
            self.quality.setCurrentIndex(self.quality.findData(DEFAULT_RESOLUTION))
            self.capacity.setText(str(DEFAULT_BUFFER_FRAMES))
            self.buffer_slider.setValue(DEFAULT_BUFFER_FRAMES)
            self.fps.setCurrentIndex(self.fps.findData(DEFAULT_FPS_LIMIT))
            self.preload.setChecked(False)
        self.apply()
