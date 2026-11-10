# 白龙桌宠 · Windows 优化版

基于 [jingh12312-rgb/bailong-desktop-pet](https://github.com/jingh12312-rgb/bailong-desktop-pet) 与 [Joseph-Blue 的 opt.23 优化分支](https://github.com/Joseph-Blue/bailong-desktop-pet-optimization)，保留白龙娘的 35 段动作、拖动、吸边、自移动及 Codex 联动，进一步降低常驻内存、减少无效提醒并改善额度查询体验。

当前版本 **0.5.1-local.2**，维护分支 **`local/windows`**。本分支完成了 Windows x64 验证；macOS 入口继承上游，尚未在本分支验收。

## 主要改动

| 功能 | 行为 |
| --- | --- |
| 低内存动画 | 后台流式解码，默认 12 帧缓冲；快速切换取消旧解码，隐藏时暂停 |
| 常用动作缓存 | 缓存常用动作的开头帧，上限 24 MiB，预读待机、拖动和落地等动作 |
| 自适应清晰度 | 根据桌宠实际大小与所在窗口的 DPI 调整分辨率，最高 720×720 |
| 动画调度 | 按素材帧率刷新，移动与吸边过渡保留 16 ms 更新 |
| 性能设置 | 省内存、均衡、高清档位；支持单独调整分辨率、帧率和缓冲 |
| 额度查询 | 先显示缓存和更新时间，较旧时后台刷新；合并重复请求，失败保留上次记录 |
| 常驻额度签 | 可选开启；显示期间每 5 分钟刷新，隐藏时不自动查询 |
| 提醒分级 | 单次工具失败不主动弹气泡；整轮失败、权限确认及完成提醒保留 |
| 启动联动 | 右键菜单可切换随 Codex / GPT 自动启动 |
| 透明边缘 | 两段待机、拖动、落地采用上游 Alpha 清理素材，处理部分帧的边缘色块 |

默认使用「均衡」：自适应清晰度、素材原帧率、12 帧缓冲。常驻额度签默认关闭。额度缓存 60 秒内复用，失败后的请求间隔至少 15 秒。

## 获取与构建

本仓库提供源码和构建入口，动画从上游素材 Release 按需下载。

1. 安装 Windows x64 的 Python 3.11～3.13。
2. 克隆本仓库，打开 PowerShell，执行：

```powershell
git clone --branch local/windows https://github.com/moon135246/bailong-desktop-pet-optimization.git
cd bailong-desktop-pet-optimization
.\build-windows.ps1 -Zip
```

输出目录：`dist-windows/build-v0.5.1-local.2/BailongPet/`。运行其中的 `BailongPet.exe`，保留完整目录。

已有依赖环境和完整素材时，也可运行：

```powershell
python work/build_windows_optimized.py --existing-assets --zip
```

完整命令、素材准备和依赖说明见 [BUILDING.md](BUILDING.md)。

## 使用

- 单击互动，双击查询 Codex 额度；拖动可移动桌宠。
- 右键打开「性能设置」「性能统计」，或开启「常驻显示额度」。
- 右键「随 Codex / GPT 自动启动」控制启动联动。
- 动画可独立运行；额度、对话与任务同步使用使用者自己的 Codex 安装和登录。

## 验证与性能

已完成专项回归、Windows 打包自检、真实只读额度连接检查，以及四段修复动画的 336 帧对照。35 段动画首帧解码和缓冲上限检查通过，其余 31 段动画与原安装文件逐字节一致。

在同一台 Windows 电脑上，原版运行内存约 2.4～2.7 GB，优化版一次采样约 222 MiB，包含桌宠、FFmpeg 和启动监听。RSS 汇总可能重复计入共享页；这是实测样本，不代表所有设备。范围、方法与上游已有测试问题见 [Windows 验证记录](docs/WINDOWS_VALIDATION.md)。

## 来源与署名

- 角色、35 段动作及原始项目：**jingh12312-rgb**。
- 流式解码、性能窗口、精简 FFmpeg 与四段透明边缘修复基础：**Joseph-Blue**，本分支基于其 `opt.23` 之后的提交 `11abecbc8a78e9c734e73028472c4d2bb1c362f5`。
- 本仓库的 Windows 缓存、额度、提醒与调度改进：**moon135246**。

原项目、素材和运行库的来源与许可说明保留，见 [ASSETS.md](ASSETS.md)。Git 仓库不包含整段动画、本机账号、聊天记录、额度缓存或虚拟环境。原作者的 `BUILD_INFO.json`、`RELEASE_NOTES.md` 和原始安装说明作为历史发行记录保留；当前版本以本 README、`app/version.py` 和 [CHANGELOG.md](CHANGELOG.md) 为准。
