import logging
import os
import subprocess
import time
import urllib.parse
from pathlib import Path

import pydantic
import requests
from pydantic_settings import BaseSettings, SettingsConfigDict

from .api_types import BaseSyncResponse, BaseSyncRequest, MetricRequest

BASE_DIR = Path(__file__).resolve(strict=True).parent.parent

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", os.path.join(BASE_DIR, ".env")), env_file_encoding="utf-8")

    interval_sec: int
    api_key: str
    server_base_url: pydantic.HttpUrl
    working_dir: str = "./workdir"
    full_control_supervisord: bool

    @pydantic.model_validator(mode="before")
    def check_working_dir(cls, values):
        working_dir_val = values.get("working_dir", "./workdir")
        path = Path(working_dir_val)
        if not path.is_absolute():
            path = BASE_DIR / path
        path.mkdir(parents=True, exist_ok=True)
        return values

    def get_working_dir(self) -> Path:
        path = Path(self.working_dir)
        if not path.is_absolute():
            path = BASE_DIR / path
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_bin_dir(self):
        working_dir = self.get_working_dir()
        res = working_dir.joinpath("bin")
        res.mkdir(parents=False, exist_ok=True)
        return res

    def get_conf_dir(self):
        working_dir = self.get_working_dir()
        res = working_dir.joinpath("conf")
        res.mkdir(parents=False, exist_ok=True)
        return res

    def get_base_sync_url(self):
        return urllib.parse.urljoin(str(settings.server_base_url), "node-manager/node/base-sync/")

    def get_binary_content_url(self, hash: str):
        return urllib.parse.urljoin(
            str(settings.server_base_url), f"node-manager/node/program-binary/hash/{hash}/content/"
        )

    def get_configfile_path_placeholder(self):
        return "CONFIGFILEPATH"

    def get_logs_dir(self):
        working_dir = self.get_working_dir()
        res = working_dir.joinpath("logs")
        res.mkdir(parents=False, exist_ok=True)
        return res

    def get_supervisor_dir(self):
        working_dir = self.get_working_dir()
        res = working_dir.joinpath("supervisor")
        res.mkdir(parents=False, exist_ok=True)
        return res

    def get_supervisor_base_config(self, subconfig_path: Path):
        res = f"""
; supervisor config file

[unix_http_server]
file=/var/run/supervisor.sock   ; (the path to the socket file)
chmod=0700                       ; sockef file mode (default 0700)

[supervisord]
logfile=/var/log/supervisor/supervisord.log ; (main log file;default $CWD/supervisord.log)
pidfile=/var/run/supervisord.pid ; (supervisord pidfile;default supervisord.pid)
childlogdir=/var/log/supervisor            ; ('AUTO' child log dir, default $TEMP)

; the below section must remain in the config file for RPC
; (supervisorctl/web interface) to work, additional interfaces may be
; added by defining them in separate rpcinterface: sections
[rpcinterface:supervisor]
supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface

[supervisorctl]
serverurl=unix:///var/run/supervisor.sock ; use a unix:// URL  for a unix socket

; The [include] section can just contain the "files" setting.  This
; setting can list multiple files (separated by whitespace or
; newlines).  It can also contain wildcards.  The filenames are
; interpreted as relative to this file.  Included files *cannot*
; include files themselves.

[include]
files = {str(subconfig_path)}
"""
        return res


def is_supervisor_running():
    result = subprocess.run(["supervisorctl", "status"], capture_output=True)
    if ".sock no such file" in str(result.stdout):
        return False
    else:
        return True


