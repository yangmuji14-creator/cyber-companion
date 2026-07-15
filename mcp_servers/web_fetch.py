"""MCP Web Fetch Server — 网页抓取 (SSRF 防护)"""
import ipaddress
import json
import re
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request

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

# ── SSRF 防护 ──
_BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"}
_BLOCKED_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("fc00::/7"),
]

def _is_internal_url(url: str) -> bool:
    """检测 URL 是否指向内网地址（SSRF 防护）"""
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname
        if not host:
            return False
        # 主机名黑名单
        host_lower = host.lower()
        if host_lower in _BLOCKED_HOSTS:
            return True
        # IP 地址黑名单
        try:
            addr = ipaddress.ip_address(host)
            if addr.is_private or addr.is_loopback or addr.is_link_local:
                return True
            for net in _BLOCKED_NETS:
                if addr in net:
                    return True
        except ValueError:
            pass  # 不是 IP 地址，跳过
        # DNS 解析后再次检查（防止 DNS rebinding）
        try:
            resolved = socket.gethostbyname(host)
            addr = ipaddress.ip_address(resolved)
            if addr.is_private or addr.is_loopback or addr.is_link_local:
                return True
            for net in _BLOCKED_NETS:
                if addr in net:
                    return True
        except Exception:
            return True  # 解析失败，fail-safe
        return False
    except Exception:
        return True


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Reject redirects so every fetched URL receives an SSRF check."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open_public_url(request: urllib.request.Request):
    """Fetch one already-validated public URL without following redirects."""
    opener = urllib.request.build_opener(_NoRedirectHandler())
    return opener.open(request, timeout=15)

def fetch(args):
    url = args.get("url", "")
    if not url: return "请提供 URL"
    if not url.startswith(("http://", "https://")): url = "https://" + url
    # SSRF 检查
    if _is_internal_url(url):
        return "安全限制: 不允许访问内网地址"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        with _open_public_url(req) as resp:
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

def main():
    """Run the local web-fetch MCP server over standard input/output."""
    while True:
        rid = None
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
            err(rid, -32603, "Internal error")
            sys.stderr.write(f"E: {e}\n"); sys.stderr.flush()


if __name__ == "__main__":
    main()
