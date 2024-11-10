import os
from pathlib import Path

from dotenv import load_dotenv

from smallo1 import main

if __name__ == "__main__":
    env_file_path = Path(os.getcwd()).joinpath(".env")
    load_dotenv(env_file_path, override=True)
    settings = main.Settings()
    main.main(settings=settings)
