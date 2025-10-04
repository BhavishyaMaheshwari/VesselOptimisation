#!/usr/bin/env python3
"""
Launch script for the SIH Logistics Optimization Dashboard
Performs system checks and launches the Dash application
"""
import sys
import subprocess
import importlib
import webbrowser
import time
from pathlib import Path

def check_dependencies():
    """Check if all required packages are installed"""
    required_packages = [
        'dash', 'plotly', 'pandas', 'numpy', 'pulp', 
        'deap', 'scikit-learn', 'dash_bootstrap_components', 
        'dash_daq', 'openpyxl'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            importlib.import_module(package)
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print("❌ Missing required packages:")
        for pkg in missing_packages:
            print(f"   - {pkg}")
        print("\n📦 Install missing packages with:")
        print("pip install -r requirements_dash.txt")
        return False
    
    print("✅ All required packages are installed")
    return True

def check_files():
    """Check if all required files exist"""
    required_files = [
        'app.py', 'data_loader.py', 'milp_optimizer.py', 
        'heuristics.py', 'simulation.py', 'visuals.py', 'utils.py'
    ]
    
    missing_files = []
    
    for file in required_files:
        if not Path(file).exists():
            missing_files.append(file)
    
    if missing_files:
        print("❌ Missing required files:")
        for file in missing_files:
            print(f"   - {file}")
        return False
    
    print("✅ All required files are present")
    return True

def run_quick_test():
    """Run a quick functionality test"""
    print("🧪 Running quick functionality test...")
    
    try:
        result = subprocess.run([sys.executable, 'test_dash_app.py'], 
                              capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            print("✅ Quick test passed - system is ready")
            return True
        else:
            print("❌ Quick test failed:")
            print(result.stderr)
            return False
            
    except subprocess.TimeoutExpired:
        print("⚠️ Quick test timed out - proceeding anyway")
        return True
    except Exception as e:
        print(f"⚠️ Quick test error: {e} - proceeding anyway")
        return True

def launch_dashboard():
    """Launch the Dash dashboard"""
    print("🚀 Launching SIH Logistics Optimization Dashboard...")
    from config import get_dashboard_url
    
    print(f"📊 Dashboard URL: {get_dashboard_url()}")
    print("🔧 Press Ctrl+C to stop the server")
    print("=" * 60)
    
    # Wait a moment then open browser
    def open_browser():
        time.sleep(3)
        try:
            webbrowser.open(get_dashboard_url())
        except:
            pass
    
    import threading
    browser_thread = threading.Thread(target=open_browser)
    browser_thread.daemon = True
    browser_thread.start()
    
    # Launch the app
    try:
        import app
        # Use consolidated server runner
        app.run_server(debug=False)
    except KeyboardInterrupt:
        print("\n👋 Dashboard stopped by user")
    except Exception as e:
        print(f"❌ Error launching dashboard: {e}")
        # Fallback to subprocess
        try:
            subprocess.run([sys.executable, 'app.py'])
        except KeyboardInterrupt:
            print("\n👋 Dashboard stopped by user")

def main():
    """Main launch sequence"""
    print("🚢🚂 SIH Logistics Optimization Dashboard - Launch Sequence")
    print("=" * 60)
    
    # Step 1: Check dependencies
    print("1️⃣ Checking dependencies...")
    if not check_dependencies():
        return False
    
    # Step 2: Check files
    print("\n2️⃣ Checking files...")
    if not check_files():
        return False
    
    # Step 3: Run quick test
    print("\n3️⃣ Running system test...")
    run_quick_test()  # Continue even if test fails
    
    # Step 4: Launch dashboard
    print("\n4️⃣ Launching dashboard...")
    launch_dashboard()
    
    return True

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n👋 Launch cancelled by user")
        sys.exit(0)