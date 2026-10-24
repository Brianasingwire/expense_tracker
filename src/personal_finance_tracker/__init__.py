"""Personal finance / expense tracker built with SQLite, Pandas, Matplotlib and Streamlit."""

import sys
from pathlib import Path


def main() -> None:
    """Entry point for the `personal-finance-tracker` command: launches the Streamlit app."""
    from streamlit.web import cli as stcli

    app = Path(__file__).with_name("app.py")
    # Bind to localhost only: the app has no auth. Pass --server.address to override.
    sys.argv = ["streamlit", "run", str(app), "--server.address=127.0.0.1", *sys.argv[1:]]
    sys.exit(stcli.main())
