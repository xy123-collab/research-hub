"""ai_client 接口 + 出站脱敏网关。OpenAI 兼容（默认腾讯云 TokenHub）。
硬性约束：绝不把原始敏感数据行放进 payload，只允许元数据/聚合。
provider 可切换（none/tokenhub/openai/local），业务代码零改动。"""
import re
import httpx
from .config import settings


class OutboundGuardError(Exception):
    pass


def _sanitize_check(payload: str):
    """出站脱敏校验：拦截疑似原始数据表进入 payload。"""
    if len(payload) > 24000:
        raise OutboundGuardError("payload 过大，疑似含原始数据，已拦截出站")
    rows = re.findall(r"^(?:\s*-?\d+[,\t]){4,}", payload, flags=re.M)
    if len(rows) > 20:
        raise OutboundGuardError("检测到疑似原始数据表，已拦截出站")


class AIClient:
    @property
    def base_url(self) -> str:
        return (settings.AI_GATEWAY_URL or settings.AI_BASE_URL).rstrip("/")

    def enabled(self) -> bool:
        return settings.AI_PROVIDER not in ("none", "") and bool(settings.AI_API_KEY)

    @property
    def provider(self) -> str:
        return settings.AI_PROVIDER

    def complete(self, prompt: str, system: str = "", strong: bool = False) -> str:
        """OpenAI 兼容 chat completions。strong=True 用强模型。"""
        _sanitize_check(prompt + system)
        if not self.enabled():
            return ("[AI 未启用] 请在环境变量配置 AI_PROVIDER=tokenhub、AI_API_KEY、"
                    "（可选）AI_MODEL / AI_BASE_URL。")
        url = f"{self.base_url}/chat/completions"
        model = settings.AI_MODEL_STRONG if strong else settings.AI_MODEL
        headers = {"Authorization": f"Bearer {settings.AI_API_KEY}",
                   "Content-Type": "application/json"}
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        body = {"model": model, "messages": messages, "temperature": 0.3}
        try:
            r = httpx.post(url, json=body, headers=headers, timeout=90)
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            return f"[AI 调用失败 {e.response.status_code}] {e.response.text[:300]}"
        except Exception as e:
            return f"[AI 调用失败] {e}"


ai_client = AIClient()
