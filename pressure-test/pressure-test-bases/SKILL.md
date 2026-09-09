# pressure-test-bases — 压力测试基础类模板

提供压力测试中常用的硬件/协议基础类模板和示例，每个基础类独立负责一个领域。

**核心要求：所有涉及数据收发的基础类（Serial/CAN/CMD/Jlink RTT），必须内置独立的日志输出能力——后台线程实时读取，按行写 `[时间戳][TX]` / `[时间戳][RX]` 到专用日志文件，用于事后分析问题。**

## 基础类列表

| 基础类 | 职责 | 日志输出 | 覆盖的自动化类型 |
|--------|------|----------|-----------------|
| **Serial** | 串口通信 | 后台线程 + serial_log_{port}_{timestamp}.txt | 串口 |
| **CAN** | CAN 总线通信（基于 ZLGCAN DLL） | 后台线程 + can_log_{timestamp}.txt | CAN 总线 |
| **CMD** | CMD 子进程输出监控 | 后台线程 + cmd_log_{timestamp}.txt | CMD 串口/子进程 |
| **AT** | AT 指令交互（串口，send+check模式） | 依赖 Serial 日志 | AT 指令 |
| **Jlink** | Jlink 调试接口（pylink RTT + 命令行复位） | 后台线程 + jlink_log_{timestamp}.txt | 固件调试/重启 |
| **File** | 日志文件管理（logging 封装，支持滚动切割） | 自身就是日志 | 日志记录 |
| **Relay** | 继电器控制（串口，NC/NO 双模式） | 无（仅发送指令） | 电源控制 |
| **Platform API** | 平台 API 调用 | 无（HTTP） | 接口自动化 |

## 基础类设计原则

1. **独立可测试**：每个基础类可以单独实例化和测试，不依赖其他基础类
2. **单一职责**：每个类只负责一个硬件或协议领域
3. **统一接口**：推荐使用 `open()/close()` 管理连接，`read()/write()` 或 `send()/recv()` 管理数据
4. **异常处理**：每个方法应妥善处理异常，返回标准状态码或抛出明确的异常
5. **日志输出（强制）**：Serial/CAN/CMD/Jlink RTT 等涉及数据收发的基础类，必须内置独立的日志输出：
   - `open()` 时接收 `log_dir` 参数，创建专用日志文件
   - 启动后台 daemon 线程持续读取数据
   - 解码后按 `\n` 分割，逐行写 `[时间戳][RX]数据` 到日志文件
   - TX 时写 `[时间戳][TX]数据` 到日志文件
   - 时间戳格式：`[%Y-%m-%d %H:%M:%S.%f]`
   - 参考 QDM551 发布压力脚本的线程模型

## 日志输出设计规范

### 通用模式

```python
import threading
import datetime

class BaseClient:
    def __init__(self):
        self._thread_flag = False
        self._read_thread = None

    def open(self, log_dir=None):
        # 1. 打开连接
        # 2. 如果 log_dir 不为 None，初始化日志文件
        if log_dir:
            self.log_file = os.path.join(log_dir, f"xxx_log_{timestamp}.txt")
            self._thread_flag = True
            self._read_thread = threading.Thread(target=self._read_loop, daemon=True)
            self._read_thread.start()

    def close(self):
        self._thread_flag = False
        if self._read_thread:
            self._read_thread.join(timeout=1)
        # 关闭连接

    def _write_log(self, msg):
        """写日志，自动带时间戳"""
        if not self.log_file:
            return
        ts = datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S.%f]")
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(f"{ts}{msg}\n")
        except Exception:
            pass

    def _read_loop(self):
        """后台线程：持续读取，按行写日志"""
        while self._thread_flag:
            try:
                if 有数据可读:
                    data = 读取并解码()
                    for line in data.split("\n"):
                        line = line.strip("\r")
                        if line:
                            self._write_log(f"[RX]{line}")
                else:
                    time.sleep(0.05)
            except Exception:
                time.sleep(0.1)
```

### 日志文件命名规范

