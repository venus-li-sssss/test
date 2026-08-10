"""抓取平台(iot-test.ninebot.com)指令下发日志并渲染成截图。
用途: 整车测试用例执行时, 指令类用例需要在"平台"侧证明
  (1) 指令确实下发 (req_time)
  (2) 下发后设备有回执 (resp_time/resp_code/status)
这就是用户反复要求的"平台的历史数据的指令下发页面"截图。

前置: SOCKS5 隧道必须通 (连接九号内网.bat 跑起来且已输密码, 1080 能连到 iot-test.ninebot.com)。
链路:
  1. (可选) 在手机 APP 触发一次精准续航开关 -> 产生一条 4G 云通道指令
  2. ninebot_ota.py commands <sn> --watch 30  -> 抓平台指令日志(下发+回执)
  3. 把日志渲染成 PNG (平台页面截图)
  4. 可选 --embed 把该 PNG 贴回 Excel 指定列

注意: 平台=网页控制台(走 ninebot_ota.py), 与手机 APP(device_control.py)是两回事。
"""
import argparse, subprocess, sys, os, tempfile, json
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

SKILL = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

def run(cmd, timeout=150):
    return subprocess.run(cmd, capture_output=True, text=True, cwd=SKILL, timeout=timeout)

def render_log_to_png(text, out_path, title="平台指令下发日志  iot-test.ninebot.com"):
    lines = [l for l in text.strip().splitlines() if l.strip()]
    w, line_h, pad = 960, 28, 22
    h = pad * 2 + 44 + line_h * max(len(lines), 6)
    img = Image.new("RGB", (w, h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("msyh.ttc", 18); bold = ImageFont.truetype("msyh.ttc", 21)
    except Exception:
        font = ImageFont.load_default(); bold = font
    d.text((pad, pad), title, fill=(200, 30, 30), font=bold)
    d.line([(pad, pad + 34), (w - pad, pad + 34)], fill=(200, 30, 30), width=2)
    y = pad + 46
    for ln in lines:
        color = (0, 0, 0)
        if "✅" in ln: color = (0, 130, 0)
        elif "⏳" in ln or "失败" in ln or "无回应" in ln or "超时" in ln: color = (200, 30, 30)
        d.text((pad, y), ln[:118], fill=color, font=font)
        y += line_h
    img.save(out_path, optimize=True)
    return img.size

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sn", required=True, help="车辆 SN (如 48DGZ2602J0022)")
    ap.add_argument("--xlsx", default=None)
    ap.add_argument("--sheet", default="精准续航")
    ap.add_argument("--id", default=None, help="用例编号, 用于贴回 Excel")
    ap.add_argument("--col", type=int, default=19, help="贴回列(默认 S=19)")
    ap.add_argument("--no-trigger", action="store_true", help="不触发设备, 仅抓当前窗口日志")
    ap.add_argument("--minutes", type=int, default=30)
    args = ap.parse_args()

    if not args.no_trigger:
        dc = os.path.join(SKILL, "device_control.py")
        run([PY, dc, "go_to_page", "--page", "more_functions"])
        run([PY, dc, "cmd", "--target", "精准续航", "--action", "on",
             "--evidence", tempfile.mkdtemp()])
        run([PY, dc, "cmd", "--target", "精准续航", "--action", "off",
             "--evidence", tempfile.mkdtemp()])

    ota = os.path.join(SKILL, "ninebot_ota.py")
    r = run([PY, ota, "commands", args.sn, "--minutes", str(args.minutes)])
    out = (r.stdout or "") + ("\n" + r.stderr if r.stderr else "")
    print(out)

    os.makedirs("ev", exist_ok=True)
    png = os.path.join(os.getcwd(), "ev", "platform_cmd_log.png")
    size = render_log_to_png(out, png)
    print(f"[IMG] {png} {size}")

    if args.xlsx and args.id:
        ex = os.path.join(SKILL, "execute_testcases.py")
        run([PY, ex, "record", "--xlsx", args.xlsx, "--sheet", args.sheet,
             "--id", args.id, "--verdict", "PASS", "--imgs", png,
             "--col", str(args.col)])
    print("[DONE]")

if __name__ == "__main__":
    main()
