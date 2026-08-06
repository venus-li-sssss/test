---
name: pyinstaller-exe-packager
description: 将 Python 脚本快速打包为 Windows 单文件 exe（PyInstaller onefile），嵌入固化在本 skill 内的版本信息文件（references/version_info.txt，已自带，不依赖外部路径）。流程极简：pip 安装 pyinstaller 后直接执行 pyinstaller 命令，不做源码改写/冻结态修补/yml 复制/冒烟测试等额外操作。触发词：打包exe、生成exe、PyInstaller、打包脚本、onefile、嵌入版本信息、出包、构建exe。
---

# PyInstaller 单文件 exe 打包器（极简版）

把 Python 脚本打包成 Windows 单文件 exe，并嵌入版本信息。**只做打包这一件事，不做任何多余操作。**

## 何时使用
- 用户要求“打包 exe / 生成 exe / 打包脚本 / PyInstaller / onefile / 嵌入版本信息 / 出包 / 构建exe”。

## 版本信息：用 skill 自带的副本，不依赖外部路径
版本信息已固化在本 skill 内，位置（与 SKILL.md 同级）：
```
<skill>/references/version_info.txt
```
绝对路径示例：`C:\Users\venus.li\.workbuddy\skills\pyinstaller-exe-packager\references\version_info.txt`
打包时取其绝对路径传给 `--version-file` 即可。该文件随 skill 一起保存，**不依赖任何外部文件**（外部那份 `D:/work/AI生成测试用例/OPEN API/file_version_info.txt` 可能随时被删，不要再去读它）。

## 打包流程（agent 直接执行，不要绕弯）
使用受管 Python 3.13 的构建 venv；若不存在则先创建：
```
"C:\Users\venus.li\.workbuddy\binaries\python\versions\3.13.12\python.exe" -m venv "C:\Users\venus.li\.workbuddy\binaries\python\envs\default"
```

步骤 1 — 安装 pyinstaller（以及脚本运行所需的依赖，按需追加在后面）：
```
"C:\Users\venus.li\.workbuddy\binaries\python\envs\default\Scripts\pip.exe" install pyinstaller <其他依赖...>
```

步骤 2 — 直接执行打包（onefile，并嵌入 skill 自带的版本信息文件）：
```
"C:\Users\venus.li\.workbuddy\binaries\python\envs\default\Scripts\pyinstaller.exe" --onefile --version-file "<skill>/references/version_info.txt" --distpath "<脚本所在目录>/dist" "<脚本路径>"
```
（`<skill>/references/version_info.txt` 换成上面给出的绝对路径。）

## 注意事项
- 路径含空格时（如脚本目录有空格）：建议在 PowerShell 中执行，或始终用引号包裹完整绝对路径，避免 bash/git-bash 把空格路径拆成多段参数导致 `unrecognized arguments` 报错。
- Windows沙箱环境兼容：打包前先设置环境变量 `PYINSTALLER_DISABLE_SAFE_DELETE=1` 绕过安全删除限制，避免因回收站不可用导致打包失败。
- **不做以下多余操作**（用户明确要求“没什么其他的东西”）：
  - 不修改用户源码、不做冻结态 `sys.frozen` 路径修补、不生成 `.bak` 备份；
  - 不复制 `aily_models.yaml` 等配置文件（如需随 exe 部署，让用户自己把 yaml 放到 `dist` 目录）；
  - 不做构建后冒烟测试 / HTTP probe；
  - 不处理 UPX 等额外开关。
- 产物：`<脚本所在目录>/dist/<脚本名>.exe`（单文件）。
- 如需改版本号/产品名，直接编辑本 skill 的 `references/version_info.txt` 即可，不要去动外部那份文件。