| 基础类 | 日志文件名 |
|--------|-----------|
| Serial | `serial_log_{port}_{timestamp}.txt` |
| CAN | `can_log_{timestamp}.txt` |
| CMD | `cmd_log_{timestamp}.txt` |
| Jlink RTT | `jlink_log_{timestamp}.txt` |

### 日志格式

```
[2026-09-03 13:47:15.033096][TX]fw
[2026-09-03 13:47:15.147670][RX]========================================
[2026-09-03 13:47:15.147670][RX]  Firmware Version
[2026-09-03 13:47:15.147670][RX]========================================
```

- TX 标记：`[TX]数据`（不带空格）
- RX 标记：`[RX]数据`（不带空格，每行一条）
- 不额外添加分隔线
- 不做数据过滤，所有数据原样保留

### 日志轮转管理（强制）

> **核心要求**：所有基础类的日志文件必须支持按大小自动切割，防止日志文件无限增长。
> 参考 QDM551 发布压力脚本的 RotatingFileHandler 实现。

每个基础类在 `_write_log` 中必须检查日志文件大小，超过 `max_bytes`（默认 10MB）时自动重命名当前日志并创建新文件：

```python
def _write_log(self, msg):
    """写日志，自动带时间戳，支持按大小轮转"""
    if not self.log_file:
        return
    ts = datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S.%f]")
    line = f"{ts}{msg}\n"
    try:
        # 检查文件大小，超过上限则轮转
        if os.path.exists(self.log_file) and os.path.getsize(self.log_file) > self._max_bytes:
            self._rotate_log()
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass

def _rotate_log(self):
    """轮转日志文件：重命名当前日志，创建新文件，保留所有轮转文件"""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = os.path.splitext(self.log_file)[0]
    rotated_name = f"{base_name}_rotated_{timestamp}.txt"
    try:
        os.rename(self.log_file, rotated_name)
    except Exception:
        pass
```

初始化时添加轮转参数：

```python
def __init__(self, ..., max_bytes=10*1024*1024):
    self._max_bytes = max_bytes         # 单个日志文件最大字节数，默认 10MB
```

或者在 `open()` 中接收轮转配置：

```python
def open(self, log_dir=None, max_bytes=10*1024*1024):
    if log_dir:
        self._max_bytes = max_bytes
        # ... 初始化日志文件
```

## 基础类模板示例

### Serial 基础类模板

> **核心要求**：后台线程实时读取串口，按行写 RX 日志；TX 时写 TX 日志。
> 参考脚本：QDM551发布压力_V05.py

```python
import serial
import threading
import datetime
import time
import os

class SerialClient:
    """串口通信客户端，后台线程实时记录串口日志"""

    def __init__(self, port, baudrate=115200, timeout=3):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None
        self.log_file = None
        self._thread_flag = False
        self._read_thread = None

    def open(self, log_dir=None):
        """打开串口，可选初始化日志并启动后台读取线程"""
        self.ser = serial.Serial(self.port, self.baudrate, timeout=0.1)
        if log_dir:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.log_file = os.path.join(log_dir, f"serial_log_{self.port}_{timestamp}.txt")
            self._write_log(f"串口 {self.port} 已打开, 波特率: {self.baudrate}")
            self._thread_flag = True
            self._read_thread = threading.Thread(target=self._read_loop, daemon=True)
            self._read_thread.start()

    def close(self):
        """关闭串口，停止后台线程"""
        self._thread_flag = False
        if self._read_thread:
            self._read_thread.join(timeout=1)
        self._write_log(f"串口 {self.port} 关闭")
        if self.ser and self.ser.is_open:
            self.ser.close()

    def _write_log(self, msg):
        """写日志，自动带时间戳"""
        if not self.log_file:
            return
        ts = datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S.%f]")
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(f"{ts}{msg}\n")
        except Exception:
            pass

    def _read_loop(self):
        """后台线程：持续读取串口，按行写日志"""
        while self._thread_flag:
            try:
                if self.ser and self.ser.is_open and self.ser.in_waiting:
                    data = self.ser.read(self.ser.in_waiting).decode("utf-8", errors="replace")
                    for line in data.split("\n"):
                        line = line.strip("\r")
                        if line:
                            self._write_log(f"[RX]{line}")
                else:
                    time.sleep(0.05)
            except Exception:
                time.sleep(0.1)

    def write(self, data):
        """发送数据，记录 TX 日志"""
        if isinstance(data, str):
            self._write_log(f"[TX]{data}")
            data = data.encode()
        else:
            self._write_log(f"[TX]{data.hex()}")
        return self.ser.write(data)

    def read(self, size=1024):
        return self.ser.read(size)

    def readline(self):
        return self.ser.readline()
```

