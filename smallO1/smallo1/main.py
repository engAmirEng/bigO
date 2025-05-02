import argparse
import datetime
import importlib.metadata
import logging.config
import logging.handlers
import os
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import xmlrpc.client
from hashlib import sha256
from pathlib import Path
from typing import Union, Tuple, Optional, List
import pydantic
import requests
import sentry_sdk
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

from .api_types import BaseSyncRequest, BaseSyncResponse, MetricRequest, SupervisorProcessInfoDict, \
    SupervisorProcessTailLog, ConfigStateRequest
from . import utils

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    is_dev: bool = False
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

    def get_timeout(self) -> Optional[Tuple[int, int]]:
        if self.is_dev:
            return None
        return 5, 10

    def get_binary_content_url(self, hash: str):
        return urllib.parse.urljoin(
            str(self.server_base_url), f"node-manager/node/program-binary/hash/{hash}/content/"
        )

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


def is_supervisor_running(sup_server: xmlrpc.client.ServerProxy):
    try:
        res = sup_server.supervisor.getState()
    except FileNotFoundError:
        return False
    return res["statecode"] == 1


def main(settings: Settings):
    _version = importlib.metadata.version("smallo1")
    formatter = logging.Formatter("%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s")
    formatter.converter = time.gmtime
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)
    file_handler = logging.handlers.RotatingFileHandler(
        settings.get_logs_dir().joinpath("debug.log"),
        maxBytes=50 * 1024 * 1024,
        backupCount=0
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    if settings.is_dev:
        root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
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
    sup_server = xmlrpc.client.ServerProxy('http://dummy', transport=utils.UnixStreamTransport("/var/run/supervisor.sock"))
    if not is_supervisor_running(sup_server=sup_server):
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
            base_sync_url = settings.get_base_sync_url()
            logger.debug(f"requesting {base_sync_url}")
            with BaseSyncRequestPayload(sup_server=sup_server, backup_dir=settings.get_logs_dir(), self_log_file=settings.get_logs_dir().joinpath("debug.log")) as payloadmanager:
                r = requests.post(base_sync_url, json=payloadmanager.payload.model_dump(mode="json"), headers=headers, timeout=settings.get_timeout())
                if r.status_code != 200:
                    next_try_in = settings.interval_sec
                    logger.warning(f"base-sync returned {r.status_code=}, {next_try_in=} and the content is {r.content}")
                    time.sleep(next_try_in)
                    continue
                payloadmanager.commited()

            response = r.json()
            logger.debug(f"base-sync respond with {r.status_code=} and content is: {response}")

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
                                timeout=settings.get_timeout()
                            )
                        except ContentDownloadError as e:
                            logger.critical(f"could not download {outer_binary_identifier} for {config.id=}")
                            continue
                else:
                    raise NotImplementedError
                conf_dir = settings.get_conf_dir()
                for dependant_file in config.dependant_files:
                    conf_file_name = f"{config.id}_{config.hash[:6]}_{dependant_file.key}"
                    if dependant_file.extension:
                        conf_file_name += dependant_file.extension
                    conf_path = conf_dir.joinpath(conf_file_name)
                    dependant_file.set_dest(conf_path)
                for dependant_file in response.global_deps:
                    conf_file_name = f"global_deps_{dependant_file.key}_{dependant_file.hash[:6]}"
                    if dependant_file.extension:
                        conf_file_name += dependant_file.extension
                    conf_path = conf_dir.joinpath(conf_file_name)
                    dependant_file.set_dest(conf_path)
                for i in [*response.global_deps, *config.dependant_files]:
                    i.process_content([*response.global_deps, *config.dependant_files])
                    if not i._dest_path.is_file():
                        with open(i._dest_path, "wb") as f:
                            f.write(i._processed_content.encode("utf-8"))
                config.process_run_opts([*response.global_deps, *config.dependant_files])
                if config.comma_separated_environment:
                    config.process_comma_separated_environment([*response.global_deps, *config.dependant_files])
                run_opts = config._processed_run_opts
                entry_command = f"{binary_path} {run_opts}"

                new_supervisor_config += f"""

# config_hash={config.hash}
[program:{config.id}]
command={entry_command}
autostart=true
autorestart=true
priority=10
"""
                if config.comma_separated_environment:
                    new_supervisor_config += f"\nenvironment={config._processed_comma_separated_environment}"

            with open(supervisor_config_path, encoding="utf8") as f:
                current = f.read()
            if current == new_supervisor_config:
                logging.debug("already up to date.")
            else:
                logging.debug("change found.")
                with open(supervisor_config_path, "wb") as f:
                    f.write(new_supervisor_config.encode("utf-8"))
                if not is_supervisor_running(sup_server=sup_server):
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
            logger.error(f"error occurred, {next_try_in=}, {e=}")
            time.sleep(next_try_in)
            continue

        time.sleep(settings.interval_sec)


