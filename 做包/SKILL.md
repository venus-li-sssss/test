---
name: 做包
description: 'Use this skill when the user wants to build FOTA upgrade packages (做包/差分包/差分升级包/差分/全量包/整包/app整包/全系统完整包/最小系统包/miniFota/升级包制作/刷机包/回滚包). 覆盖 aboot/ASR 机型（QDM568/ML307C/ASR1605、QDM562/九号/ASR1601-1605 等）：config 必须依据版本包 ZIP 里的 partition.bin 自动生成（不写死地址）、"全量包"=app整包（config_app 单镜像）不是全镜像包、全量包不挑设备当前版本（差分/最小系统包才挑，别答反）、工具目录必须纯 ASCII、adiff/FBFMake 输出是 GBK、产物必须独立自检（体积/整张镜像是否嵌入/FBF 头记录条数）。含 make_full_fbfmake.py / make_diff_fbfmake.py / fota_builder.py / make_config.py / verify_fbf_package.py / fetch_tools.py（工具从飞书云盘「做升级包」目录下载）。Triggers: 做包, 差分包, 差分升级包, 全量包, 整包, app整包, 全系统完整包, 最小系统包, miniFota, 升级包制作, fota_builder, make_config, make_full_fbfmake, make_diff_fbfmake, verify_fbf_package, fetch_tools, 做包工具下载, 下载adiff, 下载FBFMake, 升级包工具在哪, fbfmake, FBFMake, adiff, fbf_dfota, system_patch, partition.bin, 版本依赖, 全量包能升哪些版本, nOfImages, QDM568做包, QDM562做包.'
version: 3.2.0
---

# 做包（FOTA 升级包制作）

覆盖 **aboot/ASR 系列机型**的 FOTA 升级包制作：给**版本包 ZIP**（差分包要旧在前、新在后）+ 包型，
产出 **全量包(app整包) / 差分包 / 最小系统包**。

核心三句话：
1. **config 从版本包的 `partition.bin` 推出来**（绝不写死地址）；
2. **包型决定 config 里有几项、a\ 里放几个文件** —— 这一步最容易错，见 §0。
3. **包型还决定"挑不挑版本"**：**全量包不挑设备当前版本，差分/最小系统包才挑**（见 §0.1，最容易答反）。

---

## 0. 先定包型（30 秒，别跳；2026-09-22 错在这里被打回）

> 血泪案例：把"全量包"理解成"把全部镜像打进去"，用 `-f config` 出了 4,059,136 B / 3,223,552 B 的包，
> 工具照样报 `successfully`、`nOfImages = 3`，**交付后被现场打回（刷不过去）**。真正的全量包只有几百 KB。

| 包型 | 谁要它 | config | a\ 放什么 | 体积量级 | 命令 |
|---|---|---|---|---|---|
| **全量包 = app 整包**（现场口语的"全量包"） | 全量升级测试 | **1 项：客户 app 镜像**（`config_app`；地址 = 该 `cust` 分区 Start） | **只放那张 app 镜像** | **≈ app + 9 KB**（几百 KB） | `FBFMake -o <名>.bin -f config_app -a a -b a` |
| **差分包**（升级/回滚） | 版本间升级 | **多项**：`system.img` + 客户 app + `fota.json` 声明的独立容器（如 `ext_gnss.img`） | a\=新、b\=旧，**同名文件** | 变化块量级（几十 KB~MB） | `FBFMake -f config -d 0x10000 -a a -b b -o fbf_dfota.bin -q` |
| **最小系统包** | 最小系统升级 | 由 adiff 命令行给 | — | — | `adiff system_old.img system_new.img out.bin -a1 <客户分区> <app.bin> -m` |
| 全系统完整包 | ASR README §3 的**另一套**方案 | 全部镜像 | 全部镜像 | ≈ 镜像总和（3~4 MB） | `FBFMake -o fbf.bin -f config -a a -b a` |

**三把尺子**（对不上就是包型错了 —— 比翻文档快）：
1. **体积**：全量包 ≈ app 镜像 + 9 KB；≈ 镜像总和 ⇒ 那是全系统完整包。
2. **a\ 里有几个文件**：全量包 a\ 里**只有 1 个** app 文件。
3. **工具日志 `nOfImages`**：全量包 = **1**；差分/QDM562 三镜像 = 3。

