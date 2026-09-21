"""DeepSeek 与 本地 Ollama 弹幕智能决策与回复网关。

功能：
1. 接收直播间实时弹幕（礼物打赏、观众提问、普通聊天）；
2. 过滤无意义刷屏、打卡、表情符或违规内容；
3. 支持 DeepSeek 官方 API 与本地 Ollama 兼容端点（OpenAI 兼容接口）；
4. 结合当前推广商品与主播人设，生成高情商、强带货转化的口播回复文本。
"""
from __future__ import annotations

import json
import re
import requests
from typing import Dict, Optional, Tuple

DEFAULT_DEEPSEEK_BASE = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"


def is_local_ollama(api_base: str) -> bool:
    """判断地址是否为本地 Ollama 服务。"""
    raw = str(api_base or "").lower().strip()
    return any(k in raw for k in ("localhost", "127.0.0.1", "11434", "0.0.0.0"))


def is_llm_configured(cfg: Dict[str, any]) -> Tuple[bool, str]:
    """校验是否已正确配置 DeepSeek API Key 或本地 Ollama。"""
    api_key = str(cfg.get("deepseek_api_key") or "").strip()
    api_base = str(cfg.get("deepseek_api_base") or "").strip()

    if is_local_ollama(api_base):
        return True, "已配置本地 Ollama 服务"
    if api_key:
        return True, "已配置 DeepSeek API Key"
    return False, "未配置 DeepSeek API Key（若使用本地 Ollama 请在地址栏填入本地端口）"


def build_chat_endpoint(api_base: str) -> str:
    """将基础 URL 规范化为 /v1/chat/completions 端点。"""
    base = str(api_base or "").strip().rstrip("/")
    if not base:
        base = DEFAULT_DEEPSEEK_BASE
    if not base.endswith("/chat/completions"):
        if base.endswith("/v1"):
            base = f"{base}/chat/completions"
        else:
            base = f"{base}/v1/chat/completions"
    return base


