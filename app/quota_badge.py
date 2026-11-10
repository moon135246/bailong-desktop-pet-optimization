"""Optional compact quota display beside the pet; click to refresh details."""
from datetime import datetime
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel
from performance_ui import readable_font


class QuotaBadge(QLabel):
    clicked = Signal()

    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
                         | Qt.WindowType.NoDropShadowWindowHint
                         | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFont(readable_font(.9))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName('Codex 常驻额度，单击查看详情')
        self.setStyleSheet('QLabel {color:#503768;background:#f5effb;'
                           'border:1px solid #cbb4df;border-radius:12px;padding:5px 9px;}')

    def refresh(self, cache, refreshing=False, error=None):
        cache.validate_account()
        if cache.windows:
            labels = []
            for window in cache.windows[:2]:
                name = window['name'].replace('5小时', '5h').replace('一周', '周')
                value = window['remaining']
                labels.append(name + ' ' + (f'{value:g}%' if value is not None else '—'))
            text = ' · '.join(labels)
            if not cache.fresh():
                text += ' · 缓存'
        else:
            text = '额度刷新中…' if refreshing else '点击查询额度'
        self.setText(text)
        self.adjustSize()
        updated = (datetime.fromtimestamp(cache.updated_at).strftime('%m-%d %H:%M:%S')
                   if cache.updated_at else '尚未查询')
        self.setToolTip('Codex 剩余额度\n更新：' + updated
                        + ('\n正在后台刷新' if refreshing else '')
                        + ('\n刷新失败：' + error if error else '')
                        + '\n单击查看详情')

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)
