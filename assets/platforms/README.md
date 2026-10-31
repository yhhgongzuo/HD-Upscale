# assets/platforms 目录说明

本目录在安装包中存放 macOS（Intel / Apple Silicon）与 Linux（glibc x64 / ARM64）的**离线后处理资源**：

- `ART-*.dmg` / `ART-*.tar.xz`：ART 1.26.10 官方构建（单文件 100–145 MB）
- `python.tar.gz`：python-build-standalone 离线 Python 运行时
- `pillow-*.whl`：Pillow 12.2.0 离线依赖

这些二进制单文件超过 GitHub 普通仓库 **100 MB 的硬性推送限制**，因此没有纳入 git，只通过 Release 中的完整安装包分发。资源的官方下载地址、SHA-256 与体积见上层 [`resources.json`](../resources.json)。

需要完整可运行的安装包，请回到仓库首页，通过 README 中的一键下载链接获取 Release 里的 `hd-upscale.zip`，**不要手动解压**，直接把整个 zip 发给 AI 并说「请安装这个技能」即可。
