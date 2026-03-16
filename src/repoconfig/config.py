import os
from dotenv import load_dotenv

load_dotenv()

ACCESS_TOKEN    = os.getenv("GITHUB_TOKEN")
USER            = "protogia"
HISTORY_FILE    = "traffic_history.csv"
PLOT_DIR        = "static/plotly/home"