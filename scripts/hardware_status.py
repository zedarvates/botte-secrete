#!/usr/bin/env python3
"""
Botte Secrète — Hailo-8 Status Check
"""

import json
import urllib.request
import sys


def check_hailo(host="192.168.1.47", port=8767):
    """Check Hailo-8 device status."""
    base = f"http://{host}:{port}"
    
    print("=== Hailo-8 Status ===")
    
    # Health check
    try:
        resp = urllib.request.urlopen(f"{base}/health", timeout=5)
        data = json.loads(resp.read())
        print(f"Status: {data.get('status', 'unknown')}")
        print(f"YOLO loaded: {data.get('yolo_loaded', False)}")
        models = data.get("models_available", [])
        print(f"Models available: {len(models)}")
        for m in models:
            print(f"  - {m}")
    except Exception as e:
        print(f"Error: {e}")
        print("Is the Hailo MCP server running on EUREKAI?")
        return False
    
    return True


def check_comfyui(host="192.168.1.47", port=8188):
    """Check ComfyUI status."""
    base = f"http://{host}:{port}"
    
    print("\n=== ComfyUI Status ===")
    
    try:
        resp = urllib.request.urlopen(f"{base}/system_stats", timeout=5)
        data = json.loads(resp.read())
        print(f"Status: running")
        print(f"System: {data.get('system', {}).get('os', 'unknown')}")
        print(f"Python: {data.get('system', {}).get('python_version', 'unknown')}")
        for gpu in data.get("devices", []):
            vram_gb = gpu.get("vram_total", 0) // (1024 ** 3)
            print(f"GPU: {gpu.get('name', 'unknown')} ({vram_gb} GB)")
    except Exception as e:
        print(f"Error: {e}")
        return False
    
    return True


def check_bonsai(port=8788):
    """Check Bonsai Image status."""
    base = f"http://localhost:{port}"
    
    print("\n=== Bonsai Image Status ===")
    
    try:
        resp = urllib.request.urlopen(f"{base}/health", timeout=5)
        data = json.loads(resp.read())
        print(f"Status: {data.get('status', 'unknown')}")
        print(f"Model: {data.get('model', 'unknown')}")
        print(f"Backend: {data.get('backend', 'unknown')}")
    except Exception as e:
        print(f"Error: {e}")
        return False
    
    return True


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--hailo-host", default="192.168.1.47")
    parser.add_argument("--hailo-port", type=int, default=8767)
    parser.add_argument("--comfyui-host", default="192.168.1.47")
    parser.add_argument("--comfyui-port", type=int, default=8188)
    parser.add_argument("--bonsai-port", type=int, default=8788)
    args = parser.parse_args()
    
    hailo_ok = check_hailo(args.hailo_host, args.hailo_port)
    comfyui_ok = check_comfyui(args.comfyui_host, args.comfyui_port)
    bonsai_ok = check_bonsai(args.bonsai_port)
    
    print("\n=== Summary ===")
    print(f"Hailo-8:     {'✅' if hailo_ok else '❌'}")
    print(f"ComfyUI:     {'✅' if comfyui_ok else '❌'}")
    print(f"Bonsai:      {'✅' if bonsai_ok else '❌'}")
