import os
from dotenv import load_dotenv

load_dotenv()

ACCESS_TOKEN    = os.getenv("GITHUB_ACCESS_TOKEN")
USER            = "protogia"
HISTORY_DIR    = "data/"
PLOT_DIR        = "plots/" 