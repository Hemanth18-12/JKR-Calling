from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path

import httpx

from app.config import Settings

logger = logging.getLogger("jkr_api.voice_worker_supervisor")

_voice_worker_proc: subprocess.Popen | None = None
_spawn_lock = asyncio.Lock()


def _is_local_url(url: str) -> bool:
    return "127.0.0.1" in url or "localhost" in url


def _extract_port(url: str, default: str = "8100") -> str:
    cleaned = url.split("://")[-1]
    if ":" in cleaned:
        return cleaned.split(":")[1].split("/")[0]
    return default


async def check_voice_worker_healthy(base_url: str, timeout: float = 1.0) -> bool:
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
            resp = await client.get("/health")
            return resp.status_code == 200
    except Exception:
        return False


async def ensure_voice_worker_running(settings: Settings) -> bool:
    """Checks if voice-worker is reachable on settings.voice_worker_base_url.
    If it is a local address and not running, automatically spawns it as a
    background subprocess using the current Python environment."""
    global _voice_worker_proc

    if not _is_local_url(settings.voice_worker_base_url):
        return await check_voice_worker_healthy(settings.voice_worker_base_url)

    if await check_voice_worker_healthy(settings.voice_worker_base_url, timeout=0.8):
        return True

    async with _spawn_lock:
        # Re-check inside lock
        if await check_voice_worker_healthy(settings.voice_worker_base_url, timeout=0.8):
            return True

        if _voice_worker_proc is not None and _voice_worker_proc.poll() is None:
            # Process is already starting up, wait a bit
            for _ in range(15):
                await asyncio.sleep(0.3)
                if await check_voice_worker_healthy(settings.voice_worker_base_url, timeout=0.5):
                    return True
            return False

        repo_root = Path(__file__).resolve().parents[3]
        voice_worker_dir = repo_root / "services" / "voice-worker"
        if not (voice_worker_dir / "app" / "main.py").exists():
            logger.warning("[voice-worker supervisor] Directory not found: %s", voice_worker_dir)
            return False

        port = _extract_port(settings.voice_worker_base_url, "8100")
        logger.info("[voice-worker supervisor] Spawning voice-worker on port %s from %s...", port, voice_worker_dir)

        env = os.environ.copy()
        # Ensure PYTHONPATH includes repo packages if needed
        packages_dir = repo_root / "packages"
        if packages_dir.exists():
            env["PYTHONPATH"] = str(repo_root) + os.pathsep + env.get("PYTHONPATH", "")

        try:
            _voice_worker_proc = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", port],
                cwd=str(voice_worker_dir),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.info("[voice-worker supervisor] Process started with PID %s", _voice_worker_proc.pid)
        except Exception as exc:
            logger.error("[voice-worker supervisor] Failed to spawn process: %s", exc)
            return False

        # Wait up to 6 seconds for voice-worker to become healthy
        for _ in range(20):
            await asyncio.sleep(0.3)
            if await check_voice_worker_healthy(settings.voice_worker_base_url, timeout=0.5):
                logger.info("[voice-worker supervisor] voice-worker is healthy and ready on port %s!", port)
                return True

        logger.warning("[voice-worker supervisor] voice-worker did not become healthy within timeout.")
        return False


def stop_voice_worker() -> None:
    global _voice_worker_proc
    if _voice_worker_proc is not None and _voice_worker_proc.poll() is None:
        logger.info("[voice-worker supervisor] Stopping voice-worker (PID %s)...", _voice_worker_proc.pid)
        try:
            _voice_worker_proc.terminate()
            _voice_worker_proc.wait(timeout=3)
        except Exception:
            try:
                _voice_worker_proc.kill()
            except Exception:
                pass
        finally:
            _voice_worker_proc = None
