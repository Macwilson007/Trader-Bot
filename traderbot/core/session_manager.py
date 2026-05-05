from datetime import datetime, timezone
import pytz
import sys
sys.path.append('..')
from config import TRADING_SESSIONS


class SessionManager:
    def __init__(self):
        self.sessions = TRADING_SESSIONS
        self.timezone = pytz.timezone("GMT")
        self.last_session_traded = None
    
    def get_current_session(self):
        now = datetime.now(self.timezone)
        current_hour = now.hour
        current_minute = now.minute
        
        for session in self.sessions:
            if current_hour == session["hour"] and current_minute < 5:
                return session
        return None
    
    def should_trade(self):
        session = self.get_current_session()
        if session is None:
            return False, None
        
        if self.last_session_traded == session["name"]:
            return False, None
        
        return True, session
    
    def mark_session_traded(self, session_name):
        self.last_session_traded = session_name
    
    def get_next_session_time(self):
        now = datetime.now(self.timezone)
        current_minutes = now.hour * 60 + now.minute
        
        for session in self.sessions:
            session_minutes = session["hour"] * 60 + session["minute"]
            if session_minutes > current_minutes:
                return session
        return None
    
    def is_trading_hours(self):
        now = datetime.now(self.timezone)
        hour = now.hour
        return 8 <= hour <= 17
    
    def get_session_info(self):
        return self.sessions


if __name__ == "__main__":
    manager = SessionManager()
    print("Sessions:", manager.get_session_info())
    should_trade, session = manager.should_trade()
    print(f"Should trade: {should_trade}, Session: {session}")
    print(f"Trading hours: {manager.is_trading_hours()}")