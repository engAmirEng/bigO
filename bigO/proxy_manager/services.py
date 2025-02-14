from bigO.node_manager import models as node_manager_models


def get_sync_node(node: node_manager_models.Node) -> list:
    from xtlsapi import XrayClient, exception, utils

    # language=json lines
    template = """
    {
        "inbounds": [
            {
                "tag": "h2-vless-grpc-new",
                "listen": "/opt/hiddify-config/xray/run/vlessg.sock,666",
                "protocol": "vless",
                "settings": {
                    "clients": [
                        {"id": "defaultuserguidsecret", "email": "defaultuserguidsecret@hiddify.com"}
                    ],
                  "decryption": "none"
                },
                "streamSettings": {
                    "network": "grpc",
                    "security": "none",
                    "grpcSettings": {
                        "serviceName": "PATH_VLESSPATH_GRPC"
                    }
                }
              }
        ]
    }
    """

    return
