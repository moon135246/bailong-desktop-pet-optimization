# 原作者素材来源

- 原项目作者：**jingh12312-rgb**。
- 原仓库：https://github.com/jingh12312-rgb/bailong-desktop-pet
- 原始素材版本：**v0.5.1**，共 35 段动画及对应素材清单。
- 原始发布：https://github.com/jingh12312-rgb/bailong-desktop-pet/releases/tag/v0.5.1
- 本仓库从上游独立素材包获取动画；角色和动画素材创作不归本仓库所有。局部 Alpha 修复由 Joseph-Blue 优化分支提供。
- 独立素材包：https://github.com/Joseph-Blue/bailong-desktop-pet-optimization/releases/tag/v0.5.1-opt.assets.1
- 修复备选包：https://github.com/Joseph-Blue/bailong-desktop-pet-optimization/releases/tag/v0.5.1-opt.assets.repaired.2

原始包保留全部原始动画；修复备选包仅替换 idle、idle2、drag、landing 四段，其余 31 段保持原样。修复使用本项目 2026-11-07 的 Alpha 清理结果，以 720×720、24 FPS 的透明 VP9 WebM 分发；来源、范围和使用方法见 [修复素材备选包](docs/修复素材备选包.md)。所有构建脚本默认使用修复包；本地仍是原始清单时自动切换四段播放文件，原始动画文件保留。

Windows EXE 与 macOS App 图标使用同批修复 idle 的第一帧。`app/icons/repaired-idle.png` 为该帧原样副本，构建时导出 ICO／ICNS，不重绘角色、不增加底色或阴影。

原作者说明：素材随 Releases 发布，不纳入 Git 历史。35 段动画来自项目作者提供的角色素材及透明处理版本。未额外授予美术素材商用或再分发许可。

构建脚本默认从上述 Joseph-Blue Release 获取修复素材包；原版清单自动切换，已有动画文件保留。公开附件支持匿名下载；若使用受限资源或需要提高 API 限额，可提供使用者自己的 GitHub 登录或 token。本仓库不重新上传整段动画素材。
