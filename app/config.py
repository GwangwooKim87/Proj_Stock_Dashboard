"""Config: loads all broker/API settings from env_file (/opt/data/.env).."""
import os

class Settings:

    def __init__(self):
        e = os.environ
        self.KIWOOM_APP_KEY = e.get("KIWOOM_APP_KEY", "").strip()
        self.KIWOOM_APP_SECRET = e.get("KIWOOM_APP_SECRET", "").strip()
        self.KIWOOM_SERVER = e.get("KIWOOM_SERVER", "real").strip()
        self.KIWOOM_IP_ALLOWLIST = e.get("KIWOOM_IP_ALLOWLIST", "").strip()
        self.TOSSINVEST_CLIENT_ID = e.get("TOSSINVEST_CLIENT_ID", "").strip()
        self.TOSSINVEST_CLIENT_SECRET = e.get("TOSSINVEST_CLIENT_SECRET", "").strip()
        self.TOSSINVEST_SCOPE = e.get("TOSSINVEST_SCOPE", "").strip()
        self.FX_BASE_URL = e.get("FX_BASE_URL", "").strip()
        self.EXCHANGE_RATE_API_URL = e.get("EXCHANGE_RATE_API_URL", "").strip()
        self.DASHBOARD_PORT = int(e.get("DASHBOARD_PORT", "8080"))
        self.DB_PATH = "/data/dashboard.db"


settings = Settings()
