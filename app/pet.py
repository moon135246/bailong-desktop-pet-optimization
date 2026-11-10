import json, random, sys, time, threading, os, math
from pathlib import Path
from datetime import datetime

if sys.platform.startswith('linux'):
    os.environ.setdefault('QT_QPA_PLATFORM', 'xcb')
    os.environ.setdefault('QT_IM_MODULE', 'ibus')

from PySide6.QtCore import Qt, QTimer, QThread, Signal, QPoint, QPointF, QRect, QRectF, QSize, QSettings, QEvent
from PySide6.QtGui import QImage, QPixmap, QPainter, QRegion, QCursor, QIcon, QTransform
from PySide6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QProgressBar, QMenu, QMessageBox, QPushButton, QSystemTrayIcon, QTextBrowser, QSlider, QDialog, QCheckBox
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from quota import read_quota, quota_windows
from version import VERSION, BASE_VERSION, BRANCH, platform_version
from movement import plan_movement, movement_fraction
from frame_buffer import FrameBuffer
from clip_transition import ClipTransition
from performance_preferences import read_performance_preferences, decode_size, fps_cap
from quota_cache import QuotaCache, QUOTA_REFRESH_INTERVAL_MS, QUOTA_RETRY_SECONDS
from quota_badge import QuotaBadge
from performance_ui import readable_font, configure_linux_dialog

from platform_support import resource_root,state_root,user_data,configure_mac_window
ROOT=resource_root()
STATE_ROOT=state_root()
ASSETS=ROOT/'outputs/白龙桌宠素材'
FLAGS=Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.Tool

def clamp_position(position,size,area):
    """Keep the full pet window inside one monitor's usable rectangle."""
    max_x=max(area.left(),area.right()-size.width()+1)
    max_y=max(area.top(),area.bottom()-size.height()+1)
    return QPoint(max(area.left(),min(position.x(),max_x)),
                  max(area.top(),min(position.y(),max_y)))

class QuotaWorker(QThread):
    ready=Signal(object)
    failed=Signal(str)
    def __init__(self,parent=None):
        super().__init__(parent);self.cancel=threading.Event()
    def run(self):
        try: self.ready.emit(quota_windows(read_quota(cancel=self.cancel)))
        except Exception as error: self.failed.emit(str(error))

class Bubble(QWidget):
    dismiss_requested=Signal()
    def __init__(self):
        super().__init__(None, FLAGS)
        self.setFont(readable_font())
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.scale_percent=100;self.base_width=256;self.is_task_bubble=False;self.is_size_preview=False
        self.layout=QVBoxLayout(self); self.layout.setContentsMargins(13,10,13,10);self.layout.setSpacing(5)
        self.setFixedWidth(256)
        self.setStyleSheet('QLabel {color:#332644;} QProgressBar {background:#eee8f5;border:1px solid #c8b5dc;border-radius:7px;height:14px;} QProgressBar::chunk {background:#a47bc9;border-radius:6px;}')
        self.close_button=QPushButton('×',self);self.close_button.setFixedSize(24,24)
        self.close_button.setToolTip('关闭气泡')
        self.close_button.setStyleSheet('QPushButton {color:#776783;background:transparent;border:0;border-radius:10px;} QPushButton:hover {background:#eee5f7;color:#503768;}')
        self.close_button.clicked.connect(self.hide)
        self.close_button.clicked.connect(lambda:self.dismiss_requested.emit())
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'close_button'):
            self.close_button.move(self.width()-self.close_button.width()-5,5);self.close_button.raise_()
    def set_scale_percent(self,value):
        self.scale_percent=max(50,min(150,int(value)));s=self.scale_percent/100
        self.setFont(readable_font(s))
        for widget in self.findChildren(QWidget):
            widget.setFont(self.font())
        self.setFixedWidth(round(self.base_width*s))
        self.layout.setContentsMargins(round(13*s),round(10*s),round(13*s),round(10*s));self.layout.setSpacing(max(2,round(5*s)))
        self.setStyleSheet(f'QLabel {{color:#332644;}} QProgressBar {{background:#eee8f5;border:1px solid #c8b5dc;border-radius:5px;height:{round(14*s)}px;}} QProgressBar::chunk {{background:#a47bc9;border-radius:5px;}}')
        for view in self.findChildren(QTextBrowser):
            view.document().setDefaultFont(self.font())
            if self.is_size_preview:view.setFixedHeight(round(110*s))
            view.setStyleSheet('QTextBrowser {color:#332644;background:transparent;border:0;}')
        close_font=readable_font(s);close_font.setPointSizeF(close_font.pointSizeF()*1.333)
        self.close_button.setFont(close_font)
        close_size=max(round(24*s),self.close_button.fontMetrics().horizontalAdvance('×')+6)
        self.close_button.setFixedSize(close_size,close_size)
        if self.layout.count() and isinstance(self.layout.itemAt(0).widget(),QLabel):
            self.layout.itemAt(0).widget().setContentsMargins(0,0,self.close_button.width()+4,0)
        for button in self.findChildren(QPushButton):
            if button is not self.close_button:
                button.setStyleSheet(f'color:#60358c;background:#eee5f7;border:0;border-radius:7px;padding:{max(3,round(7*s))}px;')
        self.close_button.setStyleSheet('QPushButton {color:#776783;background:transparent;border:0;border-radius:8px;} QPushButton:hover {background:#eee5f7;color:#503768;}')
        for index in range(self.layout.count()):
            self.layout.itemAt(index).widget().show()
        self.fit_content()
    def fit_content(self):
        self.ensurePolished()
        self.layout.invalidate()
        self.layout.activate()
        if self.is_task_bubble:
            view=self.result_view;document=view.document()
            # 按无滚动条时的可用宽度测量，长内容变短后也能收回原有空白。
            document.setTextWidth(view.maximumViewportSize().width())
            content_height=math.ceil(document.size().height())+2*view.frameWidth()
            view.setFixedHeight(min(round(150*self.scale_percent/100),content_height))
            # 先更新布局最小高度，再缩小窗口，避免被上一条内容的高度限制。
            self.layout.invalidate();self.layout.activate()
        height=self.layout.totalHeightForWidth(self.width()) if self.layout.hasHeightForWidth() else self.layout.sizeHint().height()
        self.resize(self.width(),height)
        self.layout.activate()
        self.close_button.move(self.width()-self.close_button.width()-5,5);self.close_button.raise_()
    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(Qt.GlobalColor.white);painter.setPen(Qt.GlobalColor.transparent)
        painter.drawRoundedRect(self.rect(),16,16)
    def clear(self):
        while self.layout.count():
            widget=self.layout.takeAt(0).widget();widget.hide();widget.setParent(None);widget.deleteLater()
    def label(self,text):
        label=QLabel(text);label.setWordWrap(True);label.setTextFormat(Qt.TextFormat.PlainText)
        if not self.layout.count():label.setContentsMargins(0,0,20,0)
        self.layout.addWidget(label)
    def message(self,text):
        self.is_size_preview=False
        self.is_task_bubble=False
        self.is_task_progress=False
        self.is_quota_result=False
        self.base_width=256;self.setFixedWidth(round(256*self.scale_percent/100))
        self.clear();self.label(text);self.set_scale_percent(self.scale_percent);self.show()
    def task_result(self,title,text,details):
        self.is_size_preview=False
        self.is_task_bubble=True
        self.is_task_progress=False
        self.is_quota_result=True
        self.base_width=300;self.setFixedWidth(round(300*self.scale_percent/100))
        self.clear();self.label(title)
        self.result_title=self.layout.itemAt(0).widget()
        result=QTextBrowser();result.setPlainText(text);result.setOpenLinks(False)
        result.setStyleSheet('QTextBrowser {color:#332644;background:transparent;border:0;}')
        self.result_view=result
        self.layout.addWidget(result)
        button=QPushButton('详情');button.setStyleSheet('color:#60358c;background:#eee5f7;border:0;border-radius:7px;padding:7px;')
        button.clicked.connect(lambda checked=False:details());self.layout.addWidget(button)
        self.set_scale_percent(self.scale_percent);self.show()
    def quota(self,windows,updated_at=None,refreshing=False,error=None):
        self.is_size_preview=False
        self.is_task_bubble=False
        self.is_task_progress=False
        self.is_quota_result=True
        self.base_width=256;self.setFixedWidth(round(256*self.scale_percent/100))
        self.clear();self.label('Codex 剩余额度')
        for window in windows:
            value=window['remaining']
            self.label(window['name']+' · '+(f'剩余 {value:g}%' if value is not None else '暂未提供'))
            bar=QProgressBar();bar.setRange(0,100)
            bar.setValue(round(value) if value is not None else 0);bar.setTextVisible(False);self.layout.addWidget(bar)
            if window['resetsAt']:
                self.label('重置：'+datetime.fromtimestamp(window['resetsAt']).strftime('%m月%d日 %H:%M'))
        if updated_at:
            self.label('更新：'+datetime.fromtimestamp(updated_at).strftime('%m-%d %H:%M:%S'))
        if refreshing:self.label('正在后台刷新…')
        elif error:self.label('刷新失败，显示上次记录。\n'+error)
        self.set_scale_percent(self.scale_percent);self.show()

    def size_preview(self):
        self.clear();self.is_size_preview=True;self.is_task_bubble=False
        self.is_task_progress=False;self.is_quota_result=True;self.base_width=300
        blank=QTextBrowser()
        self.layout.addWidget(blank);self.set_scale_percent(self.scale_percent);self.show()

