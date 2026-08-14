#!/usr/bin/env python3
"""Generate complete pressure test Python script.

All code (base classes + super class + flow + main loop) in a single .py file.
Config file is always named device.yaml.
"""
import argparse
import os
import sys
import datetime


def read_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def generate_script(yaml_path, business_code, scenario_name, version, 
                    embed_code=None, embed_name=None):
    """Assemble the complete pressure test script (single file).
    
    Args:
        yaml_path: Path to device.yaml
        business_code: Business logic code (flow + example class)
        scenario_name: Scenario name for header
        version: Script version
        embed_code: Optional embedded code (e.g., super_client.py content)
        embed_name: Optional module name for embedded code
    """

    # === Part 1: Header ===
    header = f'''# ============================================
# Pressure Test Script: {scenario_name}
# Version: {version}
# Generated: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
# Config: device.yaml
# Architecture: Base Classes -> Super Class -> Flow -> Main Loop
# ============================================

'''

    # === Part 2: YAML config section ===
    yaml_config_section = generate_yaml_config_section(yaml_path)

    # === Part 3: Framework imports ===
    imports_section = generate_imports_section()

    # === Part 4: Framework code (ReTry, Make_File, xl_log, printf) ===
    framework_section = FRAMEWORK_CODE

    # === Part 5: Embedded code (e.g., super_client.py) ===
    embed_section = ''
    if embed_code:
        embed_section = f'''
################################## Embedded Module: {embed_name or 'external'} ##################################
# The following code is embedded from an external file.
# It contains base classes and/or super class definitions.
{embed_code}

'''

    # === Part 6: Business code (flow + example class) ===
    business_section = f'''
################################## Flow & Example Class ##################################
{business_code}
'''

    # === Part 7: Main loop ===
    main_section = '''
################################## Main Entry ##################################
if __name__=="__main__":
    E = example(
        _device_version=_device_version,
        _pressure_name=_pressure_name,
        _pressure_version=_pressure_version,
        wait_time=wait_time
    )
    try:
        while True:
            E.one_operation()
    except KeyboardInterrupt:
        printf_script("\\nTest stopped by user")
        if hasattr(E, 'device') and hasattr(E.device, 'close'):
            E.device.close()
    except Exception as e:
        printf_script(f"\\nUnexpected error: {traceback.format_exc()}")
        if hasattr(E, 'device') and hasattr(E.device, 'close'):
            E.device.close()
'''

    return header + yaml_config_section + imports_section + framework_section + embed_section + business_section + main_section


def generate_yaml_config_section(yaml_path):
    """Read YAML and generate the config declaration section."""
    yaml_content = read_file(yaml_path)
    section = '''################################## YAML Configuration ##################################
# Config loaded from device.yaml at runtime.
# Fields below are for reference; actual values come from YAML.
'''
    for line in yaml_content.splitlines():
        section += f'# {line}\n'
    section += '''
################################## Load YAML Config ##################################
def yaml_import(yaml_name="device.yaml"):
    """Load configuration from device.yaml into global variables."""
    import os
    if os.path.isfile(yaml_name):
        with open(yaml_name, 'r', encoding='utf-8') as f:
            config = yaml.load(f, Loader=yaml.FullLoader)
            for key in config.keys():
                globals()[key] = config[key]
    else:
        raise FileNotFoundError(f"{yaml_name} not found")

yaml_import()

# Ensure common fields exist with defaults
if 'wait_time' not in globals():
    wait_time = 60
if 'fail_stop_flag' not in globals():
    fail_stop_flag = False
if '_device_version' not in globals():
    _device_version = ""
if '_pressure_name' not in globals():
    _pressure_name = "PressureTest"
if '_pressure_version' not in globals():
    _pressure_version = 1

'''
    return section


def generate_imports_section():
    return '''################################## Imports ##################################
import importlib
import subprocess
import sys


def import_or_install(module_name, package_name=None):
    """Auto-install missing dependencies."""
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError:
        package_name = package_name or module_name
        print(f"Missing dependency {module_name}, installing {package_name}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
        return importlib.import_module(module_name)


# Auto-install core dependencies
serial = import_or_install("serial", "pyserial")
yaml = import_or_install("yaml", "PyYAML")
openpyxl = import_or_install("openpyxl")
requests = import_or_install("requests")
psutil = import_or_install("psutil")

import time
import binascii
import datetime
import re
import random
import threading
import traceback
import os
import shutil
import hashlib
import queue
import serial.tools.list_ports
import decimal
import math
from collections import deque
import itertools
import logging
from concurrent.futures import ThreadPoolExecutor
import codecs
import concurrent.futures
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from functools import wraps

'''


