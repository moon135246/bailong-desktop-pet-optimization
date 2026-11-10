# 白龙桌宠 {{TAG}} · Windows 优化版

基于 jingh12312-rgb 原项目与 Joseph-Blue opt.23 优化分支，增加常用动作缓存、额度缓存与可选额度签、性能档位、按尺寸和 DPI 调整清晰度，以及按素材帧率调度。两段待机、拖动与落地使用上游透明边缘修复素材。

## 下载

| 平台 | 完整运行包 |
| --- | --- |
{{DOWNLOAD_ROWS}}

解压并保留完整目录，Windows 运行 `BailongPet/BailongPet.exe`。动画可独立运行，Codex 联动使用使用者自己的安装和登录。

当前分支只有 Windows x64 实机验证记录。macOS 构建为继承的可选入口，默认关闭；只有已上传的产物才会列入表格。

## 默认设置

- 均衡档位：自适应清晰度、素材原帧率、12 帧缓冲。
- 常用动作开头帧缓存上限 24 MiB；隐藏时暂停解码。
- 额度缓存 60 秒内复用；旧缓存先显示并后台刷新。
- 常驻额度签默认关闭，开启后显示期间每 5 分钟刷新。
- 单次工具失败不主动弹气泡，整轮失败、权限确认和完成提醒保留。
- 平滑动画切换默认开启，在相近姿态的自然衔接处提供约 200 ms 的透明过渡，减轻首尾色差。
- 透明边缘净化默认开启：所有动作清理极低透明度残留和极小孤立像素，缩小时减少轮廓外振铃；保留连接主体的细线与较大独立特效。右键菜单可即时关闭对照，无需替换动画文件。

角色与动作作者为 **jingh12312-rgb**；基础优化和四段 Alpha 修复来自 **Joseph-Blue**。素材按[上游 Release](https://github.com/Joseph-Blue/bailong-desktop-pet-optimization/releases/tag/v0.5.1-opt.assets.repaired.2)获取，原有来源和许可保留。

[更新记录](https://github.com/{{REPO}}/blob/{{TAG}}/CHANGELOG.md) · [构建说明](https://github.com/{{REPO}}/blob/{{TAG}}/BUILDING.md) · [验证范围](https://github.com/{{REPO}}/blob/{{TAG}}/docs/WINDOWS_VALIDATION.md) · [项目主页](https://github.com/{{REPO}}/tree/{{TAG}})
