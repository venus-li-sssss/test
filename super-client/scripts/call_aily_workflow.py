#!/usr/bin/env python3
"""
飞书 Aily 文件上传工作流脚本（已验证通过）

完整流程：
1. 获取 Access Token
2. 创建会话
3. 上传文件
4. 创建消息（关联文件）
5. 触发 Bot 执行
6. 轮询运行状态
7. 获取助手返回结果

用法:
    python call_aily_workflow.py \
        --app-id <APP_ID> \
        --app-secret <APP_SECRET> \
        --spring-id <SPRING_ID> \
        --skill-id <SKILL_ID> \
        --file <FILE_PATH> \
        [--query "OCR 识别"] \
        [--timeout 60]
"""

import argparse
import json
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    print(json.dumps({
        "success": False,
        "error": "requests 未安装，请执行: pip install requests"
    }, ensure_ascii=False, indent=2))
    sys.exit(1)


# MIME 类型映射
MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


def get_mime_type(file_path: Path) -> str:
    """根据文件扩展名获取 MIME 类型"""
    return MIME_TYPES.get(file_path.suffix.lower(), "application/octet-stream")


class AilyWorkflow:
    """飞书 Aily 文件上传工作流客户端（已验证通过）"""
    
    def __init__(self, app_id: str, app_secret: str, spring_id: str, skill_id: str = None):
        self.app_id = app_id
        self.app_secret = app_secret
        self.spring_id = spring_id
        self.skill_id = skill_id
        
        self.base_url = "https://open.feishu.cn/open-apis/aily/v1"
        self.auth_url = "https://open.feishu.cn/open-apis/auth/v3"
        
        self.access_token = None
    
    def _headers(self, content_type: str = "application/json") -> dict:
        """生成带认证的请求头"""
        headers = {"Authorization": f"Bearer {self.access_token}"}
        if content_type:
            headers["Content-Type"] = content_type
        return headers
    
    def _get_token(self) -> str:
        """获取 Access Token"""
        url = f"{self.auth_url}/app_access_token/internal"
        payload = {"app_id": self.app_id, "app_secret": self.app_secret}
        
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        if data.get("code") != 0:
            raise Exception(f"获取 token 失败：{data.get('msg')}")
        
        self.access_token = data["app_access_token"]
        return self.access_token
    
    def run(self, file_path: str, query: str = "OCR 识别", timeout: int = 60) -> dict:
        """执行完整工作流

        Args:
            file_path: 待上传的文件路径
            query: 发送给 Skill 的查询内容
            timeout: 轮询超时时间（秒）

        Returns:
            {
                "success": True/False,
                "file_id": "file_xxx",
                "messages": ["AI 返回的结果..."],
                "error": None / "错误信息"
            }
        """
        result = {
            "success": False,
            "file_path": file_path,
            "query": query,
            "file_id": None,
            "messages": [],
            "error": None
        }
        
        try:
            # 1. 获取 Token
            self._get_token()
            
            # 2. 创建会话
            resp = requests.post(f"{self.base_url}/sessions", headers=self._headers(), json={}, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                raise Exception(f"创建会话失败：{data.get('msg')}")
            session_id = data["data"]["session"]["id"]
            
            # 3. 上传文件
            fp = Path(file_path)
            if not fp.exists():
                raise FileNotFoundError(f"文件不存在：{file_path}")
            
            headers = {"Authorization": f"Bearer {self.access_token}"}
            with open(fp, "rb") as f:
                files = {"file": (fp.name, f, get_mime_type(fp))}
                resp = requests.post(f"{self.base_url}/files", headers=headers, files=files, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                raise Exception(f"上传文件失败：{data.get('msg')}")
            file_id = data["data"]["files"][0]["id"]
            result["file_id"] = file_id
            
            # 4. 创建消息
            payload = {
                "idempotent_id": f"idempotent_{int(time.time() * 1000)}",
                "content_type": "MDX",
                "content": query,
                "file_ids": [file_id]
            }
            resp = requests.post(
                f"{self.base_url}/sessions/{session_id}/messages",
                headers=self._headers(), json=payload, timeout=30
            )
            resp.raise_for_status()
            
            # 5. 触发执行
            run_payload = {"app_id": self.spring_id}
            if self.skill_id:
                run_payload["skill_id"] = self.skill_id
            
            resp = requests.post(
                f"{self.base_url}/sessions/{session_id}/runs",
                headers=self._headers(), json=run_payload, timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                raise Exception(f"触发执行失败：{data.get('msg')}")
            run_id = data["data"]["run"]["id"]
            
            # 6. 轮询状态
            url = f"{self.base_url}/sessions/{session_id}/runs/{run_id}"
            start = time.time()
            while time.time() - start < timeout:
                resp = requests.get(url, headers=self._headers(), timeout=30)
                resp.raise_for_status()
                data = resp.json()
                if data.get("code") == 0:
                    status = data["data"]["run"]["status"]
                    if status == "COMPLETED":
                        break
                    if status == "FAILED":
                        result["error"] = "AI 执行失败"
                        return result
                time.sleep(2)
            else:
                result["error"] = f"AI 执行超时 (timeout={timeout}s)"
                return result
            
            # 7. 获取结果
            resp = requests.get(
                f"{self.base_url}/sessions/{session_id}/messages",
                headers=self._headers(), timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                raise Exception(f"获取消息失败：{data.get('msg')}")
            
            messages = [
                msg["content"] for msg in data["data"]["messages"]
                if msg.get("sender", {}).get("sender_type") == "ASSISTANT"
            ]
            
            result["success"] = True
            result["messages"] = messages
            return result
            
        except Exception as e:
            result["error"] = str(e)
            return result


def main():
    parser = argparse.ArgumentParser(description="飞书 Aily 文件上传工作流")
    parser.add_argument("--app-id", required=True, help="飞书应用 APP ID")
    parser.add_argument("--app-secret", required=True, help="飞书应用 APP Secret")
    parser.add_argument("--spring-id", required=True, help="Aily Spring ID (如 spring_xxx)")
    parser.add_argument("--skill-id", default=None, help="Skill ID (如 skill_xxx)")
    parser.add_argument("--file", required=True, help="待上传的文件路径")
    parser.add_argument("--query", default="OCR 识别", help="发送给 Skill 的查询内容")
    parser.add_argument("--timeout", type=int, default=60, help="轮询超时时间 (秒)")
    args = parser.parse_args()
    
    # 验证文件存在
    if not Path(args.file).exists():
        print(json.dumps({
            "success": False,
            "error": f"文件不存在：{args.file}"
        }, ensure_ascii=False, indent=2))
        sys.exit(1)
    
    # 创建工作流客户端
    workflow = AilyWorkflow(
        app_id=args.app_id,
        app_secret=args.app_secret,
        spring_id=args.spring_id,
        skill_id=args.skill_id
    )
    
    # 执行工作流
    result = workflow.run(
        file_path=args.file,
        query=args.query,
        timeout=args.timeout
    )
    
    # 输出结果
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    if not result["success"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