FRAMEWORK_CODE = r'''
################################## Retry Decorator ##################################
def retry_on_failure(max_retries=3, delay=1, backoff=2, exceptions=(Exception,)):
    """Retry decorator with exponential backoff."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        printf_script(f"{func.__name__} failed (attempt {attempt+1}/{max_retries+1}): {e}, retry in {current_delay}s...")
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        printf_script(f"{func.__name__} failed after {max_retries} retries: {e}")
            raise last_exception
        return wrapper
    return decorator


################################## ReTry Class ##################################
class ReTry:
    """Retry decorator class with time-based and count-based retry."""
    def __init__(self, printf_out=""):
        self.printf_out = printf_out

    def check_in_time(self, check_interval=0.1, check_timeout=10,
                      ex_pass_list=["[OXXXO]['statuscode']==200"],
                      ex_fail_list=[], ex_err_list=[], printf_flag=False):
        """Time-based retry decorator. Returns 404 on timeout."""
        def input_func(func):
            def wrapper(*args, **kwargs):
                start_time = time.time()
                try_flag = 0
                while time.time() - start_time < check_timeout:
                    res = func(*args, **kwargs)
                    if printf_flag:
                        self.printf_out(f"Attempt {try_flag+1}, result: {res}")
                    for ex_pass in ex_pass_list:
                        if type(ex_pass) == str:
                            now = eval(ex_pass.replace("[OXXXO]", "res"))
                        elif type(ex_pass) == list:
                            now = all(eval(i.replace("[OXXXO]", "res")) for i in ex_pass)
                        elif type(ex_pass) == int:
                            now = bool(res['statuscode'] == ex_pass)
                        else:
                            raise Exception("Invalid pass condition type")
                        if now:
                            return {"statuscode": 200, 'data': res, "reason": "pass"}
                    for ex_fail in ex_fail_list:
                        if type(ex_fail) == str:
                            now = eval(ex_fail.replace("[OXXXO]", "res"))
                        elif type(ex_fail) == list:
                            now = all(eval(i.replace("[OXXXO]", "res")) for i in ex_fail)
                        elif type(ex_fail) == int:
                            now = bool(res['statuscode'] == ex_fail)
                        else:
                            raise Exception("Invalid fail condition type")
                        if now:
                            return {"statuscode": 201, 'data': res, "reason": "fail"}
                    for ex_err in ex_err_list:
                        if type(ex_err) == str:
                            now = eval(ex_err.replace("[OXXXO]", "res"))
                        elif type(ex_err) == list:
                            now = all(eval(i.replace("[OXXXO]", "res")) for i in ex_err)
                        elif type(ex_err) == int:
                            now = bool(res['statuscode'] == ex_err)
                        else:
                            raise Exception("Invalid err condition type")
                        if now:
                            return {"statuscode": 202, 'data': res, "reason": "err"}
                    try_flag += 1
                    time.sleep(check_interval)
                return {"statuscode": 404, "reason": "timeout"}
            return wrapper
        return input_func

    def check_in_times(self, check_interval=1, check_timesout=3,
                       ex_pass_list=["[OXXXO]['statuscode']==200"],
                       ex_fail_list=[], ex_err_list=[], printf_flag=False):
        """Count-based retry decorator. Returns 404 after max retries."""
        def input_func(func):
            def wrapper(*args, **kwargs):
                try_flag = 0
                for i in range(check_timesout):
                    res = func(*args, **kwargs)
                    if printf_flag:
                        self.printf_out(f"Attempt {try_flag+1}, result: {res}")
                    for ex_pass in ex_pass_list:
                        if type(ex_pass) == str:
                            now = eval(ex_pass.replace("[OXXXO]", "res"))
                        elif type(ex_pass) == list:
                            now = all(eval(i.replace("[OXXXO]", "res")) for i in ex_pass)
                        elif type(ex_pass) == int:
                            now = bool(res['statuscode'] == ex_pass)
                        else:
                            raise Exception("Invalid pass condition type")
                        if now:
                            return {"statuscode": 200, 'data': res, "reason": "pass"}
                    for ex_fail in ex_fail_list:
                        if type(ex_fail) == str:
                            now = eval(ex_fail.replace("[OXXXO]", "res"))
                        elif type(ex_fail) == list:
                            now = all(eval(i.replace("[OXXXO]", "res")) for i in ex_fail)
                        elif type(ex_fail) == int:
                            now = bool(res['statuscode'] == ex_fail)
                        else:
                            raise Exception("Invalid fail condition type")
                        if now:
                            return {"statuscode": 201, 'data': res, "reason": "fail"}
                    for ex_err in ex_err_list:
                        if type(ex_err) == str:
                            now = eval(ex_err.replace("[OXXXO]", "res"))
                        elif type(ex_err) == list:
                            now = all(eval(i.replace("[OXXXO]", "res")) for i in ex_err)
                        elif type(ex_err) == int:
                            now = bool(res['statuscode'] == ex_err)
                        else:
                            raise Exception("Invalid err condition type")
                        if now:
                            return {"statuscode": 202, 'data': res, "reason": "err"}
                    try_flag += 1
                    time.sleep(check_interval)
                return {"statuscode": 404, "reason": "timesout"}
            return wrapper
        return input_func


################################## Logging Classes ##################################
class Make_File():
    """Log file manager."""
    def __init__(self, file_name, mode="a+", encoding="utf-8"):
        self.mode = mode
        self.encoding = encoding
        self.init_file_name = file_name
        self.file_name = '{}_log_{}.txt'.format(
            self.init_file_name,
            datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S"))
        self.open()

    def open(self):
        self.file = open(self.file_name, mode=self.mode, encoding=self.encoding)

    def close(self):
        self.file.close()

    def printf(self, msg):
        msg = "[{}] {}".format(datetime.datetime.now(), msg)
        self.file.write(msg + "\n")
        self.file.flush()


# Initialize log files
fail = Make_File("fail")
script = Make_File("script")


def printf_fail(msg):
    """Write to fail log."""
    fail.printf(msg)


def printf_script(msg):
    """Print to console and write to script log."""
    print(msg)
    script.printf(msg)


################################## Excel Statistics ##################################
class xl_log():
    """Excel statistics logger."""
    def __init__(self, _init_name, list_statistics, list_statistics_1):
        self._device_version = _init_name['_device_version']
        self._pressure_name = _init_name['_pressure_name']
        self._pressure_version = _init_name['_pressure_version']
        self._list_statistics = list_statistics
        self._list_statistics_1 = list_statistics_1
        self.statistic_log_path = 'statistic_log_{}.xlsx'.format(
            datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S"))
        workbook1 = openpyxl.Workbook()
        workbook1.save(self.statistic_log_path)
        self.workbook = openpyxl.load_workbook(self.statistic_log_path)
        self.sheet = self.workbook.active
        list_excel_begin = [
            ["Device Version", _device_version],
            ["Script Name", _pressure_name],
            ["Script Version", _pressure_version], [], []
        ]
        for l in list_excel_begin:
            self.sheet.append(l)
        self.workbook.save(self.statistic_log_path)
        self.begin_row_1 = self.sheet.max_row + 1 + 3
        list_statistics_header = [["Statistic", "Value", "Note"]]
        _list_statistics_keys = [[i] for i in self._list_statistics.keys()]
        __list_statistics_1 = list_statistics_header + _list_statistics_keys + [[], []]
        for l in __list_statistics_1:
            self.sheet.append(l)
        self.workbook.save(self.statistic_log_path)

    def printf(self):
        list_all_data = []
        begin_line = self.begin_row_1
        k = 0
        for i in self._list_statistics.values():
            list_all_data.append([begin_line + k, 2, i])
            k += 1
        for n in list_all_data:
            self.sheet.cell(n[0], n[1], n[2])
        self.workbook.save(self.statistic_log_path)


'''


def main():
    parser = argparse.ArgumentParser(description='Generate pressure test script (single file)')
    parser.add_argument('--output', required=True, help='Output Python script path')
    parser.add_argument('--yaml', required=True, help='Path to device.yaml')
    parser.add_argument('--business', required=True, help='Path to business code file')
    parser.add_argument('--scenario', default='PressureTest', help='Scenario name')
    parser.add_argument('--version', default='1', help='Script version')
    parser.add_argument('--embed', help='Path to external file to embed (e.g., super_client.py)')
    parser.add_argument('--embed-name', help='Module name for embedded file')

    args = parser.parse_args()

    business_code = read_file(args.business)
    
    embed_code = None
    if args.embed:
        embed_code = read_file(args.embed)

    result = generate_script(
        yaml_path=args.yaml,
        business_code=business_code,
        scenario_name=args.scenario,
        version=args.version,
        embed_code=embed_code,
        embed_name=args.embed_name
    )

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(result)

    print(f'Pressure test script generated: {args.output}')


if __name__ == '__main__':
    main()
