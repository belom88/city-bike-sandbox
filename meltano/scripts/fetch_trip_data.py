import requests
import os
from zipfile import ZipFile
from dotenv import load_dotenv

load_dotenv()

DATA_PATH = os.getenv("MELTANO_DATA_PATH", None)
BASE_URL = os.getenv("MELTANO_BASE_URL", "https://s3.amazonaws.com/tripdata")
YYYYMM_CODE = os.getenv("MELTANO_YYYYMM_CODE", "202608")

class ConfigError(Exception):
    pass

def main():
    if DATA_PATH is None:
        raise ConfigError("Temporary data storage path is not defined")

    full_url = f"{BASE_URL}/{YYYYMM_CODE}-citibike-tripdata.zip"
    output_path = f"{DATA_PATH}\\{YYYYMM_CODE}-citibike-tripdata.zip"
    output_csv_path = f"{DATA_PATH}\\{YYYYMM_CODE}-citibike-tripdata"

    r = requests.get(full_url, stream=True)
    byte_counter = 0
    chunk_size = 2048

    with open(output_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=chunk_size):
            f.write(chunk)
            byte_counter = byte_counter + chunk_size
            print(f"Downloaded: {byte_counter}")

    with ZipFile(output_path, "r") as archive:
        archive.extractall(output_csv_path)

if __name__ == "__main__":
    main()