### CAN 基础类模板（基于 ZLGCAN DLL）

> **核心要求**：后台线程持续读取 CAN 帧，逐帧写 RX 日志；send 时逐帧写 TX 日志。
> **核心依赖**：
> - **zlgcan.zip**（`references/zlgcan.zip`，47MB），首次使用时解压到脚本运行目录
> - **VC++ 2015-2019 runtime**：zip 内 `MSVBCRT.AIO.2019.10.19.X86_X64.exe`，需用户手动安装
> 参考脚本：551_OUT_TEST_V18.py、QDM551发布压力_V05.py

```python
from ctypes import *
import threading
import time
import os
import datetime

ZCAN_DEVICE_TYPE = c_uint
INVALID_DEVICE_HANDLE = 0
INVALID_CHANNEL_HANDLE = 0

ZCAN_USBCAN2          = ZCAN_DEVICE_TYPE(4)
ZCAN_USBCANFD_200U    = ZCAN_DEVICE_TYPE(41)
ZCAN_CANFDNET_200U_TCP = ZCAN_DEVICE_TYPE(48)

ZCAN_STATUS_OK      = 1
ZCAN_TYPE_CAN       = c_uint(0)
ZCAN_TYPE_CANFD     = c_uint(1)

class CANClient:
    """CAN 总线客户端，后台线程实时记录 CAN 日志"""

    def __init__(self, can_type=ZCAN_USBCAN2, can_rate=500000, chn=0):
        self.can_type = can_type
        self.can_rate = can_rate
        self.chn = chn
        self.network = (can_type.value >= 40)
        self.handle = None
        self.chn_handle = None
        self.zcanlib = None
        self.log_file = None
        self._thread_flag = False
        self._read_thread = None

    def open(self, log_dir=None):
        """打开 CAN 设备，可选初始化日志并启动后台读取线程"""
        from zlgcan.zlgcan_init import ZCAN, can_start
        self.zcanlib = ZCAN()
        self.handle = self.zcanlib.OpenDevice(self.can_type, self.chn, 0)
        if self.handle == INVALID_DEVICE_HANDLE:
            return (500, "Open Device failed")
        if self.network:
            self._set_value("work_mode", "1")
            self._set_value("local_port", "12345")
        else:
            self._set_rate(self.can_rate)
        self.chn_handle = can_start(self.zcanlib, self.handle, self.chn)
        if not self.chn_handle:
            return (500, "Start CAN failed")
        if self.network:
            time.sleep(3)
        # 初始化日志
        if log_dir:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.log_file = os.path.join(log_dir, f"can_log_{timestamp}.txt")
            self._write_log(f"CAN 已打开, 类型: {self.can_type.value}, 速率: {self.can_rate}")
            self._thread_flag = True
            self._read_thread = threading.Thread(target=self._read_loop, daemon=True)
            self._read_thread.start()
        return (200, "CAN opened successfully")

    def close(self):
        """关闭 CAN 设备"""
        self._thread_flag = False
        if self._read_thread:
            self._read_thread.join(timeout=1)
        if self.zcanlib and self.chn_handle:
            self.zcanlib.ResetCAN(self.chn_handle)
        if self.zcanlib and self.handle:
            self.zcanlib.CloseDevice(self.handle)

    def _write_log(self, msg):
        if not self.log_file:
            return
        ts = datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S.%f]")
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(f"{ts}{msg}\n")
        except Exception:
            pass

    def _read_loop(self):
        """后台线程：持续读取 CAN 帧，逐帧写日志"""
        while self._thread_flag:
            try:
                rcv_num = self.zcanlib.GetReceiveNum(self.chn_handle, ZCAN_TYPE_CAN)
                if rcv_num:
                    rcv_msg, rcv_num = self.zcanlib.Receive(self.chn_handle, rcv_num)
                    for i in range(rcv_num):
                        ts = rcv_msg[i].timestamp
                        can_id = hex(rcv_msg[i].frame.can_id)
                        dlc = rcv_msg[i].frame.can_dlc
                        eff = rcv_msg[i].frame.eff
                        rtr = rcv_msg[i].frame.rtr
                        data_hex = " ".join(
                            f"{rcv_msg[i].frame.data[j]:02X}"
                            for j in range(dlc)
                        )
                        self._write_log(
                            f"[RX]ts:{ts}, id:{can_id}, dlc:{dlc}, eff:{eff}, rtr:{rtr}, data:{data_hex}"
                        )
                else:
                    time.sleep(0.05)
            except Exception:
                time.sleep(0.1)

    def send(self, can_id, can_data, can_dlc=8, can_eff=1, can_rtr=0, transmit_type=0):
        """发送 CAN 帧，记录 TX 日志"""
        from zlgcan.zlgcan_init import ZCAN_Transmit_Data
        transmit_num = 1
        msgs = (ZCAN_Transmit_Data * transmit_num)()
        msgs[0].transmit_type = transmit_type
        msgs[0].frame.eff = can_eff
        msgs[0].frame.rtr = can_rtr
        msgs[0].frame.can_id = int(can_id, 16)
        msgs[0].frame.can_dlc = can_dlc
        can_data = can_data.replace(" ", "")[:2 * can_dlc].ljust(2 * can_dlc, "F")
        for j in range(can_dlc):
            msgs[0].frame.data[j] = int(can_data[j * 2:(j + 1) * 2], 16)
        self.zcanlib.Transmit(self.chn_handle, msgs, transmit_num)
        self._write_log(
            f"[TX]id:{can_id}, dlc:{can_dlc}, eff:{can_eff}, data:{can_data}"
        )
        return (200, f"id:{can_id}, dlc:{can_dlc}")

    def recv(self):
        """接收 CAN 帧（非阻塞），日志由后台线程记录"""
        rcv_num = self.zcanlib.GetReceiveNum(self.chn_handle, ZCAN_TYPE_CAN)
        if rcv_num:
            rcv_msg, rcv_num = self.zcanlib.Receive(self.chn_handle, rcv_num)
            frames = []
            for i in range(rcv_num):
                frames.append({
                    "timestamp": rcv_msg[i].timestamp,
                    "can_id": hex(rcv_msg[i].frame.can_id),
                    "can_dlc": rcv_msg[i].frame.can_dlc,
                    "eff": rcv_msg[i].frame.eff,
                    "rtr": rcv_msg[i].frame.rtr,
                    "data": "".join(
                        f"{rcv_msg[i].frame.data[j]:02X}"
                        for j in range(rcv_msg[i].frame.can_dlc)
                    )
                })
            return (200, frames)
        return (201, [])

    def recv_filter(self, filter_id, filter_cmd=None):
        """接收并过滤 CAN 帧"""
        status, data = self.recv()
        if status == 200 and data:
            matched = []
            for frame in data:
                if frame["can_id"] == hex(int(filter_id, 16)):
                    if filter_cmd is not None:
                        actual_cmd = int(frame["data"][:2], 16)
                        if actual_cmd == int(filter_cmd, 16):
                            matched.append(frame)
                    else:
                        matched.append(frame)
            if matched:
                return (200, matched)
        return (201, [])

    def in_waiting(self):
        try:
            return self.zcanlib.GetReceiveNum(self.chn_handle, ZCAN_TYPE_CAN)
        except:
            return 0

    def _set_value(self, key, value):
        p = self.zcanlib.GetIProperty(self.handle)
        res = self.zcanlib.SetValue(p, f"{self.chn}/{key}", str(value))
        self.zcanlib.ReleaseIProperty(p)
        return res

    def _set_rate(self, rate):
        return self._set_value("baud_rate", rate)
```

