---
name: 做包
description: 'Use this skill when the user wants to build FOTA upgrade packages (做包/差分包/差分升级包/全量包/整包/app整包/最小系统包/miniFota/升级包制作). 覆盖 aboot 机型（QDM568/ML307C/ASR1605、QDM562/九号/ASR1601-1605 等）：config 必须依据版本包 ZIP 里的 partition.bin 自动生成（不写死地址）、工具目录必须纯 ASCII、adiff/FBFMake 输出是 GBK。含一键三包脚本 fota_builder.py 与独立 config 生成器 make_config.py。Triggers: 做包, 差分包, 差分升级包, 全量包, 整包, app整包, 最小系统包, miniFota, 升级包制作, fota_builder, make_config, fbfmake, FBFMake, adiff, fbf_dfota, system_patch, partition.bin, QDM568做包, QDM562做包.'
version: 2.0.0
---

# 做包（FOTA 升级包制作）

覆盖 **aboot/ASR 系列机型**的 FOTA 升级包制作：给**版本包 ZIP**（旧在前、新在后）+ 包类型，
产出 **差分包 / 全量包(app整包) / 最小系统包**。核心是**从版本包里取分区表来生成 config**。

---

## 0. 三条铁律（先看，都踩过）

1. **工具目录 / 工作目录必须纯 ASCII。**
   `FBFMake_CF_V1.6-150.exe` 是 ANSI 程序，**路径含中文会弹模态框**
   `Unable to open file: ...\????\...` **然后永久卡住等人点"确定"**（进程 idle、CPU 0、无任何日志）。
   实测：同一份文件、同一个 exe，纯 ASCII 目录 1 秒出包，中文目录卡死 10 分钟。`adiff.exe` 无此问题。
2. **config 必须依据版本包里的 `partition.bin` 生成**，不许照抄文档示例、不许沿用工具目录里写死的 `config_app`。
   地址写错 = 差分会写到错误分区（有破坏风险）；且分区表随 SDK/机型变（同一个 0x002D7000 换个版本就不是它了）。
3. **不许"跑通了就算"**：每个包都要 ①输出文件非空校验 ②与分区表交叉校验 ③把生成的 config / 分区表落到输出目录可追溯。

---

## 1. 通用原理：config 从哪来

### 1.1 分区表格式（BTPA）

`partition.bin` = 8 字节头（`BTPA`） + N × **68 字节**记录：

| 偏移 | 长度 | 内容 |
|---|---|---|
| 0 | 32 | name（ascii，\0 填充） |
| 32 | 16 | type（`group/flash/ubi/part/raw/cust`） |
| 48 | 4 | start（u32，LE） |
| 52 | 4 | size（u32，LE） |
| 56 | 4 | vstart（u32，LE） |
| 60 | 4 | vsize（u32，LE） |
| 64 | 4 | 保留 |

### 1.2 谁才是"固件镜像"

- `flash` = 通道（qspi / spi…）；`group` = 总表；`ubi`/`raw` = 普通/裸分区；
- **`part` / `cust` = 容器分区**（里面还能再分子分区）→ 这些才是可做 FOTA 的"整包镜像"；
- 容器里的子分区（raw，如 `ptable/rd/cp/dsp/rfbin/btlst/btbin`、`cc1161w_*/cc0058q_*`）
  **跟着容器一起升级，不要在 config 里单列**；
- `Image_Flash_Entry_Address` = 该分区**在它所在 flash 里的 `Start`**（**不是 `vStart`**）；
- 同一机型的所有 Start/Size 基本都是 `0x1000`(4K) 整数倍（NOR/QSPI 扇区粒度），且**顺序紧排**，最后一项通常正好顶到 flash 容量。

### 1.3 两个实机案例

**案例 A：QDM568 / ML307C（ASR1605 4M，qspi 4MB）**

