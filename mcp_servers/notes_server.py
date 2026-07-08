"""MCP Notes Server"""
import json, sys, os, time
from datetime import datetime

DB = os.path.join(os.path.dirname(__file__), "..", "data", "notes_db.json")

def ld():
    if not os.path.exists(DB): return []
    with open(DB, "r", encoding="utf-8") as f: return json.load(f)

def sv(n):
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    with open(DB, "w", encoding="utf-8") as f: json.dump(n, f, ensure_ascii=False, indent=2)

def _send(msg):
    body = json.dumps(msg, ensure_ascii=False).encode("utf-8")
    hdr = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")
    sys.stdout.buffer.write(hdr + body); sys.stdout.buffer.flush()

def _read():
    h = b""
    while not h.endswith(b"\r\n\r\n"):
        c = sys.stdin.buffer.read(1)
        if not c: time.sleep(0.01); continue
        h += c
    cl = 0
    for ln in h.decode("utf-8").split("\r\n"):
        if ln.lower().startswith("content-length:"):
            cl = int(ln.split(":")[1].strip())
    b = b""
    while len(b) < cl:
        c = sys.stdin.buffer.read(cl - len(b))
        if not c: time.sleep(0.01); continue
        b += c
    return json.loads(b.decode("utf-8"))

def ok(rid, res):
    _send({"jsonrpc": "2.0", "id": rid, "result": res})

def add(args):
    n = ld()
    note = {"id": len(n)+1, "title": args.get("title",""), "content": args.get("content",""), "created_at": datetime.now().isoformat()}
    n.append(note); sv(n)
    return f"saved: {note['title']}"

def lst(args):
    n = ld()
    if not n: return "no notes"
    return "\n".join(f"- [{x['id']}] {x['title']}" for x in n)

def search(args):
    kw = args.get("keyword","").lower()
    n = ld()
    r = [x for x in n if kw in x["content"].lower() or kw in x["title"].lower()]
    if not r: return f"not found: {kw}"
    return "\n".join(f"- [{x['id']}] {x['title']}: {x['content'][:100]}" for x in r)

def delete(args):
    nid = args.get("id",0)
    n = ld()
    for i, x in enumerate(n):
        if x["id"] == nid: title = x["title"]; n.pop(i); sv(n); return f"deleted: {title}"
    return f"not found id={nid}"

H = {"add_note": add, "list_notes": lst, "search_notes": search, "delete_note": delete}
T = [
    {"name": "add_note", "description": "save a note",
     "inputSchema": {"type": "object", "properties": {"title": {"type": "string"}, "content": {"type": "string"}}, "required": ["title","content"]}},
    {"name": "list_notes", "description": "list all notes",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "search_notes", "description": "search notes",
     "inputSchema": {"type": "object", "properties": {"keyword": {"type": "string"}}, "required": ["keyword"]}},
    {"name": "delete_note", "description": "delete a note",
     "inputSchema": {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]}},
]

while True:
    try:
        m = _read()
        rid, method = m.get("id"), m.get("method","")
        if method == "initialize":
            ok(rid, {"protocolVersion": "2024-11-05", "serverInfo": {"name": "notes-server", "version": "1.0"}, "capabilities": {"tools": {}}})
        elif method == "tools/list":
            ok(rid, {"tools": T})
        elif method == "tools/call":
            p = m["params"]; h = H.get(p["name"])
            if h: ok(rid, {"content": [{"type": "text", "text": h(p.get("arguments",{}))}]})
            else: ok(rid, {"content": [{"type": "text", "text": f"unknown: {p['name']}"}]})
        elif method == "notifications/initialized": pass
        else: ok(rid, {})
    except KeyboardInterrupt: break
    except Exception as e:
        sys.stderr.write(f"E: {e}\n"); sys.stderr.flush()