### CMD 基础类模板

> **核心要求**：后台线程持续读取子进程 stdout，按行写 RX 日志；write 时写 TX 日志。
> 参考脚本：QDM551发布压力_V05.py

```python
import subprocess
import threading
import datetime
import time
import os

class CMDClient:
    """CMD 子进程输出监控客户端，后台线程实时记录日志"""

    def __init__(self, command):
        self.command = command
        self.process = None
        self.log_file = None
        self._thread_flag = False
        self._read_thread = None

    def open(self, log_dir=None):
        """启动子进程，可选初始化日志并启动后台读取线程"""
        self.process = subprocess.Popen(
            self.command,
            shell=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0
        )
        if log_dir:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.log_file = os.path.join(log_dir, f"cmd_log_{timestamp}.txt")
            self._write_log(f"CMD 已启动: {self.command}")
            self._thread_flag = True
            self._read_thread = threading.Thread(target=self._read_loop, daemon=True)
            self._read_thread.start()

    def close(self):
        """终止子进程"""
        self._thread_flag = False
        if self._read_thread:
            self._read_thread.join(timeout=1)
        if self.process:
            self.process.terminate()

    def _write_log(self, msg):
        if not self.log_file:
            return
        ts = datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S.%f]")
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(f"{ts}{msg}\n")
        except Exception:
            pass

    def _read_loop(self):
        """后台线程：持续读取 stdout，按行写日志"""
        while self._thread_flag:
            try:
                if self.process and self.process.poll() is None:
                    char = self.process.stdout.read(1)
                    if char:
                        # 逐字节读取，按换行分割
                        self._write_log(f"[RX]{char.decode('utf-8', errors='replace')}")
                    else:
                        time.sleep(0.05)
                else:
                    time.sleep(0.1)
            except Exception:
                time.sleep(0.1)

    def write(self, data):
        """向子进程 stdin 发送数据，记录 TX 日志"""
        if isinstance(data, str):
            self._write_log(f"[TX]{data}")
            data = data.encode()
        else:
            self._write_log(f"[TX]{data.hex()}")
        self.process.stdin.write(data)
        self.process.stdin.flush()

    def read_line(self):
        """读取一行"""
        return self.process.stdout.readline()
```

