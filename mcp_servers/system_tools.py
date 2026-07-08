"""MCP System Tools Server"""
import json, sys, os, random, time
from datetime import datetime

def _send(msg):
    body = json.dumps(msg, ensure_ascii=False).encode("utf-8")
    hdr = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")
    sys.stdout.buffer.write(hdr + body)
    sys.stdout.buffer.flush()

def _read():
    h = b""; empty = 0
    while not h.endswith(b"\r\n\r\n"):
        c = sys.stdin.buffer.read(1)
        if not c:
            empty += 1
            if empty > 500: return None
            time.sleep(0.01); continue
        empty = 0; h += c
    cl = 0
    for ln in h.decode("utf-8").split("\r\n"):
        if ln.lower().startswith("content-length:"):
            cl = int(ln.split(":")[1].strip())
    b = b""; empty = 0
    while len(b) < cl:
        c = sys.stdin.buffer.read(cl - len(b))
        if not c:
            empty += 1
            if empty > 500: return None
            time.sleep(0.01); continue
        empty = 0; b += c
    return json.loads(b.decode("utf-8"))

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

def rf(args):
    path = args.get("path", "")
    if not os.path.exists(path): return f"not found: {path}"
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(2000)
    except Exception as e: return str(e)

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
