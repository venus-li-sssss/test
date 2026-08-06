---
name: qdisk-quectel
version: 1.0.0
description: 移远网盘 (Quectel Netdisk / qdisk.quectel.com) 下载工具。把网盘中的文件或整个目录下载到本地指定位置。触发词：移远网盘、Quectel网盘、qdisk、下载网盘、网盘下载。
type: tool
---

# 移远网盘下载工具 (qdisk-quectel)

通过 `qdisk.quectel.com` 的 REST 接口，把网盘里的文件 / 文件夹下载到本地任意目录。
无需手动处理登录时的 RSA 加密 —— 认证走 `refresh_token` 换取 `access_token` 的流程，脚本会自动续期并缓存。

## 适用场景
- “把移远网盘里某个目录下载到 D:/xxx”
- “下载网盘里某个文件/某个项目的最新版本”
- “列一下网盘某个路径下有什么”

## 文件位置
- 主程序：`~/.workbuddy/skills/qdisk-quectel/qdisk.py`（纯标准库，无需 pip 安装）
- 令牌缓存：`~/.workbuddy/skills/qdisk-quectel/.token_cache.json`（含凭据，勿外传）

## 认证（首次使用一次即可）
登录网盘网页版后，打开浏览器 DevTools → Application → Cookies，找到：
- `quectel_refresh_token` —— 刷新令牌（**推荐**，最耐用，会自动续期）
- `quectel_token` —— 形如 `bearerxxxx-xxxx`，去掉 `bearer` 前缀即为 access_token

然后执行（任选其一，推荐 refresh_token）：
```
python qdisk.py auth --refresh-token <quectel_refresh_token 的值>
python qdisk.py auth --token <quectel_token 去掉 bearer 前缀>
```
之后脚本会缓存令牌，access_token 过期前自动用 refresh_token 刷新，长期可用。
也可通过环境变量覆盖：`QUECTEL_REFRESH_TOKEN`、`QUECTEL_TOKEN`。

## 常用命令
```bash
# 1) 列出某路径内容
python qdisk.py ls --path "部门文件/IKOTEK/Project"

# 2) 树形查看结构（不下载）
python qdisk.py tree --path "部门文件/IKOTEK/Project"

# 3) 下载单个目录到本地（仅该目录下的文件）
python qdisk.py download --path "部门文件/IKOTEK/Project/ODM Project Files/SWE/external/MOB/QDM559/STM32G0B0/app" --output D:/qdisk/app

# 4) 递归下载整个目录树
python qdisk.py download --path "部门文件/IKOTEK/Project" --output D:/qdisk --recursive

# 5) 只下载文件名包含某关键字的文件
python qdisk.py download --path "部门文件/IKOTEK/Project" --output D:/qdisk --only "QDM559_STM32G0B0_APP"

# 6) 扁平输出：直接落到 --output，不再套用末级路径名作为子目录
python qdisk.py download --path "部门文件/IKOTEK/Project/ODM Project Files/SWE/external/MOB/QDM559/STM32G0B0/app" --output "D:/work/QDM559/version" --only "V20" --flat

# 7) 下载后自动解压 .zip（解压到与 zip 同名的子目录）
python qdisk.py download --path "部门文件/IKOTEK/Project/ODM Project Files/SWE/external/MOB/QDM559/STM32G0B0/app" --output "D:/work/QDM559/version" --only "V20" --flat --extract
```

### 典型工作流：下载并解压某个版本包到指定目录（一条命令搞定）
默认下载会在 `--output` 下再套一层末级路径名子目录（如 `version/app/V20.zip`），且不会自动解压。
实际常常希望 zip 直接落在目标目录、并解压成同名子文件夹（与现有版本包目录结构一致）。
用 `--flat --extract` 即可，无需再手动移动 / 解压：

```bash
# 正式版（app 目录）
python qdisk.py download \
  --path "部门文件/IKOTEK/Project/ODM Project Files/SWE/external/MOB/QDM559/STM32G0B0/app" \
  --output "D:/work/QDM559/version" --only "V20" --flat --extract

# 自升级版（app/TEMP 目录）
python qdisk.py download \
  --path "部门文件/IKOTEK/Project/ODM Project Files/SWE/external/MOB/QDM559/STM32G0B0/app/TEMP" \
  --output "D:/work/QDM559/version" --only "BETA260724" --flat --extract
```

执行后 `D:/work/QDM559/version/` 下会得到：
- `QDM559_STM32G0B0_APP_01.001.01.001_V20.zip`（zip 本体）
- `QDM559_STM32G0B0_APP_01.001.01.001_V20/`（解压内容：SteelDustApp.bin/.hex/.ota.bin）

> 不同版本在网盘不同子目录时，分别带对应 `--path` 跑一次即可；`--only` 用版本关键字（如 `V20`）精确命中单个文件，避免误下整目录。
> 若需核对客户版本号，可在解压后的 `.hex` 中搜 ASCII（如 `023E`），在 `.bin` 中搜字节 `02 3E`。

路径以空间根目录名开头：`公司文件` / `部门文件` / `我的文件`，后面用 `/` 接子目录。
也可直接给 `--folder-id` + `--space-id` + `--space-type` 跳过路径解析。

## 关键 API（已验证，供参考 / 排错）
- 认证：`POST https://sso-web.quectel.com/api/uaa/oauth/token`
  - refresh 模式：`grant_type=refresh_token&refresh_token=<RT>&client_id=quectel&client_secret=quectel`（form-urlencoded）
  - 返回的 `access_token` 用于网盘接口，请求头固定为 `Authorization: bearer<access_token>`（**bearer 后无空格**）
- 路径 → folderId：`POST https://qdisk.quectel.com/api/disk/v1/file/qry/queryFolderIdByPath`  body `{"path":"部门文件/..."}`
- 文件夹详情（取 spaceId/spaceType）：`GET /api/disk/v1/file/qry/deatil/<folderId>`
- 列文件：`POST /api/disk/v1/file/qry/file/page`  body `{"spaceId","fileId":<folderId>,"pageNumber":1,"pageSize":200,"validSpaceTypes":[...]}`
- 获取下载签名：`POST /api/disk/v1/file/qry/sign`  body 含 `bucket:disk, dataAction:DOWNLOAD, fileId, fileKey, fileName, folderId, spaceId, spaceType`
  - 返回 `data.url` 为 `fs-oss.quectel.com` 的预签名 S3 地址（AWS4-HMAC-SHA256，有效期 6h）
- 实际下载：直接 `GET` 上面的 `data.url`（预签名 URL 自带签名，无需额外鉴权头）
- 网盘接口需带的自定义头：`quectel-version: mxz`、`hiddenmsg: false`、`loading: false`、`origin`、`referer`

## 注意事项
- 预签名 URL 有效期约 6 小时；脚本对大目录会逐个文件实时签名再下载，不受影响。
- 默认下载会在 `--output` 下以路径末级文件夹名建子目录；加 `--flat` 可改为直接落到 `--output`；`--recursive` 会保留完整目录结构。
- 加 `--extract` 时，每个下载到的 `.zip` 会自动解压到与其同名的子目录（已做 zip slip 路径穿越防护）。
- 文件名中的 `\ / : * ? " < > |` 会被替换为 `_`。
- 若认证失效（refresh_token 过期），重新执行 `auth --refresh-token <新RT>` 即可。