### Platform API 基础类模板

```python
import requests

class PlatformClient:
    def __init__(self, base_url, username, password):
        self.base_url = base_url
        self.username = username
        self.password = password
        self.session = requests.Session()

    def login(self):
        resp = self.session.post(f"{self.base_url}/api/login", json={
            "username": self.username,
            "password": self.password
        })
        return resp.json()

    def query_device(self, device_key):
        resp = self.session.get(f"{self.base_url}/api/device/{device_key}")
        return resp.json()

    def check_online(self, device_key):
        resp = self.session.get(f"{self.base_url}/api/device/{device_key}/status")
        return resp.json().get("online", False)
```

### Relay 基础类模板（串口继电器，NC/NO 双模式）

> **核心原理**：通过串口发送十六进制指令控制继电器通断。
> - **NC（常闭）**：默认通电，发指令 A0 01 01 A2 断电，发 A0 01 00 A1 上电
> - **NO（常开）**：默认断电，发指令 A0 01 00 A1 断电，发 A0 01 01 A2 上电
> 参考脚本：Reboot_SuperClient_V02.py

```python
import serial
import binascii
import time

class RelayClient:
    """继电器控制客户端，适配 pressure-test 框架"""

    def __init__(self, com_port, relay_type="NC"):
        self.com_port = com_port
        self.relay_type = relay_type
        if relay_type == "NC":
            self._cmd_off = "A0 01 01 A2".replace(" ", "")
            self._cmd_on = "A0 01 00 A1".replace(" ", "")
        else:
            self._cmd_off = "A0 01 00 A1".replace(" ", "")
            self._cmd_on = "A0 01 01 A2".replace(" ", "")
        self.ser = serial.Serial(self.com_port, 9600, timeout=0.5, write_timeout=1)

    def power_on(self):
        try:
            self.ser.write(binascii.a2b_hex(self._cmd_on))
            time.sleep(0.1)
            return (200, "Power ON success")
        except Exception:
            try:
                self.ser.close()
                self.ser = serial.Serial(self.com_port, 9600, timeout=0.5, write_timeout=1)
                self.ser.write(binascii.a2b_hex(self._cmd_on))
                time.sleep(0.1)
                return (200, "Power ON success (retry)")
            except Exception as e:
                return (500, f"Power ON failed: {e}")

    def power_off(self):
        try:
            self.ser.write(binascii.a2b_hex(self._cmd_off))
            time.sleep(0.1)
            return (200, "Power OFF success")
        except Exception:
            try:
                self.ser.close()
                self.ser = serial.Serial(self.com_port, 9600, timeout=0.5, write_timeout=1)
                self.ser.write(binascii.a2b_hex(self._cmd_off))
                time.sleep(0.1)
                return (200, "Power OFF success (retry)")
            except Exception as e:
                return (500, f"Power OFF failed: {e}")

    def close(self):
        try:
            self.ser.close()
        except Exception:
            pass
```

