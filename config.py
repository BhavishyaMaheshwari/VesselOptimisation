"""
Configuration settings for the SIH Logistics Optimization Dashboard
"""
import os

# Server configuration
DEFAULT_PORT = 5006
DEFAULT_HOST = '127.0.0.1'
DEFAULT_DEBUG = False

# Get port from environment variable or use default
PORT = int(os.environ.get('DASH_PORT', DEFAULT_PORT))
HOST = os.environ.get('DASH_HOST', DEFAULT_HOST)
DEBUG = os.environ.get('DASH_DEBUG', str(DEFAULT_DEBUG)).lower() == 'true'

# Dashboard URL
DASHBOARD_URL = f"http://{HOST}:{PORT}/"

def get_port():
    """Get the configured port"""
    return PORT

def get_host():
    """Get the configured host"""
    return HOST

def get_debug():
    """Get the debug setting"""
    return DEBUG

def get_dashboard_url():
    """Get the complete dashboard URL"""
    return DASHBOARD_URL