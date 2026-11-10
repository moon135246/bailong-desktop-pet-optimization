# Windows 构建说明

当前分支为 `local/windows`，版本 **0.5.1-local.4**。Python 3.11～3.13、Windows x64；本分支以 Windows 150% 缩放完成运行验收。macOS 构建入口继承上游，尚未在本分支验证。

## 一键构建

```powershell
.\build-windows.ps1 -Zip
# 指定本机解释器或透明解码器
.\build-windows.ps1 -Python 'C:\Python313\python.exe' -FFmpeg 'C:\tools\ffmpeg.exe' -Zip
# 已创建构建环境、依赖齐全
.\build-windows.ps1 -SkipInstall -Zip
```

兼容 Windows PowerShell 5.1 与 PowerShell 7+。首次运行选择 64 位 Python，在 `.build/venvs/windows/` 创建独立环境，按 `requirements-build.txt` 安装依赖。不会自动安装 Python，也不会调用 Microsoft Store 的解释器别名。

- 程序目录：`dist-windows/build-v0.5.1-local.4/BailongPet/`。
- 压缩包：`dist-windows/bailong-desktop-pet-v0.5.1-local.4-windows-x86_64.zip`。
- 运行整个目录中的 `BailongPet.exe`。
- ZIP 包含 Python、Qt、FFmpeg、35 段动画、使用说明和许可。打包入口会拒绝包含账号缓存、聊天记录、运行诊断或自检产物的目录，并检查 ZIP 内部 CRC。

## 使用已有环境

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe work/build_windows_optimized.py --zip
```

`--existing-assets` 使用当前 `outputs/白龙桌宠素材/` 中的完整素材，不下载或切换清单：

```powershell
.\.venv\Scripts\python.exe work/build_windows_optimized.py --existing-assets --zip
```

离线构建需要提前准备依赖、35 段动画及清单。使用 `--existing-assets` 时，缺少任何引用素材会明确报错。

## 素材与解码器

默认素材源为 [Joseph-Blue 的修复素材 Release](https://github.com/Joseph-Blue/bailong-desktop-pet-optimization/releases/tag/v0.5.1-opt.assets.repaired.2)，附件 `bailong-repaired-v0.5.1-assets.zip`。完整包包含 35 段动画，其中 idle、idle2、drag、landing 是局部 Alpha 清理版。

- 公开附件支持匿名下载；设置 `GH_TOKEN` / `GITHUB_TOKEN` 或使用已登录的 GitHub CLI，可用于受限资源或提高 API 限额。
- 已有完整修复素材时不联网；缺少素材时显示下载进度并补齐。
- 下载缓存放在 `.build/downloads/`；构建产物与动画不提交到 Git。
- `ASSET_REPOSITORY`、`ASSET_RELEASE_TAG`、`ASSET_FILE_NAME` 可覆盖默认下载位置。
- Windows 默认使用仓库中的精简 `tools/ffmpeg.exe`，保留 libvpx-vp9 透明解码；显式 `--ffmpeg` 优先。

素材的创作与许可沿用原作者及上游说明，见 [ASSETS.md](ASSETS.md) 和 [修复素材说明](docs/修复素材备选包.md)。

## 发布与验证

`.github/workflows/build-platforms.yml` 为手动运行的构建工作流，默认标签 `v0.5.1-local.4`，macOS 构建默认关闭。按需启用工作流后，先创建对应源码标签，再手动运行。构建成功与运行验收分别记录。

[Windows 验证记录](docs/WINDOWS_VALIDATION.md) 包含本分支已执行的检查和采样范围。`app/selftest.py` 保留离线程序自检入口；`--self-test --quota-only` 会通过使用者自己的 Codex 登录只读查询额度。`--chat-only` 会发起真实模型对话，不属于离线检查。

原作者入口 `work/build_windows.py`、`work/build_release.py` 保留；Windows 优化入口使用 `work/build_windows_optimized.py` 与 `work/build_common.py`。

## 继承的 macOS 入口

上游的 `build-macos.sh`、`work/build_macos.py`、精简解码器构建脚本及平台分支保留。本分支没有 macOS 实机验收记录；上游构建说明见 [Joseph-Blue/BUILDING.md](https://github.com/Joseph-Blue/bailong-desktop-pet-optimization/blob/11abecbc8a78e9c734e73028472c4d2bb1c362f5/BUILDING.md)。