### AT 基础类模板（串口 AT 指令交互）

> **核心原理**：基于串口的 send+check 模式，发送 AT 指令后通过正则匹配响应判断结果。
> 日志由底层 Serial 基础类负责，AT 层不额外输出日志。
> 参考脚本：551_OUT_TEST_V18.py

```python
import re
import time

class ATClient:
    """AT 指令客户端，基于串口 IO 对象的 send+check 模式"""

    def __init__(self, io_object):
        self.io = io_object

    def send_and_check_by_readlines(self, send_data_list, check_list):
        for send_data in send_data_list:
            self.io.write(send_data)
        read_lines = []
        for check_item in check_list:
            pass_list = check_item.get("pass", [])
            fail_list = check_item.get("fail", [])
            timeout = check_item.get("timeout", 5)
            start_time = time.time()
            while time.time() - start_time < timeout:
                line = self.io.readline()
                if line:
                    line_str = line.decode() if isinstance(line, bytes) else line
                    read_lines.append(line_str)
                    for fail_pattern in fail_list:
                        if re.search(fail_pattern, line_str):
                            return (201, f"Fail matched: {fail_pattern}")
                    for pass_pattern in pass_list:
                        if re.search(pass_pattern, line_str):
                            break
                    else:
                        continue
                    break
                else:
                    time.sleep(0.05)
            else:
                return (404, f"Timeout waiting for: {pass_list}")
        return (200, read_lines)

    def send_and_check_by_read(self, send_data_list, check_list):
        for send_data in send_data_list:
            self.io.write(send_data)
        for check_item in check_list:
            pass_list = check_item.get("pass", [])
            fail_list = check_item.get("fail", [])
            timeout = check_item.get("timeout", 5)
            start_time = time.time()
            buffer = ""
            while time.time() - start_time < timeout:
                data = self.io.read()
                if data:
                    data_str = data.decode() if isinstance(data, bytes) else data
                    buffer += data_str
                    for fail_pattern in fail_list:
                        if re.search(fail_pattern, buffer):
                            return (201, f"Fail matched: {fail_pattern}")
                    for pass_pattern in pass_list:
                        if re.search(pass_pattern, buffer):
                            return (200, buffer)
                time.sleep(0.05)
            return (404, f"Timeout waiting for: {pass_list}")
        return (200, buffer)
```

### Jlink 基础类模板（pylink RTT + 命令行复位）

> **核心要求**：后台线程持续读取 RTT 通道，按行写 RX 日志；write 时写 TX 日志。
> 参考脚本：551_OUT_TEST_V18.py

