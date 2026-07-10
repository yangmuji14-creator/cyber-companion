"""MCP System Tools Server"""
import json, sys, os, random, time
from datetime import datetime

def _send(msg):
    body = json.dumps(msg, ensure_ascii=False).encode("utf-8")
    hdr = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")
    sys.stdout.buffer.write(hdr + body)
    sys.stdout.buffer.flush()

def _read():
    """读取一条 JSON-RPC 消息 — Windows pipe 兼容"""
    header = b""
    empty_header = 0
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
            except (ValueError, IndexError): pass

    if cl <= 0: return None

    body = leftover if leftover else b""
    empty_body = 0
    while len(body) < cl:
        need = cl - len(body)
        chunk = sys.stdin.buffer.read(min(need, 65536))
        if not chunk:
            empty_body += 1
            if empty_body > 200: return None
            time.sleep(0.01); continue
        empty_body = 0; body += chunk

    return json.loads(body.decode("utf-8", errors="replace"))

def ok(rid, res):
    _send({"jsonrpc": "2.0", "id": rid, "result": res})

def err(rid, code, msg):
    _send({"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": msg}})

def dt(args):
    f = args.get("format", "full")
    n = datetime.now()
    if f == "date": return n.strftime("%Y-%m-%d")
    if f == "time": return n.strftime("%H:%M:%S")
    return n.strftime("%Y-%m-%d %H:%M:%S")

def wc(args):
    t = args.get("text", "")
    cn = sum(1 for c in t if '\u4e00' <= c <= '\u9fff')
    return f"chars={len(t)} cn={cn} words={len(t.split())}"

def rn(args):
    lo, hi = int(args.get("min", 1)), int(args.get("max", 100))
    if lo > hi: lo, hi = hi, lo
    return f"random({lo},{hi})={random.randint(lo, hi)}"

# 文件读取安全白名单
_SAFE_READ_DIRS = [
    os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")),
    os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")),
    os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config")),
]
_ALLOWED_EXTENSIONS = {".txt", ".md", ".json", ".log", ".csv", ".yaml", ".yml", ".cfg", ".ini"}
_MAX_READ_SIZE = 2000

def _is_path_safe(filepath: str) -> bool:
    """检查路径是否在安全目录内、扩展名合法、无路径遍历"""
    try:
        norm = os.path.normpath(os.path.abspath(filepath))
    except Exception:
        return False
    # 扩展名白名单
    ext = os.path.splitext(norm)[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        return False
    # 路径遍历检测：规范化后必须在安全目录内
    for safe_dir in _SAFE_READ_DIRS:
        try:
            if os.path.commonpath([norm, safe_dir]) == safe_dir:
                return True
        except ValueError:
            continue
    return False

def rf(args):
    path = args.get("path", "")
    if not path:
        return "请提供文件路径"
    if not _is_path_safe(path):
        return f"访问被拒绝: 路径不在允许范围内或文件类型不支持"
    if not os.path.exists(path):
        return f"文件不存在: {os.path.basename(path)}"
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(_MAX_READ_SIZE)
    except PermissionError:
        return "无权限读取该文件"
    except Exception as e:
        return f"读取失败: {str(e)[:100]}"

H = {"get_datetime": dt, "count_words": wc, "random_number": rn, "read_text_file": rf}
T = [
    {"name": "get_datetime", "description": "get current date/time",
     "inputSchema": {"type": "object", "properties": {"format": {"type": "string"}}}},
    {"name": "count_words", "description": "count text stats",
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
    {"name": "random_number", "description": "random integer",
     "inputSchema": {"type": "object", "properties": {"min": {"type": "integer"}, "max": {"type": "integer"}}}},
    {"name": "read_text_file", "description": "read file",
     "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
]

while True:
    try:
        m = _read()
        if m is None: break
        rid, method = m.get("id"), m.get("method", "")
        if method == "initialize":
            ok(rid, {"protocolVersion": "2024-11-05", "serverInfo": {"name": "system-tools", "version": "1.0"}, "capabilities": {"tools": {}}})
        elif method == "tools/list":
            ok(rid, {"tools": T})
        elif method == "tools/call":
            p = m["params"]; h = H.get(p["name"])
            if h: ok(rid, {"content": [{"type": "text", "text": h(p.get("arguments", {}))}]})
            else: err(rid, -32601, f"unknown: {p['name']}")
        elif method == "notifications/initialized": pass
        else: err(rid, -32601, f"unknown: {method}")
    except KeyboardInterrupt: break
    except Exception as e:
        sys.stderr.write(f"E: {e}\n"); sys.stderr.flush()
