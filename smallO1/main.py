import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from smallo1 import main

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    env_file_path = Path(os.getcwd()).joinpath(".env")
    any_env_set = load_dotenv(env_file_path, override=True)
    if not any_env_set:
        logger.debug("dotenv did not load any envs")
    settings = main.Settings()
    main.main(settings=settings)
