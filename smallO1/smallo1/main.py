import argparse
import importlib.metadata
import logging
import os
import subprocess
import time
import urllib.parse
from hashlib import sha256
from pathlib import Path
from typing import Union

import pydantic
import requests
import sentry_sdk
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

from .api_types import BaseSyncRequest, BaseSyncResponse, MetricRequest

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    interval_sec: int = 10
    api_key: str
    server_base_url: pydantic.HttpUrl
    working_dir: str
    full_control_supervisord: bool
    sentry_dsn: Union[pydantic.HttpUrl, None] = None

    @pydantic.model_validator(mode="before")
    def check_working_dir(cls, values):
        working_dir_val = values["working_dir"]
        path = Path(working_dir_val)
        if not path.is_absolute():
            raise ValueError("specify an absolute path for working_dir")
        path.mkdir(parents=True, exist_ok=True)
        return values

    def get_working_dir(self) -> Path:
        path = Path(self.working_dir)
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
        return urllib.parse.urljoin(str(self.server_base_url), "node-manager/node/base-sync/")

    def get_binary_content_url(self, hash: str):
        return urllib.parse.urljoin(
            str(self.server_base_url), f"node-manager/node/program-binary/hash/{hash}/content/"
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
    _version = importlib.metadata.version("smallo1")
    logging.basicConfig(filename=settings.get_logs_dir().joinpath("debug.log"), level=logging.DEBUG)
    if settings.sentry_dsn:
        logging.debug("sentry is configured")
        sentry_sdk.init(
            dsn=str(settings.sentry_dsn),
            release=_version,
        )
    else:
        logging.debug("sentry is not configured")

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
            headers = {"Authorization": f"Api-Key {settings.api_key}", "User-Agent": f"smallo1:{_version}"}
            payload = get_base_sync_request_payload()
            base_sync_url = settings.get_base_sync_url()
            logger.debug(f"requesting {base_sync_url}")
            r = requests.post(base_sync_url, json=payload, headers=headers)
            if r.status_code != 200:
                next_try_in = settings.interval_sec
                logger.warning(f"base-sync returned {r.status_code=}, {next_try_in=} and the content is \n{r.content}")
                time.sleep(next_try_in)
                continue
            response = r.json()
            logger.debug(f"base-sync respond with {r.status_code=} and content is:\n\n{response}")

            response = BaseSyncResponse(**response)
            new_supervisor_config = ""
            for config in response.configs:
                if config.program.inner_binary_path:
                    binary_path = Path(config.program.inner_binary_path)
                    if not binary_path.is_file():
                        logger.critical(f"inner {binary_path=} is not a valid file")
                        continue
                elif outer_binary_identifier := config.program.outer_binary_identifier:
                    binary_path = settings.get_bin_dir().joinpath(
                        f"{config.program.program_version_id}_{outer_binary_identifier[:6]}"
                    )
                    if not binary_path.is_file():
                        try:
                            download_outerbinary(
                                binary_content_url=settings.get_binary_content_url(outer_binary_identifier),
                                save_to=binary_path,
                                identifier=outer_binary_identifier,
                                api_key=settings.api_key,
                            )
                        except ContentDownloadError as e:
                            logger.critical(f"could not download {outer_binary_identifier} for {config.id=}")
                            continue
                else:
                    raise NotImplementedError
                if configfile_content := config.configfile_content:
                    conf_dir = settings.get_conf_dir()
                    conf_file_name = f"{config.id}_{config.hash[:6]}"
                    if config.config_file_ext:
                        conf_file_name += config.config_file_ext
                    conf_path = conf_dir.joinpath(conf_file_name)
                    if not conf_path.is_file():
                        with open(conf_path, "wb") as f:
                            f.write(configfile_content.encode("utf-8"))
                else:
                    conf_path = None
                    if settings.get_configfile_path_placeholder() in config.run_opts:
                        logger.critical(
                            f"run_opts contains reference to config file while there is no config file, {config.id=}"
                        )

                if conf_path is not None:
                    run_opts = config.run_opts.replace(settings.get_configfile_path_placeholder(), str(conf_path))
                else:
                    run_opts = config.run_opts
                entry_command = f"{binary_path} {run_opts}"

                new_supervisor_config += f"""

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
            sentry_sdk.capture_exception(e)
            next_try_in = settings.interval_sec
            logger.error(e, f"{next_try_in=}")
            time.sleep(next_try_in)
            continue

        time.sleep(settings.interval_sec)


def get_base_sync_request_payload():
    res = subprocess.run(["ip", "a"], capture_output=True)
    base_sync_request = BaseSyncRequest(metrics=MetricRequest(ip_a=res.stdout.decode("utf-8")))
    return base_sync_request.model_dump()


class ContentDownloadError(Exception):
    pass


def download_outerbinary(*, binary_content_url: str, save_to: Path, identifier: str, api_key: str):
    _version = importlib.metadata.version("smallo1")
    retry_limit = 3
    headers = {"Authorization": f"Api-Key {api_key}", "User-Agent": f"smallo1:{_version}"}
    retry_count = 0
    for i in range(retry_limit):
        retry_count += 1
        try:
            r = requests.get(binary_content_url, json={}, headers=headers, stream=True, timeout=(5, 10))
            if r.status_code == 200:
                recieved_sha256 = sha256()
                with open(save_to, "wb") as file:
                    for chunk in r.iter_content(chunk_size=2048):
                        file.write(chunk)
                        recieved_sha256.update(chunk)

                if recieved_sha256.hexdigest() != identifier:
                    logger.debug(f"sha missmatch happened for {identifier=}")
                    os.remove(save_to)
                    continue
                os.chmod(save_to, 0o755)
                logger.debug(f"successfully downloaded {identifier=}")
                break
            else:
                logger.warning(f"binary-content returned {r.status_code=}, and the content is \n{r.text[:50]}")
        except requests.exceptions.Timeout:
            logger.warning(f"timeout in binary download at {retry_count=}")
            if save_to.exists():
                os.remove(str(save_to))
            continue
    else:
        raise ContentDownloadError()


def cli():
    parser = argparse.ArgumentParser(description="CLI for my_package")
    parser.add_argument("--env-file", type=str, default=None, help="Path to the .env file to load settings from")
    args = parser.parse_args()

    env_file_path = Path(args.env_file).resolve() if args.env_file else None
    if env_file_path is None:
        env_file_path = Path(os.getcwd()).joinpath(".env")

    any_env_set = load_dotenv(env_file_path, override=True)
    if not any_env_set:
        logger.debug("dotenv did not load any envs")

    settings = Settings()
    main(settings=settings)
