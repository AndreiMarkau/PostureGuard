"""
setup_windows.py — one-time setup helper for Windows.
Run this once after cloning: python setup_windows.py
"""
import subprocess
import sys
import os


def run(cmd: list[str]):
    print(f"\n>>> {' '.join(cmd)}")
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        print(f"WARNING: command exited with code {result.returncode}")
    return result.returncode == 0


def main():
    print("=" * 60)
    print("PostureGuard — Windows Setup")
    print("=" * 60)

    # Check Python version
    major, minor = sys.version_info[:2]
    print(f"\nPython {major}.{minor} detected")
    if major < 3 or (major == 3 and minor < 10):
        print("ERROR: Python 3.10+ required")
        sys.exit(1)

    # Upgrade pip
    run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])

    # Install requirements
    req_file = os.path.join(os.path.dirname(__file__), "requirements.txt")
    run([sys.executable, "-m", "pip", "install", "-r", req_file])

    # Generate alert sound
    alert_path = os.path.join(os.path.dirname(__file__), "assets", "alert.wav")
    if not os.path.isfile(alert_path):
        print("\nGenerating alert sound…")
        from generate_alert import generate_buzzer
        generate_buzzer(alert_path)
        print(f"Alert sound created: {alert_path}")
    else:
        print(f"\nAlert sound already exists: {alert_path}")

    print("\n" + "=" * 60)
    print("Setup complete! Run: python main.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