```python
import pylink
import subprocess
import threading
import datetime
import time
import os

class JlinkRttClient:
    """Jlink RTT 客户端，后台线程实时记录日志"""

    def __init__(self, device_name="CC2340R53", device_rate=4000,
                 rtt_address=0x20005000, rtt_channel=0, timeout=2):
        self.device_name = device_name
        self.device_rate = device_rate
        self.rtt_address = rtt_address
        self.rtt_channel = rtt_channel
        self.timeout = timeout
        self.jlink = None
        self.log_file = None
        self._thread_flag = False
        self._read_thread = None

    def open(self, log_dir=None):
        """连接 Jlink 并启动 RTT，可选初始化日志"""
        self.jlink = pylink.JLink()
        devices = self.jlink.connected_emulators()
        if not devices:
            return (500, "No J-Link devices found")
        self.jlink.open(devices[0].SerialNumber)
        self.jlink.set_tif(pylink.enums.JLinkInterfaces.SWD)
        self.jlink.set_speed(self.device_rate)
        self.jlink.connect(self.device_name)
        self.jlink.rtt_start(block_address=self.rtt_address)
        time.sleep(1)
        if log_dir:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.log_file = os.path.join(log_dir, f"jlink_log_{timestamp}.txt")
            self._write_log(f"Jlink 已连接: {self.device_name}")
            self._thread_flag = True
            self._read_thread = threading.Thread(target=self._read_loop, daemon=True)
            self._read_thread.start()
        return (200, f"Jlink connected: {self.device_name}")

    def close(self):
        self._thread_flag = False
        if self._read_thread:
            self._read_thread.join(timeout=1)
        if self.jlink:
            self.jlink.rtt_stop()
            self.jlink.close()

    def _write_log(self, msg):
        if not self.log_file:
            return
        ts = datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S.%f]")
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(f"{ts}{msg}\n")
        except Exception:
            pass

    def _read_loop(self):
        """后台线程：持续读取 RTT，按行写日志"""
        while self._thread_flag:
            try:
                data = bytes(self.jlink.rtt_read(self.rtt_channel, 100))
                if data:
                    text = data.decode("utf-8", errors="replace")
                    for line in text.split("\n"):
                        line = line.strip("\r")
                        if line:
                            self._write_log(f"[RX]{line}")
                else:
                    time.sleep(0.05)
            except Exception:
                time.sleep(0.1)

    def write(self, data):
        if isinstance(data, str):
            self._write_log(f"[TX]{data}")
            data = data.encode()
        else:
            self._write_log(f"[TX]{data.hex()}")
        self.jlink.rtt_write(self.rtt_channel, data)
        return (200, f"Sent {len(data)} bytes")

    def read(self, size=100):
        data = bytes(self.jlink.rtt_read(self.rtt_channel, size))
        if data:
            return (200, data)
        return (201, b"")

    def readline(self, end=b"\n"):
        line = bytearray()
        start_time = time.time()
        while True:
            data = bytes(self.jlink.rtt_read(self.rtt_channel, 1))
            if data:
                line += data
                if line[-len(end):] == end:
                    return (200, bytes(line))
            else:
                if not line:
                    return (201, b"")
            if time.time() - start_time > self.timeout:
                return (404, bytes(line))


class JlinkResetClient:
    """Jlink 命令行复位客户端"""

    def __init__(self, jlink_path, jlink_reset_file, device_name="FM33FK54x"):
        self.jlink_path = jlink_path
        self.jlink_reset_file = jlink_reset_file
        self.device_name = device_name

    def reset(self):
        command = (
            f'"{self.jlink_path}" -device {self.device_name} '
            f'-if SWD -speed 4000 -CommandFile "{self.jlink_reset_file}"'
        )
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        for line in result.stdout.split("\n"):
            if "Reset" in line:
                return (200, "Jlink reset success")
        return (201, "Jlink reset failed")
```

### File 基础类模板（日志文件管理）

> **核心原理**：封装 Python logging 模块，提供带时间戳的日志文件管理，支持三种切割模式。
> 参考脚本：551_OUT_TEST_V18.py

