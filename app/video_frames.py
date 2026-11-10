"""Decode VP9 alpha explicitly; the default VP9 decoder may discard alpha."""
import os,subprocess,sys,shutil,re,threading
from collections import deque
from pathlib import Path
from platform_support import resource_root
from alpha_cleanup import clean_rgba

def ffmpeg_path():
    root=resource_root()
    candidates = ([root/'tools/ffmpeg.exe',root/'work/video-deps/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe']
                  if sys.platform=='win32' else [root/'tools/ffmpeg'])
    for candidate in candidates:
        if candidate.is_file():return str(candidate)
    found=shutil.which('ffmpeg')
    if found:return found
    raise RuntimeError('缺少透明动画播放器，请重新完整解压桌宠安装包。')

def rgba_frames(path,size,process_changed=None,rate_changed=None,fps=None,clean_edges=True):
    # Area downsampling avoids Lanczos ringing outside an otherwise clean alpha.
    filters=f'scale={size}:{size}:flags={"area" if clean_edges else "lanczos"}'
    if fps is not None:filters=f"fps='min(source_fps,{fps})',"+filters
    args=[ffmpeg_path(),'-hide_banner','-nostdin','-nostats','-loglevel','info' if rate_changed else 'error','-threads','2','-c:v','libvpx-vp9','-i',str(path),'-an','-vf',filters,'-pix_fmt','rgba','-threads','2','-f','rawvideo','pipe:1']
    kwargs={'creationflags':subprocess.CREATE_NO_WINDOW} if sys.platform=='win32' else {}
    with subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**kwargs) as proc:
        if process_changed:process_changed(proc)
        errors=deque(maxlen=16);rate_ready=threading.Event()
        def drain_errors():
            for raw in proc.stderr:
                line=raw.decode('utf-8',errors='replace');errors.append(line[-1000:])
                if rate_changed and not rate_ready.is_set() and 'Video:' in line:
                    match=re.search(r'\b([0-9]+(?:\.[0-9]+)?) fps\b',line)
                    if match and float(match[1])>0:
                        native_rate=float(match[1])
                        rate_changed(native_rate if fps is None else min(native_rate,fps));rate_ready.set()
        reader=threading.Thread(target=drain_errors,daemon=True);reader.start()
        try:
            stride=size*size*4
            while True:
                raw=proc.stdout.read(stride)
                if not raw:break
                if len(raw)!=stride:raise RuntimeError('动画帧不完整：'+str(path))
                if rate_changed and not rate_ready.wait(2):raise RuntimeError('FFmpeg 未提供素材帧率：'+str(path))
                yield clean_rgba(raw,size) if clean_edges else raw
            status=proc.wait();reader.join()
            if status!=0:raise RuntimeError('透明动画读取失败：'+''.join(errors)[-1000:])
        finally:
            if proc.poll() is None:proc.kill();proc.wait()
            reader.join()
            if process_changed:process_changed(None)
