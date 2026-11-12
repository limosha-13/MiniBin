# MiniBin 🗑️⚙️

<p align="center">
  <b>[ 🇺🇸 English ] | [ <a href="README_ru.md">🇷🇺 Русский</a> ]</b>
</p>

A lightweight, minimalist Windows system tray utility for managing and auto-cleaning your Recycle Bin with a clean dark interface.

---

## Features
* **System Tray Integration:** Runs quietly in the background without cluttering your taskbar.
* **Minimalist Dark UI:** Clean settings panel built with native `tkinter` to keep resource usage to an absolute minimum.
* **Smart Date-Based Auto-Cleaning:** Tracks the exact time difference since the last cleanup. Even if you reboot your PC, it remembers the schedule.
* **Dynamic Custom Icons:** Supports custom `empty.ico` and `full.ico` files to visually reflect the Recycle Bin's state.
* **Instant Actions:** 
  * Double-click the tray icon to empty the bin instantly.
  * Right-click menu for **Empty Now**, **Open Recycle Bin**, **Settings**, and **Exit**.
* **Zero System Bloat:** Stores its configuration safely inside `%appdata%\MiniBin`, leaving no junk files in your installation directory.

## Requirements & Installation
1. Python 3.x installed on your system.
2. Install the required dependencies:
   ```bash
   pip install pystray Pillow winshell

   > **⚠️ Antivirus Warning (False Positive)**
> Windows Defender or other antivirus software may occasionally flag the compiled `MiniBin.exe` as a threat (e.g., `Trojan:Win32/Bearfoos.B!ml`). This is a **common false positive** caused by PyInstaller packaging an uncompiled Python script. MiniBin is 100% safe and open-source. To prevent Windows from blocking it, simply add the application folder to your antivirus exclusions.
