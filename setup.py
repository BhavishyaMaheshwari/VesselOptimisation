#!/usr/bin/env python3
"""
Setup script for the SIH Logistics Optimization Dashboard
"""
import subprocess
import sys
import os

def install_requirements():
    """Install required packages"""
    print("📦 Installing required packages...")
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', 'requirements_dash.txt'])
        print("✅ All packages installed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install packages: {e}")
        return False

def run_tests():
    """Run basic tests"""
    print("\n🧪 Running basic tests...")
    try:
        result = subprocess.run([sys.executable, 'tests/test_dash_app.py'], 
                              capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            print("✅ All tests passed!")
            return True
        else:
            print(f"❌ Tests failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"⚠️ Test error: {e}")
        return False

def main():
    """Main setup process"""
    print("🚢🚂 SIH Logistics Optimization Dashboard - Setup")
    print("=" * 60)
    
    # Step 1: Install requirements
    if not install_requirements():
        print("Setup failed at package installation.")
        sys.exit(1)
    
    # Step 2: Run tests
    if not run_tests():
        print("⚠️ Tests failed, but setup completed. You can still try running the app.")
    
    # Step 3: Ready message
    print("\n" + "=" * 60)
    print("🎉 SETUP COMPLETE!")
    print("🚀 Launch the dashboard with:")
    print("   python app.py")
    print("   OR: python run.py")
    print("   OR: python launch_dashboard.py")
    print("🌐 Then open: http://127.0.0.1:5006/")
    print("=" * 60)

if __name__ == "__main__":
    main()