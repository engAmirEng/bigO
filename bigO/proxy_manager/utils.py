import asyncio
import os
import socket
import tempfile
from typing import TYPE_CHECKING

import django.template

if TYPE_CHECKING:
    from . import models


def get_xray_client_json(base_cfg_template, inbound_part: str, outbounds: list[tuple[str, int]]) -> str:
    return django.template.Template(base_cfg_template).render(
        django.template.Context(
            {
                "inbound_part": inbound_part,
            }
        )
    )


def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Xray2HttpProxyResource:
    def __init__(self, xray_path: str, connector: "models.OutboundConnector"):
        self.xray_path = xray_path
        self.connector = connector
        self.run_timeout = 10.0
        self.process = None
        self.is_ready = False
        self.port = None

    async def __aenter__(self):
        self.port = get_free_port()
        # language=json
        inbound_part = """
{
    "tag": "Xray2HttpProxy",
    "port": "PORT_NUM",
    "listen": "127.0.0.1",
    "protocol": "mixed",
    "sniffing": {
        "enabled": true,
        "destOverride": [
            "http",
            "tls"
        ],
        "routeOnly": false
    },
    "settings": {
        "auth": "noauth",
        "udp": true,
        "allowTransparent": false
    }
}
        """
        inbound_part = inbound_part.replace("PORT_NUM", self.port)
        json_cfg = get_xray_client_json(base_cfg_template="", inbound_part=inbound_part, outbounds=[self.connector])
        fd, cfg_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        with open(cfg_path, "wb") as f:
            f.write(json_cfg.encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())

        process = await asyncio.create_subprocess_exec(
            self.xray_path,
            "-c",
            cfg_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self.process = process

        # wait for port
        start = asyncio.get_event_loop().time()
        while True:
            try:
                reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
                writer.close()
                await writer.wait_closed()
                self.is_ready = True
                break
            except OSError:
                if asyncio.get_event_loop().time() - start > self.run_timeout:
                    raise TimeoutError("Proxy did not start in time")
                await asyncio.sleep(0.1)
        return self

    async def __aexit__(self, *args):
        if self.process is None:
            return
        self.process.terminate()
        await self.process.wait()