class BaseSyncRequestPayload:
    def __init__(self, sup_server: xmlrpc.client.ServerProxy, backup_dir: Path, self_log_file: Path):
        self.sup_server = sup_server
        self.backup_dir = backup_dir
        self.is_committed = False
        self.payload: pydantic.BaseModel
        self.self_log_file = self_log_file

    def __enter__(self):
        bytes_limit = 20_000_000
        try:
            all_process_info_list: List[SupervisorProcessInfoDict] = self.sup_server.supervisor.getAllProcessInfo()
        except Exception as e:
            configs_states = None
            if is_supervisor_running(sup_server=self.sup_server):
                raise e
        else:
            configs_states: List[ConfigStateRequest] = []
            with open(self.backup_file, "rb") as f:
                perv_configs_states_json = f.read()
            if perv_configs_states_json:
                perv_configs_states = pydantic.TypeAdapter(List[ConfigStateRequest]).validate_json(perv_configs_states_json)
                configs_states.extend(perv_configs_states)
            for i in all_process_info_list:
                now = datetime.datetime.now().astimezone()
                r = self.sup_server.supervisor.tailProcessStdoutLog(i["name"], 0, bytes_limit)
                stdout_r = SupervisorProcessTailLog(bytes=r[0], offset=r[1], overflow=r[2])
                r = self.sup_server.supervisor.tailProcessStderrLog(i["name"], 0, bytes_limit)
                stderr_r = SupervisorProcessTailLog(bytes=r[0], offset=r[1], overflow=r[2])
                self.sup_server.supervisor.clearProcessLogs(i["name"])
                configs_states.append(
                    ConfigStateRequest(time=now, supervisorprocessinfo=i, stdout=stdout_r, stderr=stderr_r))

        ipa_res = subprocess.run(["ip", "a"], capture_output=True)
        with open(self.self_log_file, "r+b") as f:
            total_size = os.fstat(f.fileno()).st_size
            ef = min(bytes_limit, total_size)
            f.seek(-ef, os.SEEK_END)
            self_log = f.read(ef)
            f.truncate(0)
        self.payload = BaseSyncRequest(
            metrics=MetricRequest(ip_a=ipa_res.stdout.decode("utf-8")),
            configs_states=configs_states,
            smallo1_logs=SupervisorProcessTailLog(bytes=self_log.decode("utf-8"), offset=0, overflow=total_size>bytes_limit)
        )
        return self

    @property
    def backup_file(self) -> Path:
        configs_states = self.backup_dir.joinpath("configs_states.json.bak")
        configs_states.touch(exist_ok=True)
        return configs_states
    def __exit__(self, exc_type, exc_value, exc_traceback):
        if not self.is_committed:
            with open(self.self_log_file, "r+b") as f:
                red_content = self.payload.smallo1_logs.bytes.encode("utf-8")
                content = f.read()
                f.seek(0)
                f.write(red_content)
                f.write(content)

            with open(self.backup_file, "wb") as f:
                ta = pydantic.TypeAdapter(List[ConfigStateRequest])
                f.write(ta.dump_json(self.payload.configs_states))
        else:
            self.backup_file.unlink(missing_ok=True)


    def commited(self):
        self.is_committed = True


class ContentDownloadError(Exception):
    pass


def download_outerbinary(*, binary_content_url: str, save_to: Path, identifier: str, api_key: str, timeout=Optional[Tuple[int, int]]):
    _version = importlib.metadata.version("smallo1")
    retry_limit = 3
    headers = {"Authorization": f"Api-Key {api_key}", "User-Agent": f"smallo1:{_version}"}
    retry_count = 0
    for i in range(retry_limit):
        retry_count += 1
        try:
            r = requests.get(binary_content_url, json={}, headers=headers, stream=True, timeout=timeout)
            if r.status_code == 200:
                recieved_sha256 = sha256()
                with tempfile.NamedTemporaryFile(delete=False) as file:
                    for chunk in r.iter_content(chunk_size=2048):
                        file.write(chunk)
                        recieved_sha256.update(chunk)

                    if recieved_sha256.hexdigest() != identifier:
                        logger.debug(f"sha missmatch happened for {identifier=}")
                        continue
                    shutil.move(file.name, save_to)
                os.chmod(save_to, 0o755)
                logger.debug(f"successfully downloaded {identifier=}")
                break
            else:
                logger.warning(f"binary-content returned {r.status_code=}, and the content is {r.text[:50]}")
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
