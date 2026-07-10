"""MCP Web Fetch Server — 网页抓取"""
import json, sys, time, urllib.request, urllib.error, re

def _send(msg):
    body = json.dumps(msg, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8") + body)
    sys.stdout.buffer.flush()

def _read():
    header = b""; empty_header = 0
    while not header.endswith(b"\r\n\r\n"):
        chunk = sys.stdin.buffer.read(4096)
        if not chunk:
            empty_header += 1
            if empty_header > 100: return None
            time.sleep(0.01); continue
        empty_header = 0; header += chunk
        if b"\r\n\r\n" in header:
            header, leftover = header.split(b"\r\n\r\n", 1)
            header += b"\r\n\r\n"
            break
        leftover = b""
    cl = 0
    for ln in header.decode("utf-8", errors="replace").split("\r\n"):
        if ln.lower().startswith("content-length:"):
            try: cl = int(ln.split(":")[1].strip())
            except: pass
    if cl <= 0: return None
    body = leftover if leftover else b""
    empty_body = 0
    while len(body) < cl:
        chunk = sys.stdin.buffer.read(min(cl - len(body), 65536))
        if not chunk:
            empty_body += 1
            if empty_body > 200: return None
            time.sleep(0.01); continue
        empty_body = 0; body += chunk
    return json.loads(body.decode("utf-8", errors="replace"))

def ok(rid, res): _send({"jsonrpc": "2.0", "id": rid, "result": res})
def err(rid, code, msg): _send({"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": msg}})

def fetch(args):
    url = args.get("url", "")
    if not url: return "请提供 URL"
    if not url.startswith(("http://", "https://")): url = "https://" + url
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
            # 提取文本（去标签）
            text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
            text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
            text = re.sub(r"<[^>]+>", "", text)
            text = re.sub(r"\s+", " ", text).strip()
            return text[:4000] if len(text) > 4000 else text
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}: {e.reason}"
    except Exception as e:
        return f"抓取失败: {str(e)[:200]}"

def search(args):
    """Bing 搜索"""
    keyword = args.get("keyword", "")
    if not keyword: return "请提供关键词"
    try:
        q = urllib.parse.quote(keyword)
        url = f"https://www.bing.com/search?q={q}&mkt=zh-CN"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")
            results = []
            for m in re.finditer(r'<li class="b_algo"[^>]*>.*?<h2[^>]*>.*?<a[^>]*>(.*?)</a>', html, re.DOTALL):
                title = re.sub(r"<[^>]+>", "", m.group(1)).strip()
                if title and len(title) > 3:
                    results.append(title)
            if not results:
                return f"未找到关于「{keyword}」的结果"
            return "\n".join(f"- {t}" for t in results[:10])
    except Exception as e:
        return f"搜索失败: {str(e)[:200]}"

H = {"fetch": fetch, "search": search}
T = [
    {"name": "fetch", "description": "抓取网页内容",
     "inputSchema": {"type": "object", "properties": {"url": {"type": "string", "description": "网页URL"}}, "required": ["url"]}},
    {"name": "search", "description": "搜索关键词",
     "inputSchema": {"type": "object", "properties": {"keyword": {"type": "string", "description": "搜索关键词"}}, "required": ["keyword"]}},
]

while True:
    try:
        m = _read()
        if m is None: break
        rid, method = m.get("id"), m.get("method","")
        if method == "initialize":
            ok(rid, {"protocolVersion": "2024-11-05", "serverInfo": {"name": "web-fetch", "version": "1.0"}, "capabilities": {"tools": {}}})
        elif method == "tools/list":
            ok(rid, {"tools": T})
        elif method == "tools/call":
            p = m["params"]; h = H.get(p["name"])
            if h: ok(rid, {"content": [{"type": "text", "text": h(p.get("arguments",{}))}]})
            else: err(rid, -32601, f"unknown tool: {p['name']}")
        elif method == "notifications/initialized": pass
        else: err(rid, -32601, f"unknown method: {method}")
    except KeyboardInterrupt: break
    except Exception as e:
        sys.stderr.write(f"E: {e}\n"); sys.stderr.flush()