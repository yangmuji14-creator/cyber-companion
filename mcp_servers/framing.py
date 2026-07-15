"""Persistent Content-Length framing for local MCP stdio servers."""

import json


class FrameReader:
    """Read one JSON-RPC frame while retaining surplus pipe bytes."""

    MAX_HEADER_SIZE = 64 * 1024
    MAX_BODY_SIZE = 4 * 1024 * 1024

    def __init__(self, stream):
        self._stream = stream
        self._buffer = b""

    def read(self):
        separator = b"\r\n\r\n"
        while separator not in self._buffer:
            chunk = self._stream.read1(4096)
            if not chunk:
                return None
            self._buffer += chunk
            if len(self._buffer) > self.MAX_HEADER_SIZE:
                raise ValueError("header exceeds maximum size")

        header, self._buffer = self._buffer.split(separator, 1)
        content_length = 0
        for line in header.decode("utf-8", errors="replace").split("\r\n"):
            if line.lower().startswith("content-length:"):
                content_length = int(line.split(":", 1)[1].strip())
                break
        if content_length <= 0:
            return None
        if content_length > self.MAX_BODY_SIZE:
            raise ValueError("body exceeds maximum size")

        while len(self._buffer) < content_length:
            chunk = self._stream.read1(65536)
            if not chunk:
                return None
            self._buffer += chunk

        body = self._buffer[:content_length]
        self._buffer = self._buffer[content_length:]
        return json.loads(body.decode("utf-8", errors="replace"))
