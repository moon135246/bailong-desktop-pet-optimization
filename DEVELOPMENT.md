# 开发说明

本仓库维护 `local/windows` 分支，当前版本 `0.5.1-local.4`，基于 Joseph-Blue 的 `opt.23` 优化实现。原始角色及动作来自 jingh12312-rgb。当前验收范围为 Windows x64。

## 代码入口

| 位置 | 职责 |
| --- | --- |
| `app/pet.py` | 桌宠、动作、气泡、托盘与启动菜单 |
| `app/frame_buffer.py`、`app/video_frames.py` | 有限缓冲、常用动作缓存、预读和透明解码 |
| `app/clip_transition.py` | 相近姿态的短时透明过渡、轮廓匹配及预乘 Alpha 混合 |
| `app/alpha_cleanup.py` | 极低透明度渐隐及八方向连通的小孤立像素清理，保留相连细线与较大独立特效 |
| `app/performance_preferences.py`、`app/performance_settings.py` | 性能默认值、档位及即时设置 |
| `app/diagnostics.py`、`app/performance_metrics.py` | 按需显示性能与平台资源采样 |
| `app/quota.py`、`app/quota_cache.py`、`app/quota_badge.py` | 只读额度连接、本机缓存与常驻额度签 |
| `app/chat_ui.py`、`app/task_activity.py`、`app/desktop_task_sync.py` | 自有会话、外部只读观察与临时工具状态 |
| `app/platform_support.py` | 平台窗口、资源及用户数据路径 |
| `work/build_windows_optimized.py`、`work/build_common.py` | Windows 完整运行目录与 ZIP |

## 协作与版本

- 使用 PySide6 Widgets、原生控件和系统字体；以 Windows 150% 缩放及窄窗口核对布局。
- 性能默认值集中于 `app/performance_preferences.py`；保留使用者已有有效设置。
- 工具状态只投影公开字段，不将参数、输出或私密推理保存为聊天消息。
- `app/version.py` 是版本来源，同步更新 `VERSION.txt`、README、CHANGELOG 和手动构建工作流默认标签。
- 保留原作者 `BUILD_INFO.json`、`RELEASE_NOTES.md`、原始安装说明与许可，作为历史发行记录。
- 提交、推送和发布按当前任务授权执行；不向原作者或社区上游直接推送。

## Git 中保留什么

应用源码、构建脚本、依赖、说明文档、上游已有测试和许可进入 Git。上游已追踪的图标首帧、精简 FFmpeg 与许可证继续保留。

整段动画、虚拟环境、构建产物、聊天记录、额度缓存、运行诊断、本地验证脚本和截图不进入 Git。Windows 验证结果以不含个人数据的摘要记录在 [WINDOWS_VALIDATION.md](docs/WINDOWS_VALIDATION.md)。

## 构建与检查

构建入口见 [BUILDING.md](BUILDING.md)。新增功能、既有检查与运行验收的范围分别记录，保留上游测试；不把构建成功当作运行验收。涉及真实额度或对话的检查使用执行者自己的登录。
