# assets/legacy-doubao 目录说明

本目录在安装包中存放**豆包平台沿用的专用流程与 Windows x64 离线资源**，包括：

- `SKILL.md`：豆包专用模型链、尺寸与固定提示词流程
- `scripts/`、`references/`：旧版后处理脚本与重绘提示词
- `assets/art-fixed-enhance-win64/`：Windows x64 完整离线引擎（ART、Python 运行时、Pillow 及固定预设，共 2600+ 文件）

其中 `assets/art-fixed-enhance-win64/` 含大量二进制，且整体体积约 400 MB，不纳入 git，只通过 Release 中的完整安装包分发。

需要完整可运行的安装包，请回到仓库首页，通过 README 中的一键下载链接获取 Release 里的 `hd-upscale.zip`，**不要手动解压**，直接把整个 zip 发给 AI 并说「请安装这个技能」即可。
