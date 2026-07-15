"""MCP Weather Server — 天气查询 (via wttr.in, 免费无需API key)"""
import json, sys, urllib.request, urllib.parse

if __package__:
    from .framing import FrameReader
else:
    from framing import FrameReader

def _send(msg):
    body = json.dumps(msg, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8") + body)
    sys.stdout.buffer.flush()

_reader = FrameReader(sys.stdin.buffer)

def _read():
    return _reader.read()

def ok(rid, res): _send({"jsonrpc": "2.0", "id": rid, "result": res})
def err(rid, code, msg): _send({"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": msg}})

def weather(args):
    city = args.get("city", "")
    if not city: return "请提供城市名"

    try:
        q = urllib.parse.quote(city)
        # wttr.in 天气 API（英文避免 emoji 编码问题）
        url = f"https://wttr.in/{q}?format=%l:+%c+%t+%w+%h&lang=en"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/7.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8", errors="replace").strip()
        # 翻译常见天气词
        for en, zh in [("Sunny","晴"),("Clear","晴"),("Partly cloudy","多云"),("Overcast","阴"),
                        ("Light rain","小雨"),("Moderate rain","中雨"),("Heavy rain","大雨"),
                        ("Snow","雪"),("Fog","雾"),("Mist","薄雾"),("Thunder","雷"),
                        ("km/h","公里/时"),("Humidity","湿度")]:
            raw = raw.replace(en, zh)
        return raw if raw else f"找不到「{city}」的天气信息"
    except Exception as e:
        return f"天气查询失败: {str(e)[:200]}"

def forecast(args):
    city = args.get("city", "")
    if not city: return "请提供城市名"
    try:
        q = urllib.parse.quote(city)
        url = f"https://wttr.in/{q}?format=3&lang=zh"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/7.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode("utf-8", errors="replace").strip()
        return text if text else f"找不到「{city}」的预报"
    except Exception as e:
        return f"预报查询失败: {str(e)[:200]}"

H = {"weather": weather, "forecast": forecast}
T = [
    {"name": "weather", "description": "查询城市当前天气（温度/风力/湿度）",
     "inputSchema": {"type": "object", "properties": {"city": {"type": "string", "description": "城市名（中文或英文）"}}, "required": ["city"]}},
    {"name": "forecast", "description": "查询城市天气预报",
     "inputSchema": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}},
]

def main():
    """Run the local weather MCP server over standard input/output."""
    while True:
        rid = None
        try:
            m = _read()
            if m is None: break
            rid, method = m.get("id"), m.get("method", "")
            if method == "initialize":
                ok(rid, {"protocolVersion": "2024-11-05", "serverInfo": {"name": "weather", "version": "1.0"}, "capabilities": {"tools": {}}})
            elif method == "tools/list":
                ok(rid, {"tools": T})
            elif method == "tools/call":
                p = m["params"]; h = H.get(p["name"])
                if h: ok(rid, {"content": [{"type": "text", "text": h(p.get("arguments", {}))}]})
                else: err(rid, -32601, f"unknown tool: {p['name']}")
            elif method == "notifications/initialized": pass
            else: err(rid, -32601, f"unknown method: {method}")
        except KeyboardInterrupt: break
        except Exception as e:
            err(rid, -32603, "Internal error")
            sys.stderr.write(f"E: {e}\n"); sys.stderr.flush()


if __name__ == "__main__":
    main()