def main(settings: Settings):
    logging.basicConfig(filename=settings.get_logs_dir().joinpath("debug.log"), level=logging.DEBUG)

    working_dir = settings.get_working_dir()
    supervisor_config_path = settings.get_supervisor_dir().joinpath("supervisor.conf")
    supervisor_config_path.touch()
    if not is_supervisor_running():
        if settings.full_control_supervisord:
            logger.info("supervisor is not running, starting it ...")
            supervisor_base_config_path = settings.get_supervisor_dir().joinpath("base_supervisor.conf")
            with open(supervisor_base_config_path, "wb") as f:
                f.write(settings.get_supervisor_base_config(supervisor_config_path).encode("utf-8"))
            result = subprocess.run(["supervisord", "-c", str(supervisor_base_config_path)], capture_output=True)
            if result.returncode != 0:
                logger.critical("failed to starting supervisord.")
            else:
                logger.info("supervisor started successfully.")
        else:
            logger.critical("supervisor is not running, start it !!!")

    while True:
        try:
            headers = {"Authorization": f"Api-Key {settings.api_key}"}
            payload = get_base_sync_request_payload()
            r = requests.post(settings.get_base_sync_url(), json=payload, headers=headers)
            response = r.json()
            logger.debug(f"base-sync response with {r.status_code=} and content is:\n\n{response}")
            if r.status_code != 200:
                next_try_in = settings.interval_sec * 0.3
                logger.warning(f"base-sync returned {r.status_code=}, {next_try_in=}")
                time.sleep(next_try_in)
                continue

            response = BaseSyncResponse(**response)
            new_supervisor_config = ""
            for config in response.configs:
                if config.program.inner_binary_path:
                    binary_path = Path(config.program.inner_binary_path)
                    if not binary_path.is_file():
                        logger.critical(f"{binary_path=} is not a valid file")
                        continue
                elif outer_binary_identifier := config.program.outer_binary_identifier:
                    expected_bin_dir = working_dir.joinpath("bin", outer_binary_identifier)
                    if expected_bin_dir.is_file():
                        binary_path = expected_bin_dir
                    else:
                        headers = {"Authorization": f"Api-Key {settings.api_key}"}
                        r = requests.get(
                            settings.get_binary_content_url(outer_binary_identifier), json={}, headers=headers
                        )
                        file_bin = r.content
                        binary_path = settings.get_bin_dir().joinpath(outer_binary_identifier)
                        with open(binary_path, "wb") as f:
                            f.write(file_bin)
                        os.chmod(binary_path, 0o755)
                if configfile_content := config.configfile_content:
                    conf_dir = settings.get_conf_dir()
                    conf_path = conf_dir.joinpath(config.hash)
                    if not conf_path.is_file():
                        with open(conf_path, "wb") as f:
                            f.write(configfile_content.encode("utf-8"))
                entry_command = rf"{binary_path} \{config.run_opts.replace(settings.get_configfile_path_placeholder(), str(conf_path))}"
                new_supervisor_config += f"""
                \n
                # config_hash={config.hash}
                [program:{config.id}]
                command={entry_command}
                autostart=true
                autorestart=true
                priority=10
                """
            with open(supervisor_config_path, encoding="utf8") as f:
                current = f.read()
            if current == new_supervisor_config:
                logging.debug("already up to date.")
            else:
                logging.debug("change found.")
                with open(supervisor_config_path, "wb") as f:
                    f.write(new_supervisor_config.encode("utf-8"))
                if not is_supervisor_running():
                    if settings.full_control_supervisord:
                        logger.info("supervisor is not running, starting it ...")
                        supervisor_base_config_path = settings.get_supervisor_dir().joinpath("base_supervisor.conf")
                        with open(supervisor_base_config_path, "wb") as f:
                            f.write(settings.get_supervisor_base_config(supervisor_config_path).encode("utf-8"))
                        result = subprocess.run(
                            ["supervisord", "-c", str(supervisor_base_config_path)], capture_output=True
                        )
                        if result.returncode != 0:
                            logger.critical("failed to starting supervisord.")
                        else:
                            logger.info("supervisor started successfully.")
                    else:
                        logger.critical("supervisor is not running, start it !!!")
                else:
                    res = subprocess.run(["supervisorctl", "reread"], capture_output=True)
                    if res.returncode != 0:
                        logging.critical(res)
                        continue
                    res = subprocess.run(["supervisorctl", "update"], capture_output=True)
                    if res.returncode != 0:
                        logging.critical(res)
                        continue
                    logging.info("supervisor updated")

        except Exception as e:
            next_try_in = settings.interval_sec * 0.3
            logger.error(e, f"{next_try_in=}")
            time.sleep(next_try_in)
            continue

        time.sleep(settings.interval_sec)

def get_base_sync_request_payload():
    res = subprocess.run(["ip", "a"], capture_output=True)
    base_sync_request = BaseSyncRequest(metrics=MetricRequest(ip_a=res.stdout.decode("utf-8")))
    return base_sync_request.model_dump()

def cli():
    settings = Settings()
    main(settings=settings)
