"""Register an application login locally on Linux without exposing its password."""
import argparse
import getpass
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from common.config import load_config
from storage.encrypted import EncryptedStore
from server.auth import save_account

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--config",default="config/app.local.json");parser.add_argument("--id",default="admin")
    args=parser.parse_args();config=load_config(args.config)
    password=getpass.getpass("Application password: ")
    if password!=getpass.getpass("Confirm password: "):
        raise SystemExit("Passwords do not match")
    save_account(EncryptedStore(config.data_directory,config.key_file),args.id,password)
    print("Application login registered; no password printed")
if __name__=="__main__":main()