### 0.1 包型 × 版本依赖（最容易答反的一条；2026-09-29 答反过被用户纠正）

| 包型 | 挑设备当前版本吗 | 为什么 |
|---|---|---|
| **全量包（app 整包）** | **不挑** | 整分区覆盖写：设备上是 751、V03 还是出厂版都一样刷。包里连"你现在是什么版本"这个字段都没有（§2.6 可拿产物验证） |
| 差分包 | **挑** | adiff 基于两个**具体**版本算出来，A→B 与 B→A 是两个不同的包 |
| 最小系统包 | **挑** | 同上，必须给定 old/new 两个版本包 |

全量包**唯一**的边界不是"版本"，而是"**范围**"：它只带 `customer_app` 一个分区、**不带 system**。
所以"升完能不能跑"取决于目标 app 与设备 system 是否配套：

- 这版只改了 app（`system.img` 与设备侧一致）→ 全量包够了，**任意版本直接升** ✅
- 这版同时改了 `system.img`，而设备还是老 system → 需要连 system 一起升 → 这时才换带 system 的包
  （差分/最小系统/全系统完整包）

> **别**说成"跨 system 版本就得改用差分/最小系统包" —— 那等于把"全量包不挑版本""差分挑版本"讲反了，
> 而且逻辑上正好相反：差分才要求两端版本明确。被问到时要问的是"**system 变没变、要不要一起升**"，
> 不是"全量包支不支持某个旧版本"。

**动手前先找"基准件"对形状**（现场现成的东西比文档权威）：
- `D:\make_fota\quanliang\quanliang\` = 历史**全量包**目录：`config` 只 1 项 `customer_app.bin @0x91D000`，
  `a\` 只有 `customer_app.bin`(136,320 B)，`fbf.bin` = **145,408 B**。
- `D:\make_fota\CHAFEN\CHAFEN\` = 历史**差分包**目录：`a\`/`b\` 各一个 `customer_app.bin`。
- `D:\work\QDM562\` = 近期成品：`qdm562_diff\`（双向差分包，3 镜像 config）、`appfull_pkg\`（全量包=app 整包）。

**文档出处**：Quectel《升级包制作方法及模组FOTA升级说明》（就在工具目录 `D:\work\package\fota_tool\`）
第 2 节「app 整包升级」= 现场的"全量包"；ASR《ASR1601 FOTA》§2 全系统差分 / §3 全系统完整包 / §4 最小系统 / §5 PRO 方案。

---

## 1. 四条铁律（都踩过）

1. **工具目录 / 工作目录必须纯 ASCII。** `FBFMake_CF_V1.6-150.exe` 是 ANSI 程序，路径含中文会弹模态框
   `Unable to open file: ...\????\...` 并**永久卡住等人点"确定"**（进程 idle、CPU 0、无日志）。
   实测：同一份文件同一个 exe，ASCII 目录 1 秒出包，中文目录卡死 10 分钟。`adiff.exe` 无此问题。
2. **config 必须依据版本包里的 `partition.bin` 生成**：不许照抄文档示例、不许沿用工具目录里写死的 `config_app`。
   地址写错 = 差分写到错误分区（有破坏风险），且分区表随 SDK/机型变（`0x002D7000` 换个版本就不是它了）。
3. **不许"跑通了就算"**：每个包都要 ①产物非空 ②每项地址与 `partition.bin` 交叉核对 ③**体积/文件数与包型对得上（§0 三把尺子）**
   ④生成的 `config*` + `分区表_layout_*.txt` 落到输出目录可追溯。
4. **先对基准件再动手**（§0）：包型判错时工具不会报错，只会交出一个"看着挺像"的错包。

---

## 2. 原理：config 从哪来

### 2.1 分区表格式（BTPA）

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

### 2.2 谁才是"固件镜像"

- `flash` = 通道（qspi / spi…）；`group` = 总表；`ubi`/`raw` = 普通/裸分区；
- **`part` / `cust` = 容器分区**（里面还能再分子分区）→ 这才是可做 FOTA 的"整包镜像"；
- 容器里的子分区（raw，如 `ptable/rd/cp/dsp/rfbin/btlst/btbin`、`cc1161w_*/cc0058q_*`）
  **跟着容器一起升级，不要在 config 里单列**；
- `Image_Flash_Entry_Address` = 该分区**在它所在 flash 里的 `Start`**（**不是 `vStart`**）；
- 同机型 Start/Size 基本都是 `0x1000`(4K) 整数倍（NOR/QSPI 扇区粒度），顺序紧排，最后一项通常正好顶到 flash 容量。

### 2.3 config 项数规则（决定包型的就这一条）

| 机型 | 全量包（app 整包）config | 差分包 config |
|---|---|---|
| QDM568 / ML307C | 1 项：`user_app.bin` @0x002D7000 | `system.img` + `user_app.bin`（adiff 命令行给，不用 config） |
| QDM562 / 九号 | 1 项：`customer_app.bin` @0x00322000 | 3 项：`system.img@0x00016000` + `customer_app.bin@0x00322000` + `ext_gnss.img@0x00030000` |

- 差分里的 `ext_gnss.img` 来自**包内 `fota.json` 声明**（独立 `part` 容器，spi 通道），脚本自动纳入；
- `customer_app` 是 `type=cust`，**必须显式写进差分 config**（README §4.2.5：客户 app 分区一旦用于 FOTA，
  固件必须入包，否则有破坏该分区的风险）；`0x322000` 是被钉死的锚点（`secdat` 固定 0x312000，system 变大由 `reserved` 吸收）。

### 2.4 两个实机分区表（案例）

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

**案例 B：QDM562 / 九号（ASR1601/1605 4M，带外挂 GNSS）**

| 分区 | type | Start | 备注 |
|---|---|---|---|
| system | part | 0x00016000 | 含 ptable/rd/cp/dsp/rfbin/btlst/btbin 子分区 |
| reserved | raw | 0x002D4000 | 弹性区（system 变大它就变小） |
| secdat | raw | 0x00312000 | |
| **customer_app** | **cust** | **0x00322000** | 客户分区 |
| **ext_gnss** | **part** | **0x00030000** | 外挂 SPI flash，装 cc1161w_*/cc0058q_* 两颗 GNSS 固件 |

> 永远"先看 `partition.bin`，再决定 config 有几项、每项什么地址"，**不要背数字**。

### 2.5 取 config 的工具

```bash
python scripts/make_config.py <版本包.zip>                    # 全候选镜像的 config（差分用）
python scripts/make_config.py <版本包.zip> --app-only         # 只输出客户 app 分区（全量包用）
python scripts/make_config.py <版本包.zip> --list             # 只打印分区表 + 包内镜像清单
python scripts/make_config.py <版本包.zip> --diff <已有config> # 与现有 config 对账
```

- 自动处理**外层 zip → 内层装载包**（如 `ML307C_APP.zip`），跳过 `*_Source.zip`；只输出"包内真的有镜像文件"的分区；
- 命名兜底：`user_app.bin / ML307C_APP.bin / customer_app.bin` 都认。

### 2.6 FBF 产物的头结构（拿产物就能回答"包型/版本依赖"）

`FBFMake` 产物 = **8192 B 头** + 镜像数据（实测单镜像整包 `QDM562_full_762.bin`：镜像首字节在偏移 **8192**）。
头里只有 magic + 每张镜像的地址/长度/校验记录，**没有任何版本号、产品名**：

| 观测点 | 实测（762 / V03 / 751 三版一致） | 用途 |
|---|---|---|
| 头内 ASCII 串 | 单镜像整包：**只有 `Marvell_FBF`**（差分包头里会多出几条由块数据凑成的伪 ASCII 短串） | 头里没有产品名/版本号 ⇒ **包本身不携带"设备当前版本"，整包不挑版本**（§0.1） |
| 头内 `\d+\.\d+\.\d+` 样式串 | 无 | 同上 |
| 每个 `Image_Flash_Entry_Address` | 以 u32 LE 出现在头里，呈记录形态（762 在偏移 348；其 `addr+8`、`addr+12` 为 `0xFFFFFFFF`） | 数"呈记录形态"的地址条数 ↔ config 项数 / `nOfImages` 对账（全量包 1 条、QDM562 差分 3 条） |

> ⚠️ **别拿头里的 `0xFFFFFFFF` 槽判"整包 vs 差分"**：实测双向差分包的记录同样呈现 `0xFFFFFFFF`
> （2026-09-29 差点这么写进脚本）。判整包 vs 差分只有一条硬证据 —— **整张镜像是否连续嵌在产物里**，
> 加上体积、`nOfImages`。

`scripts/verify_fbf_package.py` 已内置这段解析（打印头内 ASCII 串/版本号样式串、每个地址的记录形态命中、
并可 `--expect-images N` 断言条数）。

---

## 3. 命令与参数

| 包类型 | 工具 | 关键命令 | 产物 |
|---|---|---|---|
| 差分包（全量差分） | adiff | `adiff.exe -p system_old.img system_new.img system_patch.bin -a1 user_app user_app_old.bin user_app_new.bin -l fsall -s 20000` | 1 个 bin |
| **全量包（app 整包）** | FBFMake | `FBFMake_CF_V1.6-150.exe -o <名>.bin -f config_app -a a -b a` | 1 个 bin |
| 最小系统包 | adiff | `adiff.exe system_old.img system_new.img system_patch.bin -a1 user_app user_app.bin -m` | 1 个（`-m` 合并）或 `_1`/`_2` 两个 |
| 全系统完整包 | FBFMake | `FBFMake_CF_V1.6-150.exe -o fbf.bin -f config -a a -b a` | 整镜像（≠上表第 2 行） |
| 全系统差分（老方案） | FBFMake | `FBFMake_CF_V1.6-150.exe -f config -d 0x10000 -a a -b b -o fbf_dfota.bin -q` | 只比 a/b 不同处 |

**参数要点**

| 参数 | 含义 / 坑 |
|---|---|
| `-p` | PRO 方案。**SDK008 起 system.img 用 LZMA 压缩**，仍用老的全系统差分方案包会很大 → 必须 `-p` |
| `-a1/-a2` | 挂客户分区：`<分区名> <文件>`（mini）/ `<分区名> <旧> <新>`（PRO）。分区名从分区表取，**别写死**；最多 2 个 |
| `-l fs\|fp\|fsall` | 差分包放哪：`fp`=fota_pkg、`fs`=文件系统（备份仍走 fota_pkg）、**`fsall`=连备份也走文件系统（adiff≥5.7.1）**。机型 `fota_pkg` 只有 4K/未启用时**必须 `fsall`** |
| `-s 20000` | 备份空间预留（**16 进制**，0x20000=128K），必须 64K 整数倍、最小 0x20000，文档建议别改 |
| `-m` | 两个升级包（最小系统差分 + 非最小系统全包）合并成一个 |
| `-u updater.bin` | 把 updater 拼进包（无 updater 分区的机型用） |
| `-ext <partition>` | 借 reserved 后面的分区做 FOTA 空间；**要求地址与 reserved 连续**，且该分区固件必须入包 |
| `-npop` / `-spidsp` / `-spirf` / `-spicp2` / `-indeprf` | 掉电保护、DSP/RF/CP 在外挂 flash、RF 独立分区（adiff 5.7.x+） |
| `-d 0x10000` / `-q` | 老方案的切块大小（64K）/ fast 模式 |

**Flash 侧约束**：`fota_param` ≥ 12K（最好正好 12K）；`fota_pkg` 要放包就得够大（PRO 方案 fp>2M、fs>1M）；
`-l fsall` 可完全绕开 `fota_pkg`。

---

## 3.9 工具与文档从哪来（2026-11-13 新增）

exe 体积大，**不进 git 仓库**，统一放**飞书云盘**，用 `feishu-software-download` skill 的应用身份拉取：

- 云盘目录：**做升级包** → <https://quectel.feishu.cn/drive/folder/HVQwfjtCGlXh85dBLhmcIPtWnBf>
  （`folder_token = HVQwfjtCGlXh85dBLhmcIPtWnBf`，机器可读，免扫码）
- 目录内容：

| 文件 | 大小 | 用途 |
|---|---|---|
| `adiff.exe` | 248,320 B（5.8.6） | 差分 / 最小系统包 |
| `FBFMake_CF_V1.6-150.exe` | 6,467,072 B | FBF 打包（全量包 / 全系统完整包 / 全系统差分） |
| `config` | 578 B | **多镜像** config 模板（差分 / 全系统完整包） |
| `config_app` | 177 B | **单镜像** config 模板（全量包 = app 整包） |
| `fbfmake.bat` / `fbfmake_fast.bat` / `fbfmake_full.bat` | — | 差分 / fast / 全系统完整包 |
| `README.docx` | 109,239 B | FBFMake 说明 |
| `升级包制作方法及模组FOTA升级说明.txt` | 2,236 B | 官方《升级包制作方法及模组FOTA升级说明》 |

一键落地（推荐，下载 + 大小校验 + ASCII 路径校验）：

```bash
python scripts/fetch_tools.py                      # 默认落到 D:\work\package\fota_tool
python scripts/fetch_tools.py --dest D:\fota_tool  # 自定义（必须纯 ASCII）
python scripts/fetch_tools.py --list               # 只列云盘里有什么（带 file_token）
python scripts/fetch_tools.py --check              # 只校验本地工具齐不齐 / 大小对不对
```

手动方式：`python <feishu-software-download>/scripts/feishu_dl.py tree --folder HVQwfjtCGlXh85dBLhmcIPtWnBf`，
再 `feishu_dl.py dl <file_token> --out <ASCII目录>\<文件名>`。

> ⚠️ 两条硬约束：① 落点**必须纯 ASCII**（§1.1，`fetch_tools.py` 会先拦下来）；
> ② 云盘里的 `config` / `config_app` 只是**模板参考**，正式做包一律用 `scripts/make_config.py`
> 依据版本包 `partition.bin` 重新生成（§1.2）—— 照抄模板地址就是 §5.4 那个坑。

## 4. 落地执行（按机型/包型选一条）

工具目录统一用 **`D:\work\package\fota_tool\`**（纯 ASCII；含 `adiff.exe` 5.8.6、`FBFMake_CF_V1.6-150.exe`、
`config`（多镜像）/`config_app`（单镜像）、`fbfmake_fast.bat`（差分）/`fbfmake_full.bat`（全系统完整包）、两份文档）。
本地没有就用 `python scripts/fetch_tools.py` 从云盘一键拉（见 §3.9）。

### 4.1 QDM562 / ql-sdk —— **全量包 = app 整包**（默认该做的那个）

```bash
python scripts/make_full_fbfmake.py --pkg <版本包.zip> --label V03 --mode app -o <输出目录> --prefix QDM562
# --mode app（默认）= 现场"全量包"：config_app 单镜像 -> <输出目录>\<prefix>full_<label>.bin
# --mode full       = ASR README §3 全系统完整包（全镜像）—— 会打 WARN，不是现场的全量包
```

实跑基线（2026-09-23，config_app 1 项 `customer_app.bin @0x00322000`）：

| 版本包 | 产物 | 大小 = app + 头 | md5 | 日志 |
|---|---|---|---|---|
| `…QDM562CNAK_01.001.01.001_V03` | `QDM562_full_V03.bin` | 417,792 B（409,108 + 8,684） | `b8832ed0a69df97a808ad678c455abec` | `nOfImages = 1` |
| `…QDM562_NINEBOT_01.001.01.004_751` | `QDM562_full_751.bin` | 348,160 B（339,836 + 8,324） | `f576ef626e8b0ab28efdfacc65fbc37b` | `nOfImages = 1` |
| `…QDM562CNAK_01.001.01.001_762` | `QDM562_full_762.bin` | 424,960 B（416,364 + 8,596） | `0dae1e24577a1fbb234ccd3fa029ffd6` | `nOfImages = 1` |

基线件都在 `D:\work\QDM562\appfull_pkg\`（三版整包 + `_src\*\customer_app.bin` + `qdm562_diff\` 双向差分包），
新包做完直接拿它 `--src` 对形状。

输出目录同时落：`config_app_<label>`、`分区表_layout_<label>.txt`、`做包记录_<label>.txt`、`_src\<label>\`、`full_work\<label>\`（可复现）。

### 4.2 QDM562 / ql-sdk —— **差分包（双向）**

```bash
python scripts/make_diff_fbfmake.py --old <旧版本包.zip> --new <新版本包.zip> [-o 输出目录]
python scripts/make_diff_fbfmake.py --old A.zip --new B.zip --only up|rb   # 只出升级包 / 只出回滚包
python scripts/make_diff_fbfmake.py --old A.zip --new B.zip --prefix QDM562 --naming target
```

- 镜像来源：`system.img` + 客户 app（自动找 `customer_app.bin / user_app.bin / ML307C_APP.bin / cusapp.bin / app.bin`）；
  额外容器（`ext_gnss.img`）按包内 `fota.json` 自动纳入（`--no-extra` 关、`--images a,b,c` 手工指定）；
- 目录模型 `exe / config / a\ / b\` 同目录，a\=更新后、b\=更新前（**必须与 config 里 `Image_Path` 同名**）；
- 命令 `FBFMake_CF_V1.6-150.exe -f config -d 0x10000 -a a -b b -o fbf_dfota.bin -q`，交换 a\/b\ 再跑 = 回滚包；
- **收包必查：两个方向的 md5 必须不同**（FBFMake 不覆盖已存在输出，方向搞混会拿到同一个文件）。
- 实跑基线（751↔V03）：升级 1,440,768 B / 回滚 1,047,552 B。

### 4.3 QDM568 / ML307C —— 一键三包

- 主脚本 `D:\work\QDM568\fota_tool\fota_builder.py`（= 本 skill `scripts/fota_builder.py` 快照），输出
  `D:\work\QDM568\fota_tool\result\{旧}_to_{新}_{时间戳}\`；
- 版本包结构：外层 zip → `ML307C_APP.zip`（`partition.bin`/`system.img`/`user_app.bin`）+ `ML307C_APP.bin`（客户 app 镜像）
  + `ML307C_APP_Source.zip`（**跳过**）+ `DBG/config/partition/ASR1605_*.json`（布局，可交叉校验）：

```bash
cd /d D:\work\QDM568\fota_tool && python -c "
import sys; sys.path.insert(0, '.')
from fota_builder import make_diff_package_full, make_full_package, make_minimal_package
print(make_diff_package_full(r'<旧ZIP>', r'<新ZIP>', r'D:/work/QDM568/fota_tool/result'))
print(make_full_package(r'<旧ZIP>', r'<新ZIP>', r'D:/work/QDM568/fota_tool/result'))
print(make_minimal_package(r'<旧ZIP>', r'<新ZIP>', r'D:/work/QDM568/fota_tool/result'))
"
```

- 也可跑 GUI：`python D:\work\QDM568\fota_tool\fota_builder.py`；
- 实跑基线（V02→V04）：差分包 22,536/14,344 B；全量包 123,904/135,168 B（**≈ user_app + 9 KB**）；最小系统包 632,932/624,740 B。

### 4.4 adiff 路线（差分 / 最小系统，手工）

- 差分包：`-p`（PRO）+ `-a1 <客户分区> <旧> <新>` + `-l fsall -s 20000`；
- 最小系统包：去掉 `-p`，`-a1 <分区> <新文件>` + `-m`（合并为一个包；不带 `-m` 出 `_1` 最小系统差分 / `_2` 非最小系统全包）；
- 双向包（A→B 与 B→A）就调两次、参数对调。

---

## 5. 避坑清单（按踩坑顺序）

1. **「全量包」≠「把全部镜像打进去」**（2026-09-22 被打回）：全量包 = app 整包 = `config_app` 单镜像、
   a\ 只放那张 app 镜像、体积 ≈ app + 9 KB。做成 `-f config` 的全镜像包（≈镜像总和、`nOfImages=3`）设备侧全量升级**刷不过去**。见 §0。
2. **bat 名字会骗人**：`fbfmake_full.bat` 只是 `-a a -b a`；**包里装几个镜像完全由 config 有几项决定**。
   同一个 bat 配单镜像 config 就是全量包，配多镜像 config 就是全系统完整包。
3. **中文路径 → FBFMake 弹框卡死**（§1.1）。工具目录/工作目录一律 ASCII。
4. **config 写死地址**：必须从版本包 `partition.bin` 取；改版后地址会漂（`0x324000`→`0x322000`；
   文档截图 / 工具目录残留 config / 历史模板里的 `0x91D000`、`0x24000` 都是别的布局，**不能照抄**）。
5. **版本标签只看中段会重名**：`..._01.001.01.006_V02/_V04` 只取中段 → A→B 与 B→A **互相覆盖**。
   优先取尾部 `_V04` / `_BETA260820`；仍相同加 `_OLD/_NEW`。
6. **GBK 输出用 utf-8 解 → 死锁**：`subprocess(text=True)` 默认 utf-8，遇 GBK 会崩读取线程、管道写满 → 进程永久卡住。
   必须 `encoding='gbk', errors='replace'`。
7. **弹模态框 = 卡死**：给外部工具加超时（180~300s），超时后**读它的对话框文本**当报错原因
   （`EnumWindows` 找 `class=#32770` + 子控件 Static 文本）。
