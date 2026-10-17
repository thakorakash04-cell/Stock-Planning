"""Consistent Indian Standard Time for user-facing timestamps."""
from datetime import datetime
from zoneinfo import ZoneInfo
IST=ZoneInfo('Asia/Kolkata')
def display(value):
    return datetime.fromtimestamp(value,IST).strftime('%d %b %Y %H:%M:%S IST') if value is not None else 'Not recorded'
