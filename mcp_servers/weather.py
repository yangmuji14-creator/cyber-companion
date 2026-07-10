"""MCP Weather Server — 天气查询 (via wttr.in, 免费无需API key)"""
import json, sys, time, urllib.request, urllib.parse

def _send(msg):
    body = json.dumps(msg, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8") + body)
    sys.stdout.buffer.flush()

def _read():
    h = b""; eh = 0
    while not h.endswith(b"\r\n\r\n"):
        c = sys.stdin.buffer.read(4096)
        if not c: eh += 1
        if not c and eh > 100: return None
        if not c: time.sleep(0.01); continue
        eh = 0; h += c
        if b"\r\n\r\n" in h:
            h, lo = h.split(b"\r\n\r\n", 1); h += b"\r\n\r\n"; break
        lo = b""
    cl = 0
    for ln in h.decode(errors="replace").split("\r\n"):
        if "content-length:" in ln.lower():
            try: cl = int(ln.split(":")[1].strip())
            except: pass
    if cl <= 0: return None
    b = lo if lo else b""; eb = 0
    while len(b) < cl:
        c = sys.stdin.buffer.read(min(cl - len(b), 65536))
        if not c: eb += 1
        if not c and eb > 200: return None
        if not c: time.sleep(0.01); continue
        eb = 0; b += c
    return json.loads(b.decode(errors="replace"))

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

while True:
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
        sys.stderr.write(f"E: {e}\n"); sys.stderr.flush()