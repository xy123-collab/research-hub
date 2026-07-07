"""ai_client 接口 + 出站脱敏网关。provider 可切换（none/claude/openai/local）。
硬性约束：绝不把原始敏感数据行放进 payload，只允许元数据/聚合。"""
import re
import httpx
from .config import settings


class OutboundGuardError(Exception):
    pass


_FORBIDDEN_HINTS = ["officerID", "term_id", "身份证", "原始数据行"]


def _sanitize_check(payload: str):
    # 极简出站校验：payload 过长或含明显原始数据表格特征则拦截（示意，可扩展）
    if len(payload) > 20000:
        raise OutboundGuardError("payload 过大，疑似含原始数据，已拦截出站")
    # 连续数值行（疑似 dump 的数据表）检测
    rows = re.findall(r"^(?:\s*-?\d+[,\t]){4,}", payload, flags=re.M)
    if len(rows) > 20:
        raise OutboundGuardError("检测到疑似原始数据表，已拦截出站")


class AIClient:
    def __init__(self):
        self.provider = settings.AI_PROVIDER

    def enabled(self) -> bool:
        return self.provider not in ("none", "")

    def complete(self, prompt: str, system: str = "") -> str:
        _sanitize_check(prompt + system)
        if not self.enabled():
            return "[AI 未启用] 请在 .env 配置 AI_PROVIDER / AI_GATEWAY_URL / AI_API_KEY。"
        url = settings.AI_GATEWAY_URL
        headers = {"Authorization": f"Bearer {settings.AI_API_KEY}"}
        body = {"model": self.provider, "messages":
                [{"role": "system", "content": system}, {"role": "user", "content": prompt}]}
        try:
            r = httpx.post(url, json=body, headers=headers, timeout=60)
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"[AI 调用失败] {e}"


ai_client = AIClient()