| 分区 | type | Start | Size |
|---|---|---|---|
| bootloader | ubi | 0x00000000 | 0x00014000 |
| system | part | 0x00014000 | 0x002C1000 |
| reserved | raw | 0x002D5000 | 0x00002000 |
| **user_app** | **cust** | **0x002D7000** | 0x00080000 |
| nvm | raw | 0x00357000 | 0x00080000 |
| userdata / fota_param | part / raw | 0x003D7000 | 0x00003000 |
| updater | raw | 0x003DA000 | 0x00020000 |
| factory / factory_a | part / raw | 0x003FA000 | 0x00006000 |

→ app 整包 config：`1_Image_Path = user_app.bin` / `1_Image_Flash_Entry_Address = 0x002D7000`

**案例 B：QDM562 / 九号（ASR1601/1605 4M，带外挂 GNSS）**

| 分区 | type | Start | 备注 |
|---|---|---|---|
| system | part | 0x00016000 | 含 ptable/rd/cp/dsp/rfbin/btlst/btbin 子分区 |
| reserved | raw | 0x002D4000 | 弹性区（system 变大它就变小） |
| secdat | raw | 0x00312000 | |
| **customer_app** | **cust** | **0x00322000** | 客户分区；= 0x16000+0x2BE000+0x3E000+0x10000 |
| **ext_gnss** | **part** | **0x00030000** | 外挂 SPI flash 上，装 cc1161w_*/cc0058q_* 两颗 GNSS 固件 |

→ 这个机型 config 是**三项** `system.img / customer_app.bin / ext_gnss.img`：
来源 = 烧录包 `fota.json` 声明的 FOTA 镜像（system、ext_gnss）+ 客户分区 customer_app
（README §4.2.5 明确：客户 app 分区一旦用于 FOTA，**固件必须加入升级包，否则有破坏该分区的风险**）。
`0x322000` 是被"钉死"的锚点：`secdat` 固定 0x312000，system 变大时由 `reserved` 吸收，客户区不跟着漂。

> 两者都是"先看 `partition.bin`，再决定 config 有几项、每项什么地址"，**不要背数字**。

### 1.4 取 config 的工具

`scripts/make_config.py`（本 skill 自带，与一键脚本同一套解析逻辑）：

```bash
python scripts/make_config.py <版本包.zip>                       # 输出全部固件镜像的 config
python scripts/make_config.py <版本包.zip> --app-only            # 只输出客户 app 分区（app 整包用）
python scripts/make_config.py <版本包.zip> --list                # 只打印分区表 + 包内镜像清单
python scripts/make_config.py <版本包.zip> --diff <已有config>    # 与现有 config 对账
```

- 自动处理**外层 zip → 内层装载包**（如 `ML307C_APP.zip`），并跳过 `*_Source.zip`；
- 只输出"包内真的有镜像文件"的分区；
- 命名兜底：`user_app.bin / ML307C_APP.bin / customer_app.bin` 都认。

---

## 2. 包类型与命令（对照《升级包制作方法及模组FOTA升级说明》+ ASR 原厂 README）

| 包类型 | 工具 | 关键命令 | 产物 |
|---|---|---|---|
| **差分包**（全量差分升级） | adiff | `adiff.exe -p system_old.img system_new.img system_patch.bin -a1 user_app user_app_old.bin user_app_new.bin -l fsall -s 20000` | 1 个 bin |
| **全量包**（app 整包） | FBFMake | `FBFMake_CF_V1.6-150.exe -o system_patch.bin -f config_app -a a -b a` | 1 个 bin |
| **最小系统包** | adiff | `adiff.exe system_old.img system_new.img system_patch.bin -a1 user_app user_app.bin -m` | 1 个（`-m` 合并）或 `_1`/`_2` 两个 |
| 全系统完整包 | FBFMake | `FBFMake_CF_V1.6-150.exe -o fbf.bin -f config -a a -b a` | 整镜像 |
| 全系统差分（老方案） | FBFMake | `FBFMake_CF_V1.6-150.exe -f config -d 0x10000 -a a -b b -o fbf_dfota.bin -q` | 只比 a/b 不同处 |

