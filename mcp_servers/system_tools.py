"""MCP System Tools Server"""
import json, sys, os, random
from datetime import datetime

if __package__:
    from .framing import FrameReader
else:
    from framing import FrameReader

def _send(msg):
    body = json.dumps(msg, ensure_ascii=False).encode("utf-8")
    hdr = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")
    sys.stdout.buffer.write(hdr + body)
    sys.stdout.buffer.flush()

_reader = FrameReader(sys.stdin.buffer)

def _read():
    return _reader.read()

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
    os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")),
    os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")),
]
_ALLOWED_EXTENSIONS = {".txt", ".md", ".json", ".log", ".csv", ".yaml", ".yml", ".cfg", ".ini"}
_MAX_READ_SIZE = 2000

def _is_path_safe(filepath: str) -> bool:
    """检查路径是否在安全目录内、扩展名合法、无路径遍历"""
    try:
        norm = os.path.realpath(filepath)
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

def main():
    """Run the local system-tools MCP server over standard input/output."""
    while True:
        rid = None
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
            err(rid, -32603, "Internal error")
            sys.stderr.write(f"E: {e}\n"); sys.stderr.flush()


if __name__ == "__main__":
    main()