```python
import logging
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
import datetime

class LogFileClient:
    """日志文件管理客户端，适配 pressure-test 框架"""

    def __init__(self,
                 file_name="debug.log",
                 level=logging.DEBUG,
                 cmd_print_flag=False,
                 formatter_flag=True,
                 file_name_format_flag=True,
                 terminator='',
                 split_flag=3,
                 split_by_time_kwargs=None,
                 split_by_size_kwargs=None):
        self.file_name = file_name
        self.level = level
        self.cmd_print_flag = cmd_print_flag
        self.formatter_flag = formatter_flag
        self.file_name_format_flag = file_name_format_flag
        self.terminator = terminator
        self.split_flag = split_flag
        self.split_by_time_kwargs = split_by_time_kwargs or {"when": "M", "interval": 60, "backupCount": 7}
        self.split_by_size_kwargs = split_by_size_kwargs or {"maxBytes": 1024 * 1024 * 10, "backupCount": 7}
        self.open()

    def open(self):
        class MyFormatter(logging.Formatter):
            def formatTime(self, record, datefmt=None):
                dt = datetime.datetime.fromtimestamp(record.created)
                if datefmt:
                    return dt.strftime(datefmt)
                return dt.strftime('[%Y-%m-%d %H:%M:%S.%f]')
        if self.file_name_format_flag:
            self.file_name = '{}_{}.log'.format(
                self.file_name,
                datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            )
        self.logger = logging.getLogger(self.file_name)
        self.logger.propagate = False
        self.logger.setLevel(logging.DEBUG)
        if self.formatter_flag:
            formatter = MyFormatter(fmt='%(asctime)s%(message)s')
        else:
            formatter = logging.Formatter('%(message)s')
        if self.split_flag == 1:
            fh = logging.FileHandler(self.file_name)
        elif self.split_flag == 2:
            fh = TimedRotatingFileHandler(self.file_name, **self.split_by_time_kwargs)
        else:
            fh = RotatingFileHandler(self.file_name, **self.split_by_size_kwargs)
        fh.setLevel(self.level)
        fh.setFormatter(formatter)
        fh.terminator = self.terminator
        self.logger.addHandler(fh)
        if self.cmd_print_flag:
            ch = logging.StreamHandler()
            ch.setLevel(logging.INFO)
            ch.setFormatter(formatter)
            self.logger.addHandler(ch)
        return (200, "日志对象生成成功")

    def close(self):
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
        return (200, "日志对象关闭成功")

    def rename(self, new_name):
        self.close()
        self.file_name = new_name
        self.open()
        return (200, "日志对象重命名成功")

    def printf(self, msg):
        msg = msg.replace('\r\n', '\n')
        self.logger.debug(msg)

    def debug(self, msg):
        msg = msg.replace('\r\n', '\n')
        self.logger.debug(msg)

    def info(self, msg):
        msg = msg.replace('\r\n', '\n')
        self.logger.info(msg)

    def warning(self, msg):
        msg = msg.replace('\r\n', '\n')
        self.logger.warning(msg)

    def error(self, msg):
        msg = msg.replace('\r\n', '\n')
        self.logger.error(msg)

    def critical(self, msg):
        msg = msg.replace('\r\n', '\n')
        self.logger.critical(msg)
```

## 超类组合示例

通过组合模式将多个基础类组装为一个设备对象，`open_all()` 时统一传入 `log_dir`：

```python
class DeviceClient:
    def __init__(self, config):
        self.platform = PlatformClient(
            config['platform_base_url'],
            config['platform_username'],
            config['platform_password']
        )
        self.relay = RelayClient(config['relay_com'])
        self.serial = SerialClient(config.get('serial_port', 'COM1'))
        self.can = CANClient(can_type=ZCAN_USBCAN2, can_rate=500000)

    def open_all(self, log_dir=None):
        self.platform.login()
        self.relay.power_on()
        self.serial.open(log_dir=log_dir)
        self.can.open(log_dir=log_dir)

    def close_all(self):
        self.serial.close()
        self.can.close()
        self.relay.close()
```

## 注意事项

1. 基础类代码由用户提供或根据需求描述生成，本 skill 仅提供模板和设计规范
2. 实际使用时，基础类代码会嵌入到压力脚本中（单文件），不需要额外 import
3. 所有依赖库通过 `import_or_install()` 自动安装
4. 基础类的方法返回值应便于上层流程判断状态码
5. **日志文件统一放在 `log/{timestamp}/` 目录下**，与脚本日志同级
6. 日志文件使用 `encoding="utf-8"` 打开，确保中文正常记录
7. 后台线程必须设为 `daemon=True`，确保主程序退出时自动终止