def evaluate_and_reply(
    message: Dict[str, any],
    product_context: Dict[str, str],
    cfg: Dict[str, any],
    timeout_sec: float = 4.5,
) -> Dict[str, any]:
    """对单条弹幕进行意图评估并生成回复话术。

    :param message: 原始弹幕消息字典
    :param product_context: 包含 product_name, product_desc, pre_meet_text
    :param cfg: 系统配置字典
    :param timeout_sec: API 调用超时秒数
    :return: {
        "should_reply": bool,
        "reply_type": "gift" | "question" | "chat" | "ignore",
        "reply_text": str,
        "reason": str,
        "user": str,
    }
    """
    msg_type = message.get("type") or message.get("msg_type") or "ChatMessage"
    user_obj = message.get("user") if isinstance(message.get("user"), dict) else {}
    user = (
        message.get("name")
        or message.get("userName")
        or message.get("nickname")
        or message.get("senderName")
        or user_obj.get("nickname")
        or user_obj.get("userName")
        or "观众"
    )
    content = str(message.get("content") or message.get("text") or "").strip()

    # 1. 快速前置规则：非礼物且非文本弹幕（如点赞、进房、分享），直接忽略
    if msg_type in ("LikeMessage", "like", "MemberMessage", "enter", "SocialMessage", "follow"):
        return {"should_reply": False, "reply_type": "ignore", "reply_text": "", "reason": "like_or_enter", "user": user}

    configured, _ = is_llm_configured(cfg)
    if not configured:
        return {"should_reply": False, "reply_type": "ignore", "reply_text": "", "reason": "llm_not_configured", "user": user}

    api_key = str(cfg.get("deepseek_api_key") or "").strip()
    api_base = str(cfg.get("deepseek_api_base") or DEFAULT_DEEPSEEK_BASE).strip()
    model = str(cfg.get("deepseek_model") or DEFAULT_DEEPSEEK_MODEL).strip()
    prod_name = str(product_context.get("product_name") or "本场爆款商品").strip()
    prod_desc = str(product_context.get("product_desc") or "").strip()

    # 2. 礼物打赏专属处理
    if msg_type in ("GiftMessage", "gift"):
        gift_name = message.get("giftName") or message.get("gift_name") or "礼物"
        gift_count = message.get("giftCount") or message.get("count") or 1
        prompt = (
            f"观众【{user}】在直播间送出了【{gift_name} x {gift_count}】。\n"
            f"当前推广商品为【{prod_name}】，商品亮点：{prod_desc}。\n"
            "请以主播第一人称口吻，生成一句亲切、热情、高情商的口播感谢话术，并自然引导观众抓紧下单抢福利。\n"
            "硬性要求：只输出可直接口播的一句话，严禁前缀后缀，字数控制在40字以内。"
        )
        return _call_llm_simple_reply(
            prompt, api_key, api_base, model, timeout_sec, reply_type="gift", user=user
        )

    # 3. 聊天文本弹幕评估：空文本或极短无意义文本直接丢弃
    if not content or len(content) < 2 or content in ("111", "666", "来了", "打卡", "...", "。。。"):
        return {"should_reply": False, "reply_type": "ignore", "reply_text": "", "reason": "empty_or_trivial", "user": user}

    # 构造意图决策 Prompt（JSON 模式）
    system_prompt = (
        "你是一名带货直播间的AI智能控场助理。请阅读观众弹幕并结合商品信息，评估是否需要语音回答。\n"
        "【判断规则】\n"
        "1. 问句、咨询价格/发货/尺码/正品保障/优惠等，必须回答（should_reply=true）；\n"
        "2. 单纯打卡、数字刷屏、乱码、表情、恶意攻击谩骂，不予回答（should_reply=false）；\n"
        "3. 若需回答，以主播第一人称，结合商品卖点给出专业解答并引导下单，字数严格在40字以内。\n"
        "【输出格式】必须输出单行JSON：\n"
        "{\"should_reply\": true/false, \"reply_type\": \"question/chat/ignore\", \"reply_text\": \"话术正文\", \"reason\": \"判定原因\"}"
    )

    user_prompt = (
        f"【推广商品】{prod_name}\n"
        f"【商品描述与保障】{prod_desc}\n"
        f"【观众昵称】{user}\n"
        f"【观众弹幕】{content}\n"
    )

    url = build_chat_endpoint(api_base)
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 150,
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout_sec)
        if resp.status_code == 200:
            data = resp.json()
            raw_content = data["choices"][0]["message"]["content"].strip()
            # 提取 JSON 对象
            match = re.search(r"\{.*\}", raw_content, re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
                return {
                    "should_reply": bool(parsed.get("should_reply", False)),
                    "reply_type": parsed.get("reply_type", "chat"),
                    "reply_text": str(parsed.get("reply_text") or "").strip(),
                    "reason": parsed.get("reason", "llm_decision"),
                    "user": user,
                }
    except Exception as exc:
        return {"should_reply": False, "reply_type": "ignore", "reply_text": "", "reason": f"error_{exc}", "user": user}

    return {"should_reply": False, "reply_type": "ignore", "reply_text": "", "reason": "unmatched_decision", "user": user}


def _call_llm_simple_reply(
    prompt: str,
    api_key: str,
    api_base: str,
    model: str,
    timeout_sec: float,
    reply_type: str,
    user: str,
) -> Dict[str, any]:
    """简易模式直接获取一句生成口播（用于礼物等确定需要回复的场景）。"""
    url = build_chat_endpoint(api_base)
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.5,
        "max_tokens": 100,
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout_sec)
        if resp.status_code == 200:
            data = resp.json()
            reply = data["choices"][0]["message"]["content"].strip().strip('"\'')
            return {
                "should_reply": True,
                "reply_type": reply_type,
                "reply_text": reply,
                "reason": "gift_acknowledgement",
                "user": user,
            }
    except Exception as exc:
        # LLM 偶发超时/失败时，提供离线保底感谢，绝不漏礼
        fallback = f"感谢 {user} 送出的礼物！欢迎新进来的朋友，喜欢直接拍一号链接！"
        return {
            "should_reply": True,
            "reply_type": reply_type,
            "reply_text": fallback,
            "reason": f"fallback_gift_{exc}",
            "user": user,
        }

    fallback = f"非常感谢 {user} 的支持！下方小黄车直接拍！"
    return {
        "should_reply": True,
        "reply_type": reply_type,
        "reply_text": fallback,
        "reason": "fallback_gift",
        "user": user,
    }
