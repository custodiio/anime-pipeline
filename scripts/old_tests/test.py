import sys
import subprocess
from bot.drive_manager import split_video
try:
    split_video("test.mp4", "test_split", parts=2)
    print("Success")
except subprocess.CalledProcessError as e:
    print(e.stderr.decode('utf-8', errors='ignore'))
    print(e.stdout.decode('utf-8', errors='ignore'))