**参数要点**

| 参数 | 含义 / 坑 |
|---|---|
| `-p` | PRO 方案。**SDK008 起 system.img 用 LZMA 压缩**，仍用老的全系统差分方案包会很大 → 必须 `-p` |
| `-a1/-a2` | 挂客户分区：`<分区名> <文件>`（mini）/ `<分区名> <旧> <新>`（PRO）。分区名从分区表取，**别写死**；最多 2 个 |
| `-l fs\|fp\|fsall` | 差分包放哪：`fp`=fota_pkg、`fs`=文件系统（备份仍用 fota_pkg）、**`fsall`=连备份也走文件系统（adiff≥5.7.1）**。机型 `fota_pkg` 只有 4K/未启用时**必须 `fsall`** |
| `-s 20000` | 备份空间预留（**16 进制**，0x20000=128K），必须 64K 整数倍、最小 0x20000，文档建议别改 |
| `-m` | 两个升级包（最小系统差分 + 非最小系统全包）合并成一个 |
| `-u updater.bin` | 把 updater 拼进包（无 updater 分区的机型用） |
| `-ext <partition>` | 借 reserved 后面的分区做 FOTA 空间；**要求地址与 reserved 连续**，且该分区固件必须入包 |
| `-npop` / `-spidsp` / `-spirf` / `-spicp2` / `-indeprf` | 掉电保护、DSP/RF/CP 在外挂 flash、RF 独立分区（adiff 5.7.x+） |
| `-d 0x10000` / `-q` | 老方案的切块大小（64K）/ fast 模式 |

**Flash 侧约束**：`fota_param` ≥ 12K（最好正好 12K）；`fota_pkg` 要放包就得够大（PRO 方案 fp>2M、fs>1M）。
`-l fsall` 可以完全绕开 `fota_pkg`。

---

## 3. 落地执行

### 3.1 QDM568 / ML307C —— 一键三种包（主路径）

- 工具目录：**`D:\work\package\fota_tool\`**（纯 ASCII！含 `adiff.exe` 5.8.6 / `FBFMake_CF_V1.6-150.exe` / `config_app`）
- 主脚本：`D:\work\QDM568\fota_tool\fota_builder.py`（本 skill `scripts/fota_builder.py` 为同一份快照）
- 输出：`D:\work\QDM568\fota_tool\result\{旧版本}_to_{新版本}_{时间戳}\`

版本包结构（QDM568）：

```
QDM568_..._V04.zip
├─ ML307C_APP.zip        ← 装载包：partition.bin / system.img / user_app.bin
├─ ML307C_APP.bin        ← 客户 app 镜像（= 装载包里的 user_app.bin）
├─ ML307C_APP_Source.zip ← 源码包，做包要跳过
└─ DBG/config/partition/ASR1605_SINGLE_SIM_FLASH_LAYOUT_4M.json  ← 布局（可交叉校验）
```

```bash
cd /d D:\work\QDM568\fota_tool && python -c "
import sys; sys.path.insert(0, '.')
from fota_builder import make_diff_package_full, make_full_package, make_minimal_package
print(make_diff_package_full(r'<旧ZIP>', r'<新ZIP>', r'D:/work/QDM568/fota_tool/result'))
print(make_full_package(r'<旧ZIP>', r'<新ZIP>', r'D:/work/QDM568/fota_tool/result'))
print(make_minimal_package(r'<旧ZIP>', r'<新ZIP>', r'D:/work/QDM568/fota_tool/result'))
"
```

也可跑 GUI：`python D:\work\QDM568\fota_tool\fota_builder.py`。
**实跑基线（V02→V04）**：差分包 22,536/14,344 B；全量包 123,904/135,168 B；最小系统包 632,932/624,740 B。

### 3.2 ASR / QueCopen 机型 —— FBFMake + adiff 手工/脚本

典型工具目录（如 `D:\work\package\fota_tool`、`\tool` 子目录）：

```
tool/
├─ adiff.exe                      # 差分包 / 最小系统包
├─ FBFMake_CF_V1.6-150.exe        # 全量包 / 全系统差分
├─ config（多镜像）/ config_app（单镜像：客户 app）
├─ a\  （升级后镜像）  b\（升级前镜像）
└─ fbfmake_fast.bat / fbfmake_full.bat
```

流程：
1. 从**新版本包**解出镜像（`system.img` / 客户 app 镜像 / 其它容器镜像），用 `make_config.py` 生成 config；
2. **a\ = 升级后**、**b\ = 升级前**，文件**必须与 config 里 `Image_Path` 同名**（缺一个工具就失败）；
3. 差分包 `fbfmake_fast.bat`（`-a a -b b`）；全量包 `fbfmake_full.bat`（`-a a -b a`，同一目录）；
4. 产物交给设备端 FOTA 测试（AT 命令 / 平台下发）。

### 3.3 差分包与最小系统包（adiff 路线）

- 差分包：`-p`（PRO）+ `-a1 <客户分区> <旧> <新>` + `-l fsall -s 20000`；
- 最小系统包：去掉 `-p`，`-a1 <分区> <新文件>` + `-m`（合并为一个包；不带 `-m` 则出 `_1`（最小系统差分）和 `_2`（非最小系统全包））；
- 需要双向包（A→B 与 B→A）就调两次、参数对调。

### 3.4 QDM562 / ql-sdk —— FBFMake 双向差分包（升级包 + 回滚包）

用 `scripts/make_diff_fbfmake.py`（551 行，已内置 ASCII 校验 / 分区表生成 config / 弹窗检测 / 双向出包）：

```bash
python scripts/make_diff_fbfmake.py --old <旧版本包.zip> --new <新版本包.zip> [-o 输出目录]
python scripts/make_diff_fbfmake.py --old A.zip --new B.zip --only up     # 只出升级包
python scripts/make_diff_fbfmake.py --old A.zip --new B.zip --only rb     # 只出回滚包
python scripts/make_diff_fbfmake.py --old A.zip --new B.zip --app user_app.bin --prefix QDM562
```

- 镜像来源：版本包里的 `system.img` + 客户 app 镜像（默认自动在 `customer_app.bin / user_app.bin / ML307C_APP.bin / cusapp.bin / app.bin` 里找）；
- 额外容器（如 `ext_gnss.img`）按包内 `fota.json` 声明自动纳入，`--no-extra` 可关掉；
- 目录模型：`exe / config / a\ / b\` 同目录，a\ = 更新后、b\ = 更新前**（必须和 config 里 `Image_Path` 同名）**；
- 命令：`FBFMake_CF_V1.6-150.exe -f config -d 0x10000 -a a -b b -o fbf_dfota.bin -q`，交换 a\/b\ 再跑一次 = 回滚包；
- 产物默认 `<旧包目录>\diff_out`，文件名带新旧标签区分方向。

---

## 4. 避坑清单（按踩坑顺序）

1. **中文路径 → FBFMake 弹框卡死**（见 §0.1）。工具目录/工作目录一律 ASCII。
2. **config 写死地址**：必须从版本包 `partition.bin` 取；改版后地址会漂（案例 B 里 `0x324000`→`0x322000`）。
3. **版本标签只看中段会重名**：`..._01.001.01.006_V02/_V04` 只取 `01.001.01.006` → A→B 与 B→A **互相覆盖**。
   应优先取尾部 `_V04` / `_BETA260820`；仍相同就加 `_OLD/_NEW`。
4. **GBK 输出用 utf-8 解 → 死锁**：`subprocess(text=True)` 默认 utf-8，遇到 GBK 输出会崩读取线程，
   输出多时管道写满 → 进程永久卡住。必须 `encoding='gbk', errors='replace'`。
5. **弹模态框 = 卡死**：给外部工具加超时（如 180s），超时后**读它的对话框文本**当报错原因（`EnumWindows` 找 `class=#32770` + 子控件 Static 文本）。
6. **a\ 残留**：FBFMake 跑前会重建 `a\`；跑完清掉拷进去的镜像（`b\` 只在需要差分时创建）。
7. **app 整包要求 OS 一致**：`system.img` 必须相同、只有 app 不同；不一致就别用整包，改差分包/最小系统包。
8. **`fota_pkg` 太小**：机型常见 4K 且 `disable` → 差分包必须 `-l fsall`，不要指望往 fota_pkg 里塞。
9. **`-ext` 的分区必须与 reserved 地址连续**，且该分区固件要入包（比如 `-ext customer_app -a1 customer_app customer_app.bin`）。
10. **升级器/引导不动**：`bootloader/preboot/flasher/partition.bin` 属于烧录阶段；`nvm/erase_rd/factory/fota_param` 升级时是"擦除"不是差分。
11. **FBF 路线里 config 最好与 exe 同目录**：有案例表明 FBFMake 只认 exe 自己目录下的 config——
    否则会读到残留的旧 config，报 `a\app.bin ... is not exist for Differential Upgrading.`。
    保险做法：把 config 放到工具目录、用**相对文件名** + `cwd=工具目录` 调用（QDM568 流程用绝对路径也验证可行，但别赌）。

---

## 5. 排错表

| 现象 | 原因 | 处理 |
|---|---|---|
| FBFMake 卡住、CPU 0、无输出 | 弹模态框（多为 `Unable to open file: ...\????\...`） | 换 ASCII 路径；用脚本读弹窗文本 |
| `Unable to open file: a\user_app.bin` 但文件在 | 路径含中文（ANSI 转换变 `????`） | 目录改 ASCII |
| A→B / B→A 只剩一个文件 | 版本标签相同→重名覆盖 | 用尾部标签 + `_OLD/_NEW` |
| `adiff 输出文件未生成/为空` | 参数错（如 `-l fsall` 不被支持）、分区名错 | 看 adiff 日志尾部；确认 adiff ≥5.7.1 |
| 差分包比预期大 | LZMA 的 system 走了 mini 方案 | 加 `-p` |
| 报空间不足 | 备份 size 不够 / 切割块太大 | 调 `-s`（调小切割块）或 `-ext` 借分区 |
| 客户 app 分区被破坏 | 做 FOTA 时没把该分区固件入包 | `-a1 <客户分区> <文件>` 必须带 |
| 打包成功但设备升级失败 | config 地址与设备实际分区表不符 | 用设备侧分区表（aboot 界面/`partition.bin`）复核 |

---

## 6. 交付自检清单

- [ ] 输出目录含 `config_app`（或 `config`）+ `分区表_layout_*.txt`，能追溯 config 来源
- [ ] 日志里出现 `分区表来源: ...\partition.bin` 与 `客户 app 分区: xxx start=0x...`
- [ ] 每个包都有 `输出校验通过: ... (N bytes)`，N > 0
- [ ] 全量包模式有 `system.img 一致 (md5 ...)`
- [ ] `build_log_*.txt` 落在输出目录
- [ ] 双向包（A→B / B→A）两个文件名不同、大小合理

---

## 附：scripts

| 文件 | 用途 |
|---|---|
| `scripts/make_config.py` | 通用 config 生成器：版本包 ZIP → 分区表 → config（`--list` / `--app-only` / `--diff` / `-o`） |
| `scripts/fota_builder.py` | QDM568/ML307C 一键三包（差分包/全量包/最小系统包）+ GUI，含 ASCII/GBK/超时/弹窗/标签 全套加固 |
| `scripts/make_diff_fbfmake.py` | QDM562/ql-sdk FBFMake **双向**差分包（升级包 + 回滚包），自带 ASCII 校验/分区表 config/弹窗检测 |

三者内置同一套 BTPA 分区表解析逻辑；`fota_builder.py` 与 `make_diff_fbfmake.py` 的 `TOOL_DIR` 默认 `D:\work\package\fota_tool`（可按需 `--exe` 覆盖）。