8. **FBFMake 不覆盖已存在输出**：跑前先删旧产物，否则报 `successfully` 但拿到上一次的文件
   （自检：两方向 md5 必须不同）。
9. **`a\` 只放 config 里列到的镜像**：残留会让工具读到不该有的文件；跑前重建 `a\`。
10. **别把"版本依赖"讲反**（2026-09-29 被用户纠正）：全量包 = 整分区覆盖 ⇒ **不挑设备当前版本**；
    挑版本的是差分/最小系统包（基于两个具体版本算出来）。老话"app 整包要求 OS 一致"说的是**包的范围**：
    整包只带 `customer_app`、不带 system，所以"这版同时改了 system 而设备还是老 system"要靠带 system 的包。
    写成"全量包要求设备已经是某个版本"就是错的（§0.1）。
11. **`fota_pkg` 太小**：机型常见 4K 且未启用 → 差分包必须 `-l fsall`，不要指望往 fota_pkg 里塞。
12. **`-ext` 的分区必须与 reserved 地址连续**，且该分区固件要入包。
13. **升级器/引导不动**：`bootloader/preboot/flasher/partition.bin` 属烧录阶段；
    `nvm/erase_rd/factory/fota_param` 升级时是"擦除"不是差分。
14. **FBF 路线 config 必须与 exe 同目录**（FBFMake 只读 exe 自己目录的 config），否则会读到残留的旧 config，
    报 `a\app.bin ... is not exist for Differential Upgrading.`。做法：把 exe+config 拷到干净工作目录、`cwd=` 该目录调用。

---

## 6. 排错表

| 现象 | 原因 | 处理 |
|---|---|---|
| **包做好了但设备刷不过去** | **包型错**（把全镜像全系统完整包当全量包） | 按 §0 改 `--mode app`（config_app 单镜像）；比体积 ≈ app+9KB |
| 全量包体积 ≈ 3~4 MB | 同上（用了 `-f config`） | 换 `-f config_app`，a\ 只留 app 镜像 |
| FBFMake 卡住、CPU 0、无输出 | 弹模态框（多为 `Unable to open file: ...\????\...`） | 换 ASCII 路径；用脚本读弹窗文本 |
| `Unable to open file: a\user_app.bin` 但文件在 | 路径含中文（ANSI 转换变 `????`） | 目录改 ASCII |
| A→B / B→A 只剩一个文件 / md5 相同 | 版本标签相同→重名覆盖；或旧产物没删 | 用尾部标签 + `_OLD/_NEW`；跑前删旧产物 |
| `adiff` 输出未生成/为空 | 参数错（如 `-l fsall` 不被支持）、分区名错 | 看 adiff 日志尾部；确认 adiff ≥5.7.1 |
| 差分包比预期大 | LZMA 的 system 走了 mini 方案 | 加 `-p` |
| 报空间不足 | 备份 size 不够 / 切割块太大 | 调 `-s` 或 `-ext` 借分区 |
| 客户 app 分区被破坏 | 做 FOTA 时没把该分区固件入包 | `-a1 <客户分区> <文件>` 必须带 |
| 打包成功但设备升级失败（地址类） | config 地址与设备实际分区表不符 | 用设备侧分区表（aboot 界面/`partition.bin`）复核 |
| 被问"全量包不是不管什么版本都能升吗？" | 对，全量包**不挑版本**；老文案把"包的范围（只带 app 不带 system）"错写成了"版本依赖" | 按 §0.1 答：不挑版本的是全量包，挑版本的是差分/最小系统包；要确认的是 system 变没变 |
| 想确认产物是整包还是差分、有没有版本门槛 | 靠看头/体积，没走硬检查 | `python scripts/verify_fbf_package.py --pkg <产物> --src <镜像目录> --addr <0x地址> --expect-images 1`；整张镜像连续嵌入 = 整包；头内无版本号样式串 = 无版本门槛 |

---

## 7. 交付自检清单

- [ ] **包型对**：全量包体积 ≈ app + 9 KB、`nOfImages = 1`、a\ 只有 1 个 app 文件；
      差分/QDM562 三镜像包体积为变化块量级、`nOfImages = 3`
- [ ] 每项 `_Image_Flash_Entry_Address` 都等于该版本包 `partition.bin` 里同名分区的 **Start**（非 vStart）
- [ ] 输出目录含 `config_app`（或 `config`）+ `分区表_layout_*.txt`，能追溯 config 来源
- [ ] 用 `scripts/verify_fbf_package.py` 独立自检：头 `Marvell_FBF`、地址在包内、**每张镜像整张连续嵌入**
      （防"其实是差分/被截断"）；`--expect-images 1`（全量包）/ `3`（QDM562 差分）对账头内记录条数
- [ ] 被问"这包能升哪些版本"时，用 §0.1 的口径回答（不挑版本的是全量包），别照抄老文案
- [ ] 双向包两个方向 md5 不同、大小合理（同板同布局时应接近）
- [ ] 日志/记录落在输出目录（`做包记录_*.txt` 或 `build_log_*.txt`）

---

## 附：scripts

| 文件 | 用途 |
|---|---|
| `scripts/make_config.py` | 通用 config 生成器：版本包 ZIP → 分区表 → config（`--list` / `--app-only` / `--diff` / `-o`） |
| `scripts/make_full_fbfmake.py` | **全量包**：`--mode app`（默认）= 现场"全量包"= app 整包（config_app 单镜像）；`--mode full` = ASR README §3 全系统完整包（非现场全量包） |
| `scripts/make_diff_fbfmake.py` | QDM562/ql-sdk FBFMake **双向**差分包（升级包 + 回滚包），自带 ASCII 校验/分区表 config/弹窗检测 |
| `scripts/fota_builder.py` | QDM568/ML307C 一键三包（差分包/全量包/最小系统包）+ GUI，含 ASCII/GBK/超时/弹窗/标签 全套加固 |
| `scripts/verify_fbf_package.py` | 产物独立自检：头 `Marvell_FBF` / 地址是否进包 / **整张镜像是否连续嵌入**（判"真全量 vs 其实是差分"）/ 头结构解析（头内 ASCII 串与版本号样式串、每个地址的记录形态命中、`--expect-images N` 断言条数、`--dump-header N` 排错） |
| `scripts/fetch_tools.py` | 从飞书云盘「做升级包」目录拉工具集到本地 ASCII 目录（`--list` / `--check` / `--force`），依赖 feishu-software-download |

五个脚本内置同一套 BTPA 分区表解析逻辑（`make_full_fbfmake.py` 直接 import `make_diff_fbfmake.py`）；
`TOOL_DIR` 默认 `D:\work\package\fota_tool`（可用 `--exe` 覆盖）。
