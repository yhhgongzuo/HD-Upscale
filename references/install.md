# 安装适配（给 Agent）

本包是完整离线后处理资源包，不包含生图服务、账号、API 密钥或付费额度。资源和官方出处见 `assets/resources.json`；完整性见 `MANIFEST.sha256.json`。需要能解压 ZIP、运行程序、写入工作/缓存目录的宿主。

## 安装入口

通过宿主已提供的技能安装机制将 `ahui-hd-upscale/` 注册到其技能目录。不要给未知平台编造安装位置。Codex 可使用其当前技能安装器；其他 Agent 使用其真实支持的技能导入机制。如果仅能读取说明而不能安装持久技能，明确报告未完成安装。

Windows x64：

```powershell
& '<技能目录>\launch.cmd' doctor
```

macOS / Linux（不依赖系统 Python；系统需有标准 sh、tar，以及 sha256sum 或 shasum）：

```sh
sh '<技能目录>/launch.sh' doctor
```

启动器所有参数均为独立参数；路径必须正确引用。启动器从本包解出匹配资源，不联网下载。默认缓存写入用户缓存目录，可通过 `AHUI_HD_CACHE` 指定已有可写位置。不要修改全局 Python、PATH 或其他应用配置。

`doctor` 未提供能力记录时，运行离线后处理自检后仍返回 `ready=false`、`installation_status=needs_image_provider_verification`；这不是安装成功。Agent 先通过当前工具目录、提供商文档和可用的只读鉴权检查核实图像编辑能力，再在本次工作目录生成记录文件：

```json
{
  "host": "实际宿主名称或 unknown",
  "image_edit": true,
  "result_access": true,
  "provider": "实际工具名或接口提供商",
  "evidence": "实际核实依据：支持参考图的工具参数、登录/权限状态及结果获取方法"
}
```

禁止为了通过检查虚填 true；脚本只校验记录，无法代替 Agent 探测外部生图工具。记录不得包含密钥。再运行 `doctor --capabilities '<记录路径>'`，通过且注册成功后完成安装。若权限无法只读核实，报告待验证，不以付费请求偷偷探测。首次用户真实生成成功后才记录端到端通过。

## 安装后的固定引导与触发登记

完成能力核实、自检和宿主技能注册后，仅给用户这句简单引导：

“安装完成！上传图片后，说‘用阿辉的高清放大’，我就会帮你处理。”

触发短句统一为“用阿辉的高清放大”。保持自动调用开启，保留 SKILL.md 描述中的短句；宿主支持触发词或别名注册时使用该短句。以后收到这句话且有明确图片时，直接执行本技能；缺图时只索要图片，补图后继续。不要求用户输入英文技能名、美元符号或 Skill 字样。仅引用或讨论指令不触发处理。

若宿主无法持久注册技能或在新聊天加载技能，应如实说明；不要把本轮读取成功当成所有后续聊天已注册。

## 运行环境边界

- Windows：本包内置 x64 原版资源；不宣称 ARM 原生支持，ARM 机器需另行验证其 x64 兼容运行环境。
- macOS：提供 Intel、Apple Silicon 官方 ART 及匹配 Python/Pillow。DMG 文件名标注的是官方构建环境，不直接当成最低系统版本。使用系统 hdiutil 只读挂载并复制应用到本技能缓存，不写入 /Applications。不删除 quarantine，不关闭 Gatekeeper；系统拦截时如实反馈，由用户通过系统允许的方式处理。
- Linux：提供 glibc x64/ARM64 原生发行包；musl/Alpine、缺少图形相关动态库、noexec 沙箱等不能保证运行。使用官方 CLI 包装器，无需打开图形窗口；自检失败时报告缺失依赖，不宣称已完成安装。
- 平台既无程序执行权限、也无可用外部处理服务时，反馈缺少图片后处理能力。生图 API 不能替代 ART 运行环境。
- Mac/Linux 的资源完整性已检查不等于本包已完成这些平台的实机图像验证。用户环境 `doctor` 必须通过。发布时实际验证范围见 `验证说明.md`。

## 命令

启动器后可接：`doctor`、`plan --width W --height H [--mode universal|doubao]`、`run --input PATH --output PATH [--mode universal|doubao]`、`preview --before PATH --after PATH --output PATH`。豆包专用尺寸计算：`size --image PATH --model MODEL --tier auto`，直接复用旧版函数；通用模型禁止使用该命令套算尺寸。

单张任务工作目录应唯一。输出 PNG/HTML 不覆盖已有文件。预览不依赖外部网络，跨机器保存时使用页面中的内嵌成品下载，不依赖原电脑 file:// 路径。
