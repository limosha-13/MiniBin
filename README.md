# MiniBin 🗑️⚙️

<p align="center">
  <b>A lightweight, minimalist Windows system tray utility for managing and auto-cleaning your Recycle Bin, styled with a modern dark Deadlock aesthetic.</b><br>
  <b>Легковесная минималистичная утилита для системного трея Windows с автоочисткой корзины и темным тактическим дизайном в стиле Deadlock.</b>
</p>

<p align="center">
  <a href="#english">English</a> • <a href="#русский">Русский</a>
</p>

---

<a name="english"></a>
## 🇺🇸 English

### Features
* **System Tray Integration:** Runs quietly in the background without cluttering your taskbar.
* **Deadlock Dark Aesthetics:** Clean, minimalist settings panel built with native `tkinter` to keep resource usage to an absolute minimum.
* **Smart Date-Based Auto-Cleaning:** Unlike simple timers, it tracks the exact time difference since the last cleanup. Even if you reboot your PC, it remembers the schedule.
* **Dynamic Custom Icons:** Supports custom `empty.ico` and `full.ico` files to visually reflect the Recycle Bin's state.
* **Instant Actions:** 
  * Double-click the tray icon to empty the bin instantly.
  * Right-click menu for **Empty Now**, **Open Recycle Bin**, **Settings**, and **Exit**.
* **Zero System Bloat:** Stores its configuration safely inside `%appdata%\DeadlockCleaner`, leaving no junk files in your installation directory.

### Requirements & Installation
1. Python 3.x installed on your system.
2. Install the required dependencies:
   ```bash
   pip install pystray Pillow winshell
