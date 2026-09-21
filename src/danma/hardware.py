"""硬件与 GPU 显存自适应探测模块。

根据机器的显存大小（VRAM）自动判定 AI 弹幕回复的适用模式：
1. 显存 >= 8GB (8192 MB)：IndexTTS 模式（旗舰音质、克隆原声）；
2. 4GB <= 显存 < 8GB：MOSS-TTS-Nano 模式（轻量化 0.1B 实时低延时）；
3. 显存 < 4GB 或无独显：Playwright 公屏文本回复模式（预留接口）。
"""
from __future__ import annotations

import os
import subprocess
from typing import Dict, Tuple

TIER_INDEX_TTS = "index_tts"
TIER_MOSS_TTS = "moss_tts"
TIER_PLAYWRIGHT = "playwright"

MODE_DISPLAY_MAP: Dict[str, str] = {
    TIER_INDEX_TTS: "【自适应】IndexTTS 旗舰语音 (显存≥8G)",
    TIER_MOSS_TTS: "【自适应】MOSS-TTS-Nano 轻量语音 (显存4-8G)",
    TIER_PLAYWRIGHT: "【预留】Playwright 公屏文本回复 (低显存/无独显)",
}

ALL_MODE_DISPLAYS = list(MODE_DISPLAY_MAP.values())


def _query_nvidia_smi() -> Tuple[int, str]:
    """通过 nvidia-smi 查询首块 GPU 显存 (MB) 及型号名。失败返回 (0, '')。"""
    try:
        res = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2.5,
        )
        if res.returncode == 0 and res.stdout.strip():
            first_line = res.stdout.strip().splitlines()[0]
            parts = [p.strip() for p in first_line.split(",")]
            if len(parts) >= 2:
                name = parts[0]
                vram_mb = int(float(parts[1]))
                return vram_mb, name
    except Exception:
        pass
    return 0, ""


def _query_wmi_vram() -> Tuple[int, str]:
    """通过 PowerShell 查询 Win32_VideoController 显卡显存 (MB) 及名称。"""
    try:
        ps_cmd = (
            "Get-CimInstance Win32_VideoController | "
            "Where-Object { $_.AdapterRAM -gt 0 } | "
            "Sort-Object AdapterRAM -Descending | "
            "Select-Object -First 1 Name, AdapterRAM | "
            "ForEach-Object { \"$($_.Name)|$($_.AdapterRAM)\" }"
        )
        res = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=3.0,
        )
        if res.returncode == 0 and res.stdout.strip():
            raw = res.stdout.strip().splitlines()[0]
            if "|" in raw:
                name, ram_bytes = raw.split("|", 1)
                ram_mb = int(int(ram_bytes.strip()) / (1024 * 1024))
                return ram_mb, name.strip()
    except Exception:
        pass
    return 0, ""


def detect_gpu_tier() -> Dict[str, any]:
    """自动侦测本机 GPU 显存容量并判定 AI 弹幕回复模式。

    返回字典结构：
    {
        "tier": "index_tts" | "moss_tts" | "playwright",
        "display_name": "【自适应】...",
        "vram_mb": int,
        "gpu_name": str,
        "summary": "NVIDIA Quadro P520 (2048 MB) -> playwright",
    }
    """
    vram_mb, gpu_name = _query_nvidia_smi()
    if vram_mb <= 0:
        vram_mb, gpu_name = _query_wmi_vram()

    if not gpu_name:
        gpu_name = "标准图形显示适配器 / 无独显"

    # 显存阈值分档（考虑显存微量保留，留出 500MB 余量容差）
    if vram_mb >= 7500:
        tier = TIER_INDEX_TTS
    elif vram_mb >= 3500:
        tier = TIER_MOSS_TTS
    else:
        tier = TIER_PLAYWRIGHT

    display_name = MODE_DISPLAY_MAP[tier]
    summary = f"{gpu_name} ({vram_mb} MB) -> {display_name}"

    return {
        "tier": tier,
        "display_name": display_name,
        "vram_mb": vram_mb,
        "gpu_name": gpu_name,
        "summary": summary,
    }


detect_gpu_hardware = detect_gpu_tier