class Pet(QWidget):
    def __init__(self):
        # 角色沿用原素材透明边缘，不叠加桌面系统的窗口阴影。
        super().__init__(None,FLAGS|Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle('白龙桌宠');self.setFixedSize(256,256)
        self.manifest=json.loads((ASSETS/'素材清单.json').read_text(encoding='utf-8'))
        self.variants=[v for v in self.manifest['variants'] if self.asset_path(v).is_file()]
        self.idles=[self.manifest['idle']]+self.manifest.get('additionalIdleAnimations',[])[:1]
        self.extra_idles=[v for v in self.manifest.get('additionalIdleAnimations',[]) if v.get('id') in ('idle03','idle04','idle05','idle06') and self.asset_path(v).is_file()]
        self.next_leisure_group='idle';self.next_leisure_at=time.monotonic()+15.0
        self.frames=[];self.current=None;self.mode='idle';self.index=0
        self.source_index=0;self.display_item=None;self.reference_frame=None;self.loading=False
        self.stream=FrameBuffer()
        QApplication.instance().aboutToQuit.connect(self.stream.close)
        self.transition=None
        self.bubble=Bubble();self.generation=0;self.worker=None;self.quota_inflight=False;self.dragging=False;self.last_click=None
        self.bubble.dismiss_requested.connect(self.dismiss_bubble)
        self.chat=None
        self.diagnostics=None
        self.task_active=False
        self.manual_hidden=False;self.fullscreen_hidden=False;self.hidden_since=None
        self.settings=QSettings('BailongPet','DesktopPet')
        self.smooth_switch_enabled=self.settings.value('smoothSwitchEnabled',True,type=bool)
        self.natural_switch=False
        self.resolution,self.buffer_capacity,self.fps_limit,self.preload_whole=read_performance_preferences(self.settings)
        self.bubble_percent=max(50,min(150,self.settings.value('bubblePercent',100,type=int)))
        self.task_bubbles_disabled=self.settings.value('taskBubblesDisabled',False,type=bool)
        self.sound_disabled=self.settings.value('soundDisabled',False,type=bool)
        self.bubble.set_scale_percent(self.bubble_percent)
        self.size_percent=max(50,min(200,self.settings.value('sizePercent',100,type=int)))
        pixels=round(256*self.size_percent/100);self.setFixedSize(pixels,pixels)
        self.frame_size=self.desired_decode_size()
        self.resolution_timer=QTimer(self);self.resolution_timer.setSingleShot(True)
        self.resolution_timer.setInterval(120);self.resolution_timer.timeout.connect(self.refresh_decode_size)
        self.quota_cache=QuotaCache(user_data()/'quota-cache.json')
        self.quota_error=None;self.quota_bubble_requested=False;self.quota_generation=-1
        self.last_quota_attempt=float('-inf');self.quota_request_account=None
        self.quota_badge_enabled=self.settings.value('quotaBadgeEnabled',False,type=bool)
        self.quota_badge=QuotaBadge();self.quota_badge.clicked.connect(self.quota)
        self.quota_timer=QTimer(self);self.quota_timer.setInterval(QUOTA_REFRESH_INTERVAL_MS)
        self.quota_timer.timeout.connect(self.background_quota_refresh);self.quota_timer.start()
        self.auto_hide_fullscreen=self.settings.value('autoHideFullscreen',True,type=bool)
        self.auto_movement_disabled=self.settings.value('autoMovementDisabled',False,type=bool)
        self.dock_edge=None
        self.work_slots=self.manifest.get('workAnimations',[])[:6]
        self.movement_slots=[v for v in self.manifest.get('movementAnimations',[]) if v and self.asset_path(v).is_file()]
        self.common_animations=self.idles+[self.manifest[name] for name in
            ('dragAnimation','landingAnimation','quotaAnimation') if self.manifest.get(name)]
        self.stream.set_common_paths(self.asset_path(item) for item in self.common_animations)
        self.movement_plan=None;self.movement_mirrored=False;self.pointer_down=False
        self.last_interaction=time.monotonic();self.movement_ready_at=0.0
        self.click_timer=QTimer(self);self.click_timer.setTimerType(Qt.TimerType.PreciseTimer);self.click_timer.setSingleShot(True);self.click_timer.setInterval(250);self.click_timer.timeout.connect(self.single_click)
        self.dock_click_timer=QTimer(self);self.dock_click_timer.setSingleShot(True)
        self.dock_click_timer.setTimerType(Qt.TimerType.PreciseTimer);self.dock_click_timer.setInterval(250)
        self.dock_click_timer.timeout.connect(self.begin_undock)
        self.dock_double_click=False
        self.bubble_timer=QTimer(self);self.bubble_timer.setSingleShot(True);self.bubble_timer.timeout.connect(self.dismiss_bubble)
        self.tick=QTimer(self);self.tick.setTimerType(Qt.TimerType.PreciseTimer);self.tick.setInterval(16);self.tick.timeout.connect(self.animate)
        area=QApplication.primaryScreen().availableGeometry()
        self.move(self.constrained_position(QPoint(area.right()-360,area.bottom()-340)))
        for screen in QApplication.screens():self.watch_screen(screen)
        QApplication.instance().screenAdded.connect(self.watch_screen)
        QApplication.instance().screenRemoved.connect(lambda screen:QTimer.singleShot(0,self.ensure_on_screen))
        self.play(self.idles[0],'idle')
        self.transition=None
        self.started=time.monotonic();self.tick.start()
        self.last_interaction=self.started
        self.next_leisure_at=self.started+15.0
        QApplication.instance().installEventFilter(self)
        self.setup_tray()
        from desktop_visibility import FullscreenDetector
        self.fullscreen_detector=FullscreenDetector()
        self.fullscreen_candidate=False;self.fullscreen_candidate_since=time.monotonic()
        self.visibility_timer=QTimer(self);self.visibility_timer.setInterval(500)
        self.visibility_timer.timeout.connect(self.check_fullscreen)
        if QApplication.platformName()!='offscreen':self.visibility_timer.start()
        from desktop_task_sync import DesktopTaskSync
        self.desktop_sync=DesktopTaskSync(self)
        if QApplication.platformName()!='offscreen':QTimer.singleShot(1500,self.desktop_sync.start)
        QTimer.singleShot(0,self.bind_window_screen)
        QTimer.singleShot(600,self.prepare_common_animations)
        if self.quota_badge_enabled:QTimer.singleShot(1800,self.background_quota_refresh)
    def setup_tray(self):
        # Use the default idle's first frame, independent of the current action.
        icon=QIcon(self.reference_frame) if self.reference_frame else QIcon()
        self.setWindowIcon(icon)
        self.tray=QSystemTrayIcon(icon,self);self.tray.setToolTip('GPT白龙娘桌宠')
        self.tray_menu=self.context_menu();self.tray.setContextMenu(self.tray_menu)
        self.tray_menu.aboutToShow.connect(self.refresh_tray_menu)
        self.tray.activated.connect(self.tray_activated)
        if self.reference_frame and QSystemTrayIcon.isSystemTrayAvailable():self.tray.show()
    def refresh_tray_menu(self):
        self.note_interaction(cancel_movement=False)
        # Rebuild through the same factory used by the pet's right-click menu.
        fresh=self.context_menu()
        self.tray_menu.clear()
        # Keep submenu/action owners alive until the next refresh.
        previous=getattr(self,'tray_menu_contents',None)
        self.tray_menu_contents=fresh
        for action in fresh.actions():self.tray_menu.addAction(action)
        if previous:previous.deleteLater()
    def tray_activated(self,reason):
        self.note_interaction(cancel_movement=False)
        if reason==QSystemTrayIcon.ActivationReason.DoubleClick:self.set_manual_hidden(False)
    def eventFilter(self,obj,event):
        if obj is self and event.type()==QEvent.Type.DevicePixelRatioChange:
            self.schedule_resolution_update()
        if event.type() in (QEvent.Type.MouseButtonPress,QEvent.Type.MouseButtonRelease,
                            QEvent.Type.MouseMove,QEvent.Type.KeyPress,QEvent.Type.Wheel):
            roots=[self,self.bubble]
            if self.chat:roots.extend((self.chat.composer,self.chat.window))
            owned=isinstance(obj,QWidget) and any(obj is root or root.isAncestorOf(obj) for root in roots)
            if owned:self.note_interaction(cancel_movement=False)
        return super().eventFilter(obj,event)
    def note_interaction(self,cancel_movement=True):
        self.last_interaction=time.monotonic()
        self.next_leisure_at=self.last_interaction+15.0;self.next_leisure_group='idle'
        if cancel_movement and self.mode=='movement':
            self.finish_movement()
            self.play(self.idles[0],'idle')
    def finish_movement(self):
        if self.movement_plan is not None:
            self.movement_ready_at=time.monotonic()+10.0
        self.movement_plan=None;self.movement_mirrored=False
    def movement_allowed(self,now=None):
        now=time.monotonic() if now is None else now
        return (not self.dock_edge and not self.auto_movement_disabled and bool(self.movement_slots) and now-self.last_interaction>=15.0
                and now>=self.movement_ready_at and not self.desktop_hidden()
                and not self.task_active and not self.quota_inflight and not self.dragging
                and not self.pointer_down and not self.click_timer.isActive()
                  and not (getattr(self,'size_dialog',None) and self.size_dialog.isVisible())
                  and not (getattr(self,'bubble_settings_dialog',None) and self.bubble_settings_dialog.isVisible())
                and QApplication.activePopupWidget() is None)
    def start_movement(self,item,manual=False):
        if self.desktop_hidden() or (self.task_active and not manual) or self.dragging:return False
        if manual:self.undock()
        if manual:
            self.note_interaction();self.click_timer.stop();self.last_click=None
        if not manual and time.monotonic()<self.movement_ready_at:return False
        self.ensure_on_screen()
        screen=QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
        area=screen.availableGeometry();left=area.left();right=area.right()-self.width()+1
        bottom=area.bottom()-self.height()+1
        if self.chat and self.chat.enabled:
            shift=max(0,(self.chat.composer.width()-self.width())//2)
            left+=shift;right-=shift;bottom-=8+self.chat.composer.height()
        if right<left or bottom<area.top():return False
        origin=self.pos()
        facing=item.get('sourceFacing','right')
        directions=(-1,) if facing=='left' else (1,)
        run_ms=item.get('moveStopMs',5583)-item.get('moveStartMs',3000)
        speed=item.get('movementSpeed',.5 if item.get('number')=='01' else 1.0)
        route=plan_movement((origin.x(),origin.y()),(left,area.top(),right,bottom),self.width(),allowed_directions=directions,distance_scale=max(.25,run_ms/2583)*speed,angle_range=item.get('movementAngleRange'),downward_angle_range=[45,65] if item.get('movementAngleRange') else None)
        if route is None:
            if not manual:return False
            # Still allow a manual preview at an edge, without moving outwards.
            route=((origin.x(),origin.y()),False)
        self.play(item,'movement')
        target,_=route
        self.movement_plan=(origin,QPoint(round(target[0]),round(target[1])))
        self.movement_mirrored=False
        self.generation+=1;self.bubble_timer.stop();self.bubble.hide()
        return True
    def advance_movement(self,elapsed):
        if self.movement_plan is None:return
        origin,target=self.movement_plan
        fraction=movement_fraction(elapsed*1000,self.current.get('moveStartMs',0),
                                   self.current.get('moveStopMs',self.current['durationMs']))
        position=QPoint(round(origin.x()+(target.x()-origin.x())*fraction),
                        round(origin.y()+(target.y()-origin.y())*fraction))
        self.move(self.constrained_position(position))
        if self.bubble.isVisible():self.position_bubble()
    def desktop_hidden(self):
        return self.manual_hidden or self.fullscreen_hidden
    def dialogue_hidden(self):
        return self.desktop_hidden()
    def speech_hidden(self):
        return self.desktop_hidden() or (self.mode=='working' and self.current and self.current.get('id','').startswith('work'))
    def sync_dialogue_visibility(self):
        if self.speech_hidden() and not getattr(self.bubble,'is_task_progress',False) and not self.bubble.is_size_preview and self.bubble.isVisible():self.bubble.hide()
        if self.dialogue_hidden():
            if self.bubble.isVisible():self.bubble.hide()
            if self.chat and self.chat.composer.isVisible():self.chat.composer.hide()
        elif self.chat and self.chat.enabled:
            if not self.chat.composer.isVisible():
                self.chat.composer.show();self.chat.position()
    def set_auto_hide_fullscreen(self,enabled):
        self.note_interaction()
        self.auto_hide_fullscreen=enabled
        self.settings.setValue('autoHideFullscreen',enabled)
        if not enabled:self.fullscreen_hidden=False;self.apply_visibility()
        self.fullscreen_candidate=False;self.fullscreen_candidate_since=time.monotonic()
    def set_auto_movement_disabled(self,disabled):
        self.note_interaction()
        self.auto_movement_disabled=disabled
        self.settings.setValue('autoMovementDisabled',disabled)
    def set_manual_hidden(self,hidden):
        self.note_interaction()
        if hidden and not self.tray.isVisible():
            self.say('主人，托盘暂时没准备好，我先留在这里陪你。');return
        self.manual_hidden=hidden;self.apply_visibility()
    def apply_visibility(self):
        self.stream.pause(self.desktop_hidden())
        if self.desktop_hidden():
            self.transition=None
            if self.hidden_since is None:self.hidden_since=time.monotonic()
            self.dock_click_timer.stop()
            self.tick.stop();self.click_timer.stop();self.last_click=None;self.dragging=False
            self.pointer_down=False
            self.hide();self.bubble.hide()
            if self.chat:self.chat.composer.hide()
        else:
            if self.hidden_since is not None:
                self.started+=time.monotonic()-self.hidden_since;self.hidden_since=None
            self.ensure_on_screen();self.show();self.tick.start()
            self.sync_dialogue_visibility()
        self.update_quota_badge()
        if hasattr(self,'tray'):
            state='已隐藏' if self.manual_hidden else ('全屏时自动隐藏' if self.fullscreen_hidden else '正在陪伴主人')
            self.tray.setToolTip('GPT白龙娘桌宠 · '+state)
    def check_fullscreen(self):
        if self.tray_menu.isVisible():return
        state=self.auto_hide_fullscreen and self.fullscreen_detector.active();now=time.monotonic()
        if state!=self.fullscreen_candidate:
            self.fullscreen_candidate=state;self.fullscreen_candidate_since=now
        # Hide promptly; wait longer before restoring to avoid focus-change flicker.
        if state!=self.fullscreen_hidden and now-self.fullscreen_candidate_since>=(.25 if state else .75):
            self.fullscreen_hidden=state;self.apply_visibility()
        if self.desktop_hidden():
            self.bubble.hide()
            if self.chat:self.chat.composer.hide()
        self.sync_dialogue_visibility()
    def constrained_position(self,position,pointer=None):
        screens=QApplication.screens()
        # Allow crossing monitors, but never use their bounding union: it can
        # contain empty gaps or permit half the pet to hang off a monitor.
        screen=QApplication.screenAt(pointer) if pointer is not None else None
        def constrain(area):
            if self.chat and self.chat.enabled:
                width=max(self.width(),self.chat.composer.width());shift=(width-self.width())//2
                size=QSize(width,self.height()+8+self.chat.composer.height())
                return clamp_position(position-QPoint(shift,0),size,area)+QPoint(shift,0)
            return clamp_position(position,self.size(),area)
        if screen:return constrain(screen.availableGeometry())
        candidates=[constrain(s.availableGeometry()) for s in screens]
        return min(candidates,key=lambda p:(p.x()-position.x())**2+(p.y()-position.y())**2) if candidates else position
    def dock_rect(self):
        size=112;w=self.width();h=self.height()
        return QRectF({'left':0,'right':w-size}.get(self.dock_edge,(w-size)//2),
                      {'top':0,'bottom':h-size}.get(self.dock_edge,(h-size)//2),size,size)
    def try_dock(self):
        if self.chat and self.chat.enabled:return False
        screen=QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
        area=screen.availableGeometry();p=self.pos()
        gaps={'left':abs(p.x()-area.left()),'right':abs(area.right()+1-p.x()-self.width())}
        edge=min(gaps,key=gaps.get)
        if gaps[edge]>24:return False
        self.finish_movement();self.dock_edge=edge
        self.dock_started=time.monotonic()
        if edge=='left':p.setX(area.left())
        elif edge=='right':p.setX(area.right()+1-self.width())
        self.move(p);self.bubble_timer.stop();self.bubble.hide()
        self.play(self.idles[0],'idle');return True
    def undock(self):
        if not self.dock_edge:return
        self.dock_click_timer.stop()
        self.dock_exit=None
        self.dock_edge=None;self.last_interaction=time.monotonic();self.update()
    def begin_undock(self):
        self.dock_click_timer.stop()
        if not self.dock_edge or getattr(self,'dock_exit',None):return
        elapsed=min(1,max(0,(time.monotonic()-self.dock_started)/.3))
        self.dock_exit=(time.monotonic(),1-(1-elapsed)**3)
        self.click_timer.stop();self.last_click=None;self.last_interaction=time.monotonic()
        self.update()
    def watch_screen(self,screen):
        screen.availableGeometryChanged.connect(lambda area:self.ensure_on_screen())
        screen.logicalDotsPerInchChanged.connect(lambda dpi:self.schedule_resolution_update())
        QTimer.singleShot(0,self.ensure_on_screen)
    def bind_window_screen(self):
        window=self.windowHandle()
        if window and not getattr(self,'window_screen_bound',False):
            window.screenChanged.connect(lambda screen:self.schedule_resolution_update())
            self.window_screen_bound=True
        self.schedule_resolution_update()
    def desired_decode_size(self):
        screen=QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
        window=self.windowHandle()
        ratio=(window.devicePixelRatio() if window and window.screen() is screen else screen.devicePixelRatio())
        return decode_size(self.resolution,ratio,self.width())
    def schedule_resolution_update(self):
        if hasattr(self,'resolution_timer') and self.resolution==0:
            self.resolution_timer.start()
    def refresh_decode_size(self):
        size=self.desired_decode_size()
        if size==self.frame_size:return
        self.frame_size=size;self.stream.clear_other_sizes(size)
        if self.current:
            route=self.movement_plan
            self.play(self.current,self.mode)
            if route:self.movement_plan=(QPoint(self.pos()),route[1])
        self.prepare_common_animations()
    def prepare_common_animations(self):
        for item in self.common_animations:
            self.stream.prepare(self.asset_path(item),self.frame_size,item['durationMs']/1000,
                                fps=fps_cap(self.fps_limit))
    def ensure_on_screen(self):
        position=self.constrained_position(self.pos())
        if position!=self.pos():
            if self.mode=='movement':self.finish_movement();self.play(self.idles[0],'idle')
            self.move(position)
            if self.dragging:self.origin=self.pos();self.press_pos=QCursor.pos()
        if self.bubble.isVisible():self.position_bubble()
        if self.chat:self.chat.position()
    def moveEvent(self,event):
        super().moveEvent(event)
        if getattr(self,'chat',None):self.chat.position()
        self.schedule_resolution_update()
        if hasattr(self,'quota_badge'):self.position_quota_badge()
    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.schedule_resolution_update()
        if hasattr(self,'quota_badge'):self.position_quota_badge()
    def asset_path(self,item):
        # Optional playbackFile allows future formats without changing the manifest's video source.
        return ASSETS/(item.get('playbackFile') or item['file'].replace('.webm','.webp'))
    def play(self,item,mode):
        if self.dock_edge and mode!='idle':return
        previous=None
        if (self.natural_switch and self.smooth_switch_enabled and self.frames
                and not self.dock_edge and not self.desktop_hidden()
                and self.mode not in ('movement','drag') and mode not in ('movement','drag','landing','quota')):
            previous=self.snapshot_frame().toImage()
        if self.movement_plan is not None:self.finish_movement()
        self.current=item;self.mode=mode;self.source_index=0;self.loading=True
        self.stream.play(self.asset_path(item),self.frame_size,item['durationMs']/1000,self.buffer_capacity,
                         fps=fps_cap(self.fps_limit),preload_whole=self.preload_whole)
        self.started=time.monotonic()
        self.update_tick_interval()
        if not self.desktop_hidden():self.tick.start()
        if getattr(self,'hidden_since',None) is not None:self.hidden_since=self.started
        self.transition=ClipTransition(previous) if previous is not None else None
        self.sync_dialogue_visibility()
        # Keep the return-to-idle and drag-to-landing paths ready ahead of a switch.
        upcoming=self.manifest.get('landingAnimation') if mode=='drag' else self.idles[0]
        if upcoming:self.stream.prepare(self.asset_path(upcoming),self.frame_size,
            upcoming['durationMs']/1000,fps=fps_cap(self.fps_limit))
    def idle(self):
        if self.dock_edge:
            self.play(random.choices(self.idles,weights=[7,3][:len(self.idles)])[0],'idle')
            return
        if self.task_active:
            work=self.regular_work_animations()
            previous=self.current.get('id') if self.current else None
            groups=[('working',work),('idle',self.idles)] if work else [('idle',self.idles)]
            candidates=[(mode,[v for v in pool if v['id']!=previous]) for mode,pool in groups]
            candidates=[g for g in candidates if g[1]]
            if not candidates:return
            mode,pool=random.choices(candidates,weights=[35 if mode=='working' else 65 for mode,pool in candidates])[0]
            self.last_task_group=mode
            self.play(random.choice(pool),mode)
            return
        if self.try_leisure():return
        item=random.choices(self.idles,weights=[4,1][:len(self.idles)])[0]
        self.play(item,'idle')
    def try_leisure(self):
        now=time.monotonic()
        if (now<self.next_leisure_at or now-self.last_interaction<15 or self.dock_edge
                or self.desktop_hidden() or self.task_active or self.quota_inflight or self.dragging
                or self.pointer_down or self.click_timer.isActive() or QApplication.activePopupWidget() is not None
                or any(getattr(self,n,None) and getattr(self,n).isVisible() for n in ('size_dialog','bubble_settings_dialog'))):return False
        if self.next_leisure_group=='movement' and self.movement_allowed(now):
            candidates=random.sample(self.movement_slots,len(self.movement_slots))
            for item in candidates:
                if self.start_movement(item):
                    self.next_leisure_group='idle';self.next_leisure_at=now+15;return True
        if self.extra_idles:
            self.play(random.choice(self.extra_idles),'leisure')
            self.next_leisure_group='movement' if not self.auto_movement_disabled else 'idle'
            self.next_leisure_at=now+15;return True
        return False
    def regular_work_animations(self):
        return [v for v in self.work_slots if v and v['id']!='work01' and self.asset_path(v).is_file()]
    def task_started(self):
        self.note_interaction()
        self.task_active=True
        self.last_task_group=None
        self.click_timer.stop();self.last_click=None
        work=[v for v in self.work_slots if v and self.asset_path(v).is_file()]
        opening=next((v for v in work if v['id']=='work01'),None)
        if opening and not self.dock_edge:self.play(opening,'work-start')
        else:self.idle()
    def task_finished(self):
        self.task_active=False
        if self.mode in ('work-start','working','idle'):
            self.natural_switch=True
            try:self.idle()
            finally:self.natural_switch=False
    def return_transition_item(self,item):
        transition=item['returnTransition']
        return {'id':'return-'+item['id'],'file':transition['file'],
                'durationMs':transition['durationMs'],'renderScale':1.0,'renderOffset':[0,0]}
    def update_frame(self):
        # Windows layered windows use per-pixel alpha. A binary mask would
        # dither the soft character edges and damage transparent rendering.
        self.update()
    def update_tick_interval(self):
        now=time.monotonic()
        smooth=(self.mode=='movement' or self.dragging or bool(getattr(self,'dock_exit',None))
                or bool(self.dock_edge and now-getattr(self,'dock_started',0)<.3)
                or bool(self.transition and self.transition.started is not None))
        rate=self.stream.rate
        interval=16 if self.loading or smooth or not rate else max(8,round(1000/rate))
        if self.tick.interval()!=interval:self.tick.setInterval(interval)
    def animate(self):
        # Edge motion remains responsive while a new clip's first frame loads.
        if getattr(self,'dock_exit',None) and time.monotonic()-self.dock_exit[0]>=.3:
            self.undock();self.idle()
        docking=bool(self.dock_edge and (getattr(self,'dock_exit',None)
                     or time.monotonic()-getattr(self,'dock_started',0)<.3))
        if docking or getattr(self,'was_docking',False):self.update()
        self.was_docking=docking
        self.update_tick_interval()
        elapsed=0 if self.loading else time.monotonic()-self.started
        try:frame=self.stream.take(elapsed)
        except RuntimeError as error:
            self.tick.stop()
            if self.reference_frame:self.say('动画加载失败：'+str(error),0)
            else:QMessageBox.critical(self,'动画加载失败',str(error))
            return
        if frame is not None:
            source_index,_,raw=frame
            image=QImage(raw,self.frame_size,self.frame_size,self.frame_size*4,QImage.Format.Format_RGBA8888)
            self.frames=[QPixmap.fromImage(image)];self.index=0;self.source_index=source_index
            self.display_item=self.current
            if self.reference_frame is None:
                self.reference_frame=self.frames[0]
                icon=QIcon(self.reference_frame)
                QApplication.setWindowIcon(icon)
                self.setWindowIcon(icon);self.tray.setIcon(icon)
                if QSystemTrayIcon.isSystemTrayAvailable():self.tray.show()
            if self.loading:
                self.loading=False;self.started=time.monotonic()
                if self.transition and not self.transition.begin(self.sprite_image(),self.started):
                    self.transition=None
            self.update_tick_interval()
            self.update_frame()
        if self.loading:return
        duration=self.current.get('durationMs',4000)/1000
        elapsed=time.monotonic()-self.started
        # Automatic actions are selected by idle() only at clip boundaries.
        # Reaching the inactivity deadline must not cut an idle clip short.
        if self.mode=='movement':self.advance_movement(elapsed)
        if elapsed>=duration:
            self.natural_switch=True
            try:
                if self.mode=='movement':self.finish_movement()
                if self.mode=='drag':self.play(self.manifest.get('dragAnimation') or self.idles[0],'drag')
                elif self.mode=='work-start' and self.task_active:
                    work=self.regular_work_animations()
                    if work:
                        self.last_task_group='working';self.play(random.choice(work),'working')
                    else:self.idle()
                elif self.mode=='variant' and self.current.get('returnTransition'):
                    self.play(self.return_transition_item(self.current),'return-idle')
                elif self.mode=='return-idle':self.play(self.idles[0],'idle')
                else:self.idle()
            finally:self.natural_switch=False
            return
        if self.transition:
            if self.transition.finished(time.monotonic()):
                self.transition=None;self.update_tick_interval()
            self.update()
    def paintEvent(self,event):
        if self.frames:
            painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            self.draw_frame(painter,QRectF(self.rect()))
            painter.end()
            if self.diagnostics:self.diagnostics.record(self.frames[self.index])
    def draw_frame(self,painter,canvas):
        if self.transition and self.transition.started is not None:
            image=self.transition.render(self.sprite_image(),time.monotonic())
            painter.drawImage(canvas,image,QRectF(image.rect()))
        else:self.draw_sprite(painter,canvas)
    def sprite_image(self):
        image=QImage(self.frame_size,self.frame_size,QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter=QPainter(image);painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.draw_sprite(painter,QRectF(image.rect()));painter.end()
        return image
    def draw_sprite(self,painter,canvas):
        painter.save()
        if self.dock_edge:
            # Rotate and slide the COMPLETE sprite beyond the edge. The
            # viewport clips only the off-screen body, never a head crop.
            t=min(1,max(0,(time.monotonic()-getattr(self,'dock_started',0))/.3))
            t=1-(1-t)**3
            if getattr(self,'dock_exit',None):
                progress=min(1,max(0,(time.monotonic()-self.dock_exit[0])/.3))
                t=self.dock_exit[1]*(1-progress)**3
            w,h=canvas.width(),canvas.height()
            pivot=QPointF(w*.5,h*.5)
            angle={'left':45,'right':-45,'top':180,'bottom':0}[self.dock_edge]
            rotation=QTransform();rotation.translate(pivot.x(),pivot.y());rotation.rotate(angle*t);rotation.translate(-pivot.x(),-pivot.y())
            # Match the reference's 55% exposure of the rotated visible bounds,
            # rather than anchoring a guessed head crop to a square viewport.
            stable=self.reference_frame
            if not hasattr(self,'dock_visible_bounds'):self.dock_visible_bounds=QRegion(stable.mask()).boundingRect()
            bounds=self.dock_visible_bounds
            local=QRectF(bounds.x()*w/stable.width(),bounds.y()*h/stable.height(),bounds.width()*w/stable.width(),bounds.height()*h/stable.height())
            rotated=rotation.mapRect(local);exposure=1-.45*t
            dx=dy=0.0
            if self.dock_edge=='left':dx=exposure*rotated.width()-rotated.right()
            elif self.dock_edge=='right':dx=w-exposure*rotated.width()-rotated.left()
            elif self.dock_edge=='top':dy=exposure*rotated.height()-rotated.bottom()
            else:dy=h-exposure*rotated.height()-rotated.top()
            painter.translate(dx*t,dy*t);painter.setTransform(rotation,True)
        if self.movement_mirrored:
            painter.translate(canvas.x()*2+canvas.width(),0);painter.scale(-1,1)
        item=self.display_item or self.current
        scale=item.get('renderScale',1.0);offset=item.get('renderOffset',[0,0])
        width,height=canvas.width()*scale,canvas.height()*scale
        target=QRectF(canvas.x()+(canvas.width()-width)/2+canvas.width()*offset[0],canvas.y()+canvas.height()-height+canvas.height()*offset[1],width,height)
        frame=self.frames[self.index];painter.drawPixmap(target,frame,QRectF(frame.rect()))
        painter.restore()
    def snapshot_frame(self):
        pixmap=QPixmap(self.frame_size,self.frame_size);pixmap.fill(Qt.GlobalColor.transparent)
        painter=QPainter(pixmap);self.draw_frame(painter,QRectF(pixmap.rect()));painter.end();return pixmap
    def position_bubble(self):
        screen=QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
        area=screen.availableGeometry();pet=self.frameGeometry()
        width,height=self.bubble.width(),self.bubble.height();gap=12
        if self.dock_edge in ('left','right'):
            # The rotated sprite occupies only part of its transparent window.
            # Attach to real painted pixels, not the empty window rectangle.
            pixmap=self.grab();bounds=QRegion(pixmap.mask()).boundingRect();ratio=pixmap.devicePixelRatio()
            visible=QRectF(bounds.x()/ratio,bounds.y()/ratio,bounds.width()/ratio,bounds.height()/ratio).toAlignedRect().translated(self.pos())
            x=visible.right()+7 if self.dock_edge=='left' else visible.left()-width-6
            y=visible.center().y()-height//2
            self.bubble.move(clamp_position(QPoint(x,y),self.bubble.size(),area));return
        if not getattr(self.bubble,'is_quota_result',False):
            x=max(area.left(),min(pet.center().x()-width//2,area.right()-width+1))
            y=pet.top()-height-gap
            if y<area.top():y=pet.bottom()+gap+1
            y=max(area.top(),min(y,area.bottom()-height+1))
            self.bubble.move(x,y);return
        # Prefer the sides; choose a screen-safe position with no character overlap.
        candidates=[(pet.right()+gap+1,pet.center().y()-height//2),
                    (pet.left()-width-gap,pet.center().y()-height//2),
                    (pet.center().x()-width//2,pet.top()-height-gap),
                    (pet.center().x()-width//2,pet.bottom()+gap+1)]
        positions=[]
        for x,y in candidates:
            x=max(area.left(),min(x,area.right()-width+1))
            y=max(area.top(),min(y,area.bottom()-height+1))
            overlap=pet.intersected(QRect(x,y,width,height))
            score=max(0,overlap.width())*max(0,overlap.height())
            if self.chat and self.chat.enabled:
                overlap=self.chat.composer.frameGeometry().intersected(QRect(x,y,width,height))
                score+=max(0,overlap.width())*max(0,overlap.height())
            positions.append((score,x,y))
        _,x,y=min(positions,key=lambda item:item[0]);self.bubble.move(x,y)
    def say(self,text,ms=4000):
        if self.speech_hidden():return
        self.bubble_timer.stop();self.bubble.message(text);self.position_bubble()
        if ms:self.bubble_timer.start(ms)
    def dismiss_bubble(self):
        self.quota_bubble_requested=False
        self.bubble_timer.stop()
        self.bubble.hide()
        if self.mode=='quota':self.idle()
    def task_result(self,title,text,details):
        if self.task_bubbles_disabled:return
        if self.speech_hidden():return
        self.quota_bubble_requested=False
        self.generation+=1;self.bubble_timer.stop()
        self.bubble.task_result(title,text,details);self.position_bubble();self.bubble_timer.start(20000)
    def task_progress(self,title,text,details):
        if title=='工具进度':
            self.last_tool_status=text
            if text.startswith(('命令执行失败','本次调用失败','调用已中断','调用已拒绝')):
                return
        if self.task_bubbles_disabled:return
        if self.desktop_hidden():return
        self.quota_bubble_requested=False
        self.bubble_timer.stop()
        if getattr(self.bubble,'is_task_progress',False) and self.bubble.isVisible():
            view=self.bubble.result_view;bar=view.verticalScrollBar()
            bottom=bar.value()>=bar.maximum()-8;old=bar.value()
            self.bubble.result_title.setText(title);view.setPlainText(text)
            self.bubble.fit_content()
            bar.setValue(bar.maximum() if bottom else min(old,bar.maximum()))
        else:
            self.bubble.task_result(title,text,details);self.bubble.is_task_progress=True
        self.position_bubble();self.bubble_timer.start(12000)
    def task_completed(self,text,details):
        self.play_click_sound()
        celebration=next((v for v in self.variants if v['id']=='18'),None)
        if celebration and not self.dock_edge:self.play(celebration,'task-celebration')
        # Play directly so the celebration's interaction line is never shown.
        self.task_result('主人，完成啦！',text,details)
    def chat_controller(self):
        if self.chat is None:
            from chat_ui import ChatController
            try:self.chat=ChatController(self)
            except Exception as error:
                self.say('唔，主人，对话模式暂时打不开啦：'+str(error),10000);return None
        return self.chat
    def toggle_chat(self):
        self.undock()
        self.note_interaction()
        controller=self.chat_controller()
        if controller:controller.toggle()
        self.sync_dialogue_visibility()
    def open_history(self):
        self.note_interaction()
        controller=self.chat_controller()
        if controller:controller.open_history()
    def context_menu(self):
        menu=QMenu(self)
        if self.dock_edge:menu.addAction('展开桌宠',self.begin_undock)
        action=menu.addAction('显示桌宠' if self.manual_hidden or self.fullscreen_hidden else '隐藏桌宠')
        action.triggered.connect(lambda checked=False:self.set_manual_hidden(not self.manual_hidden if not self.fullscreen_hidden else False))
        if self.fullscreen_hidden:
            menu.addAction('全屏结束后自动显示').setEnabled(False)
        menu.addSeparator()
        automatic=menu.addAction('全屏时自动隐藏');automatic.setCheckable(True)
        automatic.setChecked(self.auto_hide_fullscreen);automatic.toggled.connect(self.set_auto_hide_fullscreen)
        if sys.platform=='win32':
            from autostart import startup_entry
            launch=menu.addAction('随 Codex / GPT 自动启动');launch.setCheckable(True)
            launch.setChecked(startup_entry().is_file());launch.toggled.connect(self.set_autostart_enabled)
        menu.addSeparator()
        menu.addAction('关闭对话模式' if self.chat and self.chat.enabled else '打开对话模式',self.toggle_chat)
        menu.addAction('查看历史对话',self.open_history)
        menu.addAction('对话框大小…',self.show_bubble_settings)
        menu.addSeparator()
        interaction=QMenu('互动差分动画',menu);menu.addMenu(interaction)
        for item in self.variants:
            action=interaction.addAction(item['id']+' · '+item['name'])
            action.triggered.connect(lambda checked=False,v=item:self.choose(v))
        work=QMenu('工作差分动画',menu);menu.addMenu(work)
        available=[item for item in self.work_slots if item and self.asset_path(item).is_file()]
        for item in available:
            action=work.addAction(item['id']+' · '+item['name'])
            action.triggered.connect(lambda checked=False,v=item:self.choose(v))
        if not available:work.addAction('暂无动作（已预留6个位置）').setEnabled(False)
        idle=QMenu('待机差分动画',menu);menu.addMenu(idle)
        for index,item in enumerate(self.idles+self.extra_idles):
            name='默认待机' if index==0 else ('待机动作02' if index==1 else item['name'])
            action=idle.addAction(name);action.triggered.connect(lambda checked=False,v=item:self.preview_idle(v))
        movement=QMenu('移动差分',menu);menu.addMenu(movement)
        for item in self.movement_slots:
            action=movement.addAction(item.get('number',item['id'])+' · '+item['name'])
            action.triggered.connect(lambda checked=False,v=item:self.start_movement(v,manual=True))
        if not self.movement_slots:movement.addAction('暂无动作').setEnabled(False)
        movement_switch=menu.addAction('禁用自移动');movement_switch.setCheckable(True)
        movement_switch.setChecked(self.auto_movement_disabled)
        movement_switch.toggled.connect(self.set_auto_movement_disabled)
        # Keep Python wrappers alive as well as Qt's native ownership tree.
        menu._submenus=(interaction,work,idle,movement)
        menu.addSeparator();menu.addAction('桌宠大小…',self.show_size_dialog)
        muted=menu.addAction('禁用音效');muted.setCheckable(True)
        muted.setChecked(self.sound_disabled);muted.toggled.connect(self.set_sound_disabled)
        menu.addSeparator()
        menu.addAction('性能设置…',self.show_performance_settings)
        menu.addAction('性能统计…',self.show_diagnostics)
        smooth=menu.addAction('平滑动画切换');smooth.setCheckable(True)
        smooth.setChecked(self.smooth_switch_enabled);smooth.toggled.connect(self.set_smooth_switch_enabled)
        badge=menu.addAction('常驻显示额度');badge.setCheckable(True)
        badge.setChecked(self.quota_badge_enabled);badge.toggled.connect(self.set_quota_badge_enabled)
        menu.addAction('查询 Codex 额度',self.quota)
        menu.addAction('关于…',self.show_about)
        menu.addAction('退出桌宠',self.close)
        return menu
    def show_diagnostics(self):
        if self.diagnostics is None:
            from diagnostics import DiagnosticsWindow
            self.diagnostics=DiagnosticsWindow(self,ROOT)
        self.diagnostics.reveal()
    def show_performance_settings(self):
        from performance_settings import PerformanceSettings
        if not hasattr(self,'performance_settings'):
            self.performance_settings=PerformanceSettings(self)
        self.performance_settings.showNormal();self.performance_settings.raise_();self.performance_settings.activateWindow()
    def apply_performance(self,resolution,capacity,fps_limit,preload_whole):
        self.resolution=resolution;self.buffer_capacity=capacity;self.fps_limit=fps_limit
        self.preload_whole=preload_whole
        self.settings.setValue('animationResolution',resolution)
        self.settings.setValue('animationBufferFrames',capacity)
        self.settings.setValue('animationFPSLimit',fps_limit)
        self.settings.setValue('preloadWholeAnimation',preload_whole)
        self.frame_size=self.desired_decode_size();self.stream.clear_other_sizes(self.frame_size)
        route=self.movement_plan
        self.play(self.current,self.mode)
        if route:self.movement_plan=(QPoint(self.pos()),route[1])
        self.prepare_common_animations()
    def set_autostart_enabled(self,enabled):
        from autostart import enable_autostart,disable_autostart
        try:
            (enable_autostart if enabled else disable_autostart)()
        except (OSError,RuntimeError) as error:
            QMessageBox.warning(self,'自动启动设置失败',str(error))
    def set_smooth_switch_enabled(self,enabled):
        self.smooth_switch_enabled=enabled;self.settings.setValue('smoothSwitchEnabled',enabled)
        if not enabled:
            self.transition=None;self.update_tick_interval();self.update()
    def show_about(self):
        QMessageBox.about(self,'关于白龙桌宠',
            '<h3>GPT白龙娘动态桌宠</h3>'
            f'<p>分支版本：{platform_version()}<br>原作者基线：v{BASE_VERSION}<br>分支：{BRANCH}</p>'
            '<p>技术栈：Python · PySide6 / Qt · FFmpeg<br>角色素材：原作者 v0.5.1 素材</p>'
            '<p><a href="https://github.com/jingh12312-rgb/bailong-desktop-pet">原作者项目</a></p>')
    def set_sound_disabled(self,disabled):
        self.sound_disabled=bool(disabled);self.settings.setValue('soundDisabled',self.sound_disabled)
    def set_task_bubbles_disabled(self,disabled):
        self.task_bubbles_disabled=bool(disabled)
        self.settings.setValue('taskBubblesDisabled',self.task_bubbles_disabled)
        if disabled and self.bubble.is_task_bubble:self.dismiss_bubble()
    def set_bubble_percent(self,value):
        self.bubble_percent=max(50,min(150,int(value)))
        self.bubble.set_scale_percent(self.bubble_percent)
        self.settings.setValue('bubblePercent',self.bubble_percent)
        if self.bubble.isVisible():self.position_bubble()
    def show_bubble_settings(self):
        if not hasattr(self,'bubble_settings_dialog'):
            dialog=QDialog(self,Qt.WindowType.Tool|Qt.WindowType.WindowStaysOnTopHint)
            configure_linux_dialog(dialog)
            dialog.setWindowTitle('对话框大小与提醒');layout=QVBoxLayout(dialog)
            layout.setContentsMargins(18,16,18,16);layout.setSpacing(14)
            label=QLabel(dialog);slider=QSlider(Qt.Orientation.Horizontal,dialog)
            slider.setRange(50,150);slider.setMinimumWidth(280)
            slider.valueChanged.connect(self.set_bubble_percent)
            slider.valueChanged.connect(lambda value:label.setText(f'对话框大小：{value}%（50%—150%）'))
            reset=QPushButton('恢复默认大小',dialog);reset.clicked.connect(lambda:slider.setValue(100))
            mute=QCheckBox('禁用聊天气泡提醒',dialog)
            mute.setToolTip('关闭任务接收、进展、异常和完成气泡；互动与额度气泡不受影响。')
            mute.toggled.connect(self.set_task_bubbles_disabled)
            done=QPushButton('完成',dialog);done.clicked.connect(dialog.accept)
            dialog.finished.connect(self.finish_bubble_preview)
            for widget in (label,slider,reset,mute,done):layout.addWidget(widget)
            self.bubble_settings_dialog=dialog;self.bubble_slider=slider;self.bubble_size_label=label
            self.bubble_reset=reset;self.task_bubble_checkbox=mute
        if not self.bubble.isVisible():
            self.bubble_timer.stop();self.bubble.size_preview();self.position_bubble()
        self.bubble_size_label.setText(f'对话框大小：{self.bubble_percent}%（50%—150%）')
        self.bubble_slider.setValue(self.bubble_percent)
        self.task_bubble_checkbox.setChecked(self.task_bubbles_disabled)
        self.bubble_settings_dialog.adjustSize()
        self.position_size_dialog(reserve=True,dialog=self.bubble_settings_dialog)
        self.bubble_settings_dialog.show()
        self.position_size_dialog(reserve=True,dialog=self.bubble_settings_dialog)
        self.bubble_settings_dialog.raise_();self.bubble_settings_dialog.activateWindow()
    def finish_bubble_preview(self):
        if self.bubble.is_size_preview:
            self.bubble.hide();self.bubble.is_size_preview=False;self.bubble.clear()
    def show_size_dialog(self):
        if not hasattr(self,'size_dialog'):
            dialog=QDialog(self,Qt.WindowType.Tool|Qt.WindowType.WindowStaysOnTopHint)
            configure_linux_dialog(dialog)
            dialog.setWindowTitle('调节桌宠大小');layout=QVBoxLayout(dialog)
            layout.setContentsMargins(18,16,18,16);layout.setSpacing(14)
            label=QLabel(dialog);slider=QSlider(Qt.Orientation.Horizontal,dialog)
            slider.setRange(50,200);slider.setMinimumWidth(280)
            slider.valueChanged.connect(self.set_size_percent)
            slider.valueChanged.connect(lambda value:label.setText(f'桌宠大小：{value}%（50%—200%）'))
            close=QPushButton('完成',dialog);close.clicked.connect(dialog.accept)
            reset=QPushButton('恢复默认',dialog);reset.clicked.connect(lambda:slider.setValue(100))
            layout.addWidget(label);layout.addWidget(slider);layout.addWidget(reset);layout.addWidget(close)
            self.size_dialog=dialog;self.size_slider=slider;self.size_label=label
            self.size_reset=reset
        self.size_label.setText(f'桌宠大小：{self.size_percent}%（50%—200%）')
        self.size_slider.setValue(self.size_percent)
        self.size_dialog.adjustSize()
        self.position_size_dialog(reserve=True)
        self.size_dialog.show();self.position_size_dialog(reserve=True)
        self.size_dialog.raise_();self.size_dialog.activateWindow()
    def position_size_dialog(self,reserve=False,dialog=None):
        dialog=dialog or getattr(self,'size_dialog',None)
        if dialog is None:return
        pet=self.frameGeometry()
        screen=QApplication.screenAt(pet.center()) or QApplication.primaryScreen()
        area=screen.availableGeometry();size=dialog.frameGeometry().size()
        if not reserve and not dialog.frameGeometry().intersects(pet.adjusted(-12,-12,12,12)):return
        occupied=QRect(pet)
        if reserve:
            for pixels in (128,512):
                point=clamp_position(QPoint(pet.center().x()-pixels//2,pet.bottom()+1-pixels),QSize(pixels,pixels),area)
                occupied=occupied.united(QRect(point,QSize(pixels,pixels)))
            if dialog is getattr(self,'bubble_settings_dialog',None) and self.bubble.isVisible():
                # Keep the options panel away from the bubble being previewed,
                # including the extra space needed when scaled up to 150%.
                bubble=self.bubble.frameGeometry()
                occupied=occupied.united(bubble.adjusted(-150,-bubble.height()//2,150,bubble.height()//2))
        gap=20;w,h=size.width(),size.height()
        points=[QPoint(occupied.right()+gap,pet.center().y()-h//2),QPoint(occupied.left()-w-gap,pet.center().y()-h//2),
                QPoint(pet.center().x()-w//2,occupied.top()-h-gap),QPoint(pet.center().x()-w//2,occupied.bottom()+gap)]
        points=[clamp_position(point,size,area) for point in points]
        chosen=next((point for point in points if not QRect(point,size).intersects(occupied)),None)
        if chosen is None:
            # At extreme screen sizes choose the least overlap with the pet.
            def overlap(point):
                r=QRect(point,size).intersected(pet);return max(0,r.width())*max(0,r.height())
            chosen=min(points,key=overlap)
        dialog.move(chosen)
    def set_size_percent(self,value):
        value=max(50,min(200,int(value)))
        if value==self.size_percent:return
        self.note_interaction();center=self.frameGeometry().center();bottom=self.frameGeometry().bottom()
        self.size_percent=value;pixels=round(256*value/100)
        self.setFixedSize(pixels,pixels)
        self.move(self.constrained_position(QPoint(center.x()-pixels//2,bottom+1-pixels)))
        if self.dock_edge:
            screen=QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
            area=screen.availableGeometry();position=self.pos()
            if self.dock_edge=='left':position.setX(area.left())
            elif self.dock_edge=='right':position.setX(area.right()+1-pixels)
            elif self.dock_edge=='top':position.setY(area.top())
            else:position.setY(area.bottom()+1-pixels)
            self.move(position)
        self.settings.setValue('sizePercent',value)
        if self.bubble.isVisible():self.position_bubble()
        if self.chat:self.chat.position()
        self.update()
    def preview_idle(self,item):
        self.note_interaction()
        self.click_timer.stop();self.last_click=None;self.generation+=1;self.play(item,'idle')
    def play_click_sound(self):
        if self.sound_disabled:return
        if sys.platform.startswith('linux'):
            import subprocess
            environment=os.environ.copy()
            environment['LD_LIBRARY_PATH']=environment.get('LD_LIBRARY_PATH_ORIG','')
            self.click_sound_process=subprocess.Popen(['/usr/bin/paplay',str(ROOT/'app/sounds/click.wav')],env=environment)
            return
        if sys.platform=='darwin':
            from PySide6.QtMultimedia import QSoundEffect
            from PySide6.QtCore import QUrl
            if not hasattr(self,'click_sound'):
                self.click_sound=QSoundEffect(self);self.click_sound.setSource(QUrl.fromLocalFile(str(ROOT/'app/sounds/click.wav')))
            self.click_sound.play();return
        if sys.platform=='win32':
            import winsound
            sound=ROOT/'app/sounds/click.wav'
            if sound.is_file():
                try:winsound.PlaySound(str(sound),winsound.SND_FILENAME|winsound.SND_ASYNC|winsound.SND_NODEFAULT)
                except RuntimeError:pass
    def choose(self,item):
        self.note_interaction()
        self.click_timer.stop();self.last_click=None;self.generation+=1
        try:self.play_click_sound();self.play(item,'variant');self.say(item.get('line',''),4000)
        except Exception as error:self.idle();self.say('唔，主人，这个动作暂时没能准备好：'+str(error))
    def single_click(self):
        self.last_click=None
        pool=self.interaction_animations()
        previous=self.current.get('id') if self.current else None
        available=[v for v in pool if v['id']!=previous] or pool
        if available:self.choose(random.choice(available))
    def interaction_animations(self):
        return self.variants+[v for v in self.work_slots if v and self.asset_path(v).is_file()]
    def quota(self):
        self.note_interaction()
        self.click_timer.stop();self.last_click=None;self.generation+=1;token=self.generation
        self.play_click_sound()
        if not self.dock_edge:self.play(self.manifest.get('quotaAnimation') or self.idles[0],'quota')
        self.quota_generation=token;self.quota_bubble_requested=True
        self.quota_cache.validate_account()
        if self.quota_cache.fresh():
            self.show_cached_quota();return
        refreshing=self.start_quota_refresh()
        if self.quota_cache.windows:self.show_cached_quota(refreshing=refreshing)
        elif refreshing:self.say('正在查询 Codex 额度…',0)
        else:self.say('额度暂时未更新。\n'+(self.quota_error or '请稍后重试。'),8000)
    def start_quota_refresh(self):
        if self.quota_inflight:return True
        if time.monotonic()-self.last_quota_attempt<QUOTA_RETRY_SECONDS:return False
        self.last_quota_attempt=time.monotonic();self.quota_inflight=True
        self.quota_request_account=self.quota_cache.revision()
        worker=QuotaWorker(self);self.worker=worker
        worker.ready.connect(self.quota_ready);worker.failed.connect(self.quota_failed)
        worker.finished.connect(lambda w=worker:self.quota_worker_finished(w))
        worker.finished.connect(worker.deleteLater);worker.start()
        self.update_quota_badge();return True
    def quota_worker_finished(self,worker):
        if self.worker is worker:self.worker=None
    def show_cached_quota(self,refreshing=False):
        if not self.quota_bubble_requested or self.quota_generation!=self.generation or self.speech_hidden():return
        self.bubble.quota(self.quota_cache.windows,self.quota_cache.updated_at,
                         refreshing=refreshing,error=None if refreshing else self.quota_error)
        self.position_bubble();self.bubble_timer.start(12000)
    def quota_ready(self,windows):
        self.quota_inflight=False
        if self.quota_request_account!=self.quota_cache.revision():
            self.quota_cache.validate_account()
            self.quota_failed('登录状态已变化，请重新查询额度。');return
        self.quota_cache.update(windows);self.quota_error=None
        self.show_cached_quota();self.update_quota_badge()
    def quota_failed(self,error):
        self.quota_inflight=False
        self.quota_error=str(error)
        if self.quota_bubble_requested and self.quota_generation==self.generation:
            if self.quota_cache.windows:self.show_cached_quota()
            else:self.say('额度刷新失败。\n'+str(error),8000)
        self.update_quota_badge()
    def background_quota_refresh(self):
        if self.quota_badge_enabled and not self.desktop_hidden() and not self.quota_cache.fresh():
            self.start_quota_refresh()
        self.update_quota_badge()
    def set_quota_badge_enabled(self,enabled):
        self.quota_badge_enabled=enabled;self.settings.setValue('quotaBadgeEnabled',enabled)
        self.background_quota_refresh()
    def position_quota_badge(self):
        screen=QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
        area=screen.availableGeometry();badge=self.quota_badge
        y=self.y()-badge.height()-6
        if y<area.top():y=self.y()+self.height()+6
        badge.move(clamp_position(QPoint(self.x()+(self.width()-badge.width())//2,y),badge.size(),area))
    def update_quota_badge(self):
        self.quota_badge.refresh(self.quota_cache,self.quota_inflight,self.quota_error)
        self.position_quota_badge()
        self.quota_badge.setVisible(self.quota_badge_enabled and not self.desktop_hidden())
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.dock_edge:
            self.consume_dock_release=True;self.pointer_down=False
            self.note_interaction(cancel_movement=False)
            self.dock_double_click=self.dock_click_timer.isActive()
            if self.dock_double_click:
                self.dock_click_timer.stop();self.quota()
            return
        self.note_interaction()
        if event.button()==Qt.MouseButton.RightButton:
            self.dock_click_timer.stop()
            self.click_timer.stop();self.last_click=None
            menu=self.context_menu();menu.exec(event.globalPosition().toPoint());menu.deleteLater();return
        if event.button()==Qt.MouseButton.LeftButton:
            self.pointer_down=True
            self.press_pos=event.globalPosition().toPoint();self.origin=self.pos();self.dragging=False
    def mouseDoubleClickEvent(self,event):
        # Qt may emit this before mousePressEvent for the second physical press.
        self.mousePressEvent(event)
    def mouseMoveEvent(self,event):
        if getattr(self,'consume_dock_release',False):return
        if event.buttons()&Qt.MouseButton.LeftButton and hasattr(self,'press_pos'):
            delta=event.globalPosition().toPoint()-self.press_pos
            if delta.manhattanLength()>8 and not self.dragging:
                self.dragging=True;self.click_timer.stop();self.last_click=None;self.generation+=1
                self.bubble_timer.stop();self.bubble.hide()
                self.play(self.manifest.get('dragAnimation') or self.idles[0],'drag')
            if self.dragging:
                self.move(self.constrained_position(self.origin+delta,event.globalPosition().toPoint()))
                self.position_bubble()
    def mouseReleaseEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton:return
        if getattr(self,'consume_dock_release',False):
            self.consume_dock_release=False;self.pointer_down=False
            self.click_timer.stop();self.last_click=None
            if self.dock_edge and not self.dock_double_click:self.dock_click_timer.start()
            self.dock_double_click=False;return
        # A menu's closing mouse release can land on the moving pet, without
        # a matching press on the pet. It is not a new click or stop command.
        if not self.pointer_down and not self.dragging:return
        self.pointer_down=False;self.note_interaction()
        if self.dragging:
            self.dragging=False;self.last_click=None;self.click_timer.stop()
            if self.try_dock():return
            landing=self.manifest.get('landingAnimation')
            if landing:self.play(landing,'landing')
            else:self.idle()
            return
        now=time.monotonic()
        if self.last_click is not None and now-self.last_click<=.25:self.quota()
        else:self.last_click=now;self.click_timer.start()
    def closeEvent(self,event):
        if self.chat and not self.chat.shutdown():
            event.ignore();QTimer.singleShot(500,self.close);return
        self.desktop_sync.stop()
        self.quota_timer.stop();self.resolution_timer.stop();self.quota_badge.close()
        self.stream.close()
        if self.diagnostics:self.diagnostics.close()
        self.tick.stop();self.visibility_timer.stop();self.tray.hide();self.bubble.close()
        if self.worker and self.worker.isRunning():self.worker.cancel.set();self.worker.wait(3000)
        QApplication.quit();event.accept()

def main():
    if '--autostart' in sys.argv:
        from autostart import main as monitor
        return monitor()
    if '--self-test' in sys.argv:
        from selftest import run
        return run(ROOT)
    app=QApplication(sys.argv)
    if sys.platform.startswith('linux'):
        app.setDesktopFileName('bailong-desktop-pet')
    app.setQuitOnLastWindowClosed(False)
    if '--enable-autostart' in sys.argv or '--disable-autostart' in sys.argv:
        from autostart import enable_autostart,disable_autostart
        try:
            if '--enable-autostart' in sys.argv:
                enable_autostart();message='已开启：以后登录系统时，助手会自动运行；打开GPT后启动桌宠。\n如要移动桌宠文件夹，请先关闭自动启动，移好后再开启。'
            else:disable_autostart();message='已关闭桌宠自动启动。'
            QMessageBox.information(None,'白龙桌宠',message);return 0
        except Exception as error:QMessageBox.critical(None,'设置失败',str(error));return 1
    socket=QLocalSocket();socket.connectToServer('bailong-desktop-pet-v1')
    if socket.waitForConnected(150):return 0
    QLocalServer.removeServer('bailong-desktop-pet-v1');server=QLocalServer();server.listen('bailong-desktop-pet-v1')
    try:
        pet=Pet();pet.show();configure_mac_window(pet);configure_mac_window(pet.bubble)
        def reveal_existing_pet():
            while server.hasPendingConnections():
                connection=server.nextPendingConnection()
                connection.disconnectFromServer();connection.deleteLater()
            screen=QApplication.primaryScreen()
            if screen:
                area=screen.availableGeometry()
                pet.move(clamp_position(QPoint(area.center().x()-pet.width()//2,area.center().y()-pet.height()//2),pet.size(),area))
            pet.set_manual_hidden(False)
            if pet.desktop_hidden():return
            pet.showNormal();pet.show();pet.raise_()
            if sys.platform=='win32':
                import ctypes
                ctypes.windll.user32.ShowWindow(int(pet.winId()),4)
        server.newConnection.connect(reveal_existing_pet)
        def record_startup():
            # pythonw can inherit a hidden startup state from a launcher.
            # Explicitly show this app's own window without stealing focus.
            native_visible=pet.isVisible()
            if sys.platform=='win32':
                import ctypes
                handle=int(pet.winId())
                ctypes.windll.user32.ShowWindow(handle,4)
                native_visible=bool(ctypes.windll.user32.IsWindowVisible(handle))
            (STATE_ROOT/'app').mkdir(parents=True,exist_ok=True)
            (STATE_ROOT/'app/运行状态.json').write_text(json.dumps({'version':VERSION,'pid':os.getpid(),'visible':pet.isVisible(),'nativeVisible':native_visible,'windowId':int(pet.winId()),'variants':len(pet.variants),'position':[pet.x(),pet.y()],'displaySize':[pet.width(),pet.height()],'frameSize':[pet.frames[0].width(),pet.frames[0].height()] if pet.frames else []},ensure_ascii=False),encoding='utf-8')
        QTimer.singleShot(1000,record_startup)
        def record_visibility():
            (STATE_ROOT/'app/显示诊断.json').write_text(json.dumps({'pid':os.getpid(),'visible':pet.isVisible(),'manualHidden':pet.manual_hidden,'fullscreenHidden':pet.fullscreen_hidden,'trayVisible':pet.tray.isVisible(),'trayAvailable':QSystemTrayIcon.isSystemTrayAvailable(),'syncWatching':pet.desktop_sync.timer.isActive(),'syncActive':len(pet.desktop_sync.running),'syncObserved':len(pet.desktop_sync.known),'platform':QApplication.platformName(),'position':[pet.x(),pet.y()],'windowId':int(pet.winId())},ensure_ascii=False),encoding='utf-8')
        diagnostic_timer=QTimer(pet);diagnostic_timer.setInterval(2000);diagnostic_timer.timeout.connect(record_visibility);diagnostic_timer.start()
        if '--preview' in sys.argv:
            QTimer.singleShot(500,lambda:pet.grab().save(str(STATE_ROOT/'app/桌宠窗口预览.png')))
            QTimer.singleShot(900,app.quit)
    except Exception as error:QMessageBox.critical(None,'白龙桌宠启动失败',str(error));return 1
    return app.exec()

if __name__=='__main__':sys.exit(main())
