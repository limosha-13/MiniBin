from datetime import datetime, timedelta
import ctypes
import json
import os
import queue
import sys
import tempfile
import threading
import tkinter as tk
from ctypes import wintypes
from tkinter import messagebox

from PIL import Image, ImageDraw
import pystray
import winshell


APPDATA_DIR = os.path.join(
    os.getenv("APPDATA") or os.path.expanduser("~"),
    "MiniBin",
)
CONFIG_FILE = os.path.join(APPDATA_DIR, "config.json")

DEFAULT_CONFIG = {
    "auto_clean": True,
    "interval_hours": 24,
    "last_clean_time": None,
    "double_click_action": "open",
}

CONFIG_LOCK = threading.RLock()
STOP_EVENT = threading.Event()


def normalize_config(data):
    """Проверяет настройки и заменяет некорректные значения безопасными."""
    if not isinstance(data, dict):
        data = {}

    auto_clean = data.get("auto_clean", DEFAULT_CONFIG["auto_clean"])
    if not isinstance(auto_clean, bool):
        auto_clean = DEFAULT_CONFIG["auto_clean"]

    interval = data.get("interval_hours", DEFAULT_CONFIG["interval_hours"])
    try:
        if isinstance(interval, bool):
            raise ValueError
        interval = int(interval)
    except (TypeError, ValueError):
        interval = DEFAULT_CONFIG["interval_hours"]

    interval = max(1, min(168, interval))

    last_clean_time = data.get("last_clean_time")
    if last_clean_time is not None:
        if not isinstance(last_clean_time, str):
            last_clean_time = None
        else:
            try:
                datetime.fromisoformat(last_clean_time)
            except ValueError:
                last_clean_time = None

    double_click_action = data.get(
        "double_click_action",
        DEFAULT_CONFIG["double_click_action"],
    )
    if double_click_action not in ("open", "empty", "none"):
        double_click_action = DEFAULT_CONFIG["double_click_action"]

    return {
        "auto_clean": auto_clean,
        "interval_hours": interval,
        "last_clean_time": last_clean_time,
        "double_click_action": double_click_action,
    }


def load_config():
    """Загружает настройки или возвращает значения по умолчанию."""
    with CONFIG_LOCK:
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as file:
                return normalize_config(json.load(file))
        except (OSError, json.JSONDecodeError):
            return DEFAULT_CONFIG.copy()


def save_config(config):
    """Сохраняет настройки через временный файл, чтобы не повредить конфиг."""
    config = normalize_config(config)

    with CONFIG_LOCK:
        os.makedirs(APPDATA_DIR, exist_ok=True)
        temp_path = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=APPDATA_DIR,
                delete=False,
                suffix=".tmp",
            ) as file:
                json.dump(config, file, indent=4, ensure_ascii=False)
                file.flush()
                os.fsync(file.fileno())
                temp_path = file.name

            os.replace(temp_path, CONFIG_FILE)
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass


def resource_path(filename):
    """Ищет ресурс рядом со скриптом или внутри сборки PyInstaller."""
    base_path = getattr(
        sys,
        "_MEIPASS",
        os.path.dirname(os.path.abspath(__file__)),
    )
    return os.path.join(base_path, filename)


def make_fallback_icon(is_full):
    """Создаёт простую запасную иконку, если .ico-файлы не найдены."""
    background = "#ff5a1f" if is_full else "#252a35"
    image = Image.new("RGBA", (64, 64), background)
    draw = ImageDraw.Draw(image)

    # Контрастная корзина с толстой обводкой.
    draw.rectangle((18, 22, 46, 51), fill="#f3f0e8", outline="#111318", width=3)
    draw.rectangle((15, 16, 49, 21), fill="#ff5a1f", outline="#111318", width=3)
    draw.rectangle((25, 11, 39, 14), fill="#f3f0e8", outline="#111318", width=2)
    draw.line((27, 27, 27, 46), fill="#111318", width=3)
    draw.line((32, 27, 32, 46), fill="#111318", width=3)
    draw.line((37, 27, 37, 46), fill="#111318", width=3)

    return image


def load_custom_icon(is_full=False):
    """Загружает full.ico или empty.ico, если файл существует."""
    filename = "full.ico" if is_full else "empty.ico"
    icon_path = resource_path(filename)

    if os.path.exists(icon_path):
        try:
            with Image.open(icon_path) as image:
                return image.convert("RGBA")
        except OSError as error:
            print(f"Не удалось загрузить {filename}: {error}")

    return make_fallback_icon(is_full)


def check_recycle_bin_status():
    """Проверяет, есть ли файлы в Корзине."""
    try:
        return any(winshell.recycle_bin())
    except Exception as error:
        print(f"Не удалось проверить Корзину: {error}")
        return False


def empty_recycle_bin():
    """Очищает Корзину и записывает время очистки."""
    try:
        winshell.recycle_bin().empty(
            confirm=False,
            show_progress=False,
            sound=False,
        )

        config = load_config()
        config["last_clean_time"] = datetime.now().isoformat(timespec="seconds")
        save_config(config)

        return True
    except Exception as error:
        print(f"Ошибка при очистке Корзины: {error}")
        return False


def open_recycle_bin():
    """Открывает стандартное окно Корзины Windows."""
    try:
        os.startfile("shell:RecycleBinFolder")
    except OSError as error:
        print(f"Не удалось открыть Корзину: {error}")


class MiniBinTrayIcon(pystray.Icon):
    """Использует собственное меню и двойной щелчок Windows в системном трее."""

    WM_LBUTTONUP = 0x0202
    WM_LBUTTONDBLCLK = 0x0203
    WM_RBUTTONUP = 0x0205

    def __init__(self, *args, on_double_click, on_right_click, **kwargs):
        self.on_double_click = on_double_click
        self.on_right_click = on_right_click
        super().__init__(*args, menu=None, **kwargs)

    def _on_notify(self, wparam, lparam):
        if lparam == self.WM_LBUTTONDBLCLK:
            self.on_double_click()
        elif lparam == self.WM_RBUTTONUP:
            point = wintypes.POINT()
            if not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
                raise ctypes.WinError()
            self.on_right_click(point.x, point.y)
        elif lparam != self.WM_LBUTTONUP:
            super()._on_notify(wparam, lparam)


class MiniBinApp:
    """Приложение с иконкой в трее и окном настроек."""

    BG = "#0b0b0f"
    PANEL = "#17171d"
    PANEL_HOVER = "#25252d"
    FG = "#f5f5f7"
    MUTED = "#a1a1aa"
    ACCENT = "#a8c7fa"
    ACCENT_HOVER = "#c5d9ff"
    OUTLINE = "#292930"

    def __init__(self):
        # Tkinter создаётся в главном потоке.
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("MiniBin")
        self.root.configure(bg=self.BG)
        self.root.protocol("WM_DELETE_WINDOW", self.hide_settings)

        self.commands = queue.Queue()
        self.settings_window = None
        self.auto_var = None
        self.interval_var = None
        self.double_click_var = None
        self.icon = None
        self.tray_menu_window = None

        self.root.after(100, self.process_commands)

    def create_tray_icon(self):
        self.icon = MiniBinTrayIcon(
            "minibin",
            load_custom_icon(is_full=check_recycle_bin_status()),
            "MiniBin",
            on_double_click=self.on_tray_double_click,
            on_right_click=self.on_tray_right_click,
        )

    def on_tray_double_click(self):
        self.commands.put("double_click")

    def on_tray_right_click(self, x, y):
        self.commands.put(("show_tray_menu", x, y))

    def on_clear(self, icon, item):
        if empty_recycle_bin() and self.icon is not None:
            self.icon.icon = load_custom_icon(is_full=False)

    def on_open_bin(self, icon, item):
        open_recycle_bin()

    def on_settings(self, icon, item):
        # Обращение к Tkinter выполняется в главном потоке через очередь.
        self.commands.put("show_settings")

    def on_exit(self, icon, item):
        STOP_EVENT.set()
        icon.stop()
        self.commands.put("quit")

    def process_commands(self):
        try:
            while True:
                command = self.commands.get_nowait()

                if command == "show_settings":
                    self.show_settings()
                elif command == "double_click":
                    action = load_config()["double_click_action"]
                    if action == "open":
                        self.on_open_bin(self.icon, None)
                    elif action == "empty":
                        self.on_clear(self.icon, None)
                elif command == "open_bin":
                    self.on_open_bin(self.icon, None)
                elif command == "quit":
                    self.root.quit()
                    return
                elif isinstance(command, tuple) and command[0] == "show_tray_menu":
                    self.show_tray_menu(command[1], command[2])
        except queue.Empty:
            pass

        self.root.after(100, self.process_commands)

    def show_tray_menu(self, x, y):
        self.hide_tray_menu()

        window = tk.Toplevel(self.root)
        self.tray_menu_window = window
        window.overrideredirect(True)
        window.configure(bg=self.PANEL)
        window.attributes("-topmost", True)

        panel = tk.Frame(
            window,
            bg=self.PANEL,
            highlightbackground=self.OUTLINE,
            highlightthickness=1,
            padx=10,
            pady=10,
        )
        panel.pack()

        tk.Label(
            panel,
            text="MiniBin",
            bg=self.PANEL,
            fg=self.FG,
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w", padx=8, pady=(4, 0))

        status = "Корзина полная" if check_recycle_bin_status() else "Корзина пуста"
        tk.Label(
            panel,
            text=status,
            bg=self.PANEL,
            fg=self.MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=8, pady=(0, 8))

        def add_action(text, action, primary=False):
            background = self.ACCENT if primary else self.PANEL
            foreground = "#101318" if primary else self.FG
            hover = self.ACCENT_HOVER if primary else self.PANEL_HOVER

            def invoke():
                self.hide_tray_menu()
                action()

            button = tk.Button(
                panel,
                text=text,
                command=invoke,
                anchor="w",
                bg=background,
                fg=foreground,
                activebackground=hover,
                activeforeground=foreground,
                relief="flat",
                bd=0,
                padx=12,
                pady=9,
                font=("Segoe UI", 10, "bold" if primary else "normal"),
                takefocus=False,
                cursor="hand2",
            )
            button.pack(fill="x", pady=2)
            button.bind(
                "<Enter>",
                lambda event: button.configure(bg=hover),
            )
            button.bind(
                "<Leave>",
                lambda event: button.configure(bg=background),
            )

        add_action("Очистить корзину", lambda: self.on_clear(self.icon, None), True)
        add_action("Открыть корзину", lambda: self.on_open_bin(self.icon, None))
        add_action("Настройки", lambda: self.on_settings(self.icon, None))
        add_action("Выход", lambda: self.on_exit(self.icon, None))

        window.bind("<Escape>", lambda event: self.hide_tray_menu())
        window.bind(
            "<FocusOut>",
            lambda event: self.root.after(
                100,
                lambda: self.hide_tray_menu() if self.tray_menu_window is window else None,
            ),
        )
        window.update_idletasks()

        width = window.winfo_reqwidth()
        height = window.winfo_reqheight()
        screen_width = window.winfo_screenwidth()
        screen_height = window.winfo_screenheight()
        x = max(8, min(x - width, screen_width - width - 8))
        y = max(8, min(y - height, screen_height - height - 8))
        window.geometry(f"+{x}+{y}")
        window.lift()
        window.focus_force()

    def hide_tray_menu(self):
        if self.tray_menu_window is not None:
            try:
                self.tray_menu_window.destroy()
            except tk.TclError:
                pass
            self.tray_menu_window = None

    def show_settings(self):
        if self.settings_window is not None:
            try:
                if self.settings_window.winfo_exists():
                    self.settings_window.deiconify()
                    self.settings_window.lift()
                    self.settings_window.focus_force()
                    return
            except tk.TclError:
                self.settings_window = None

        self.create_settings_window()

    def create_settings_window(self):
        config = load_config()

        window = tk.Toplevel(self.root)
        self.settings_window = window
        window.title("MiniBin — Настройки")
        window.geometry("430x550")
        window.resizable(False, False)
        window.configure(bg=self.BG)
        window.protocol("WM_DELETE_WINDOW", self.hide_settings)

        tk.Label(
            window,
            text="MiniBin",
            bg=self.BG,
            fg=self.FG,
            font=("Segoe UI", 24, "bold"),
        ).pack(anchor="w", padx=28, pady=(24, 0))

        tk.Label(
            window,
            text="Настройки очистки корзины",
            bg=self.BG,
            fg=self.MUTED,
            font=("Segoe UI", 10),
        ).pack(anchor="w", padx=30, pady=(2, 18))

        auto_panel = tk.Frame(
            window,
            bg=self.PANEL,
            padx=16,
            pady=14,
        )
        auto_panel.pack(fill="x", padx=24, pady=(0, 12))

        self.auto_var = tk.BooleanVar(value=config["auto_clean"])
        checkbox = tk.Checkbutton(
            auto_panel,
            text="Автоочистка",
            variable=self.auto_var,
            bg=self.PANEL,
            fg=self.FG,
            selectcolor=self.OUTLINE,
            activebackground=self.PANEL,
            activeforeground=self.ACCENT,
            font=("Segoe UI", 11, "bold"),
            padx=2,
            pady=2,
            cursor="hand2",
        )
        checkbox.pack(anchor="w")

        tk.Label(
            auto_panel,
            text="Автоматически очищать корзину по расписанию",
            bg=self.PANEL,
            fg=self.MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=28, pady=(0, 2))

        double_click_panel = tk.Frame(
            window,
            bg=self.PANEL,
            padx=16,
            pady=12,
        )
        double_click_panel.pack(fill="x", padx=24, pady=(0, 12))

        tk.Label(
            double_click_panel,
            text="Двойное нажатие на значок",
            bg=self.PANEL,
            fg=self.FG,
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w")

        self.double_click_var = tk.StringVar(
            value=config["double_click_action"],
        )
        for label, value in (
            ("Открыть Корзину", "open"),
            ("Очистить Корзину", "empty"),
            ("Ничего не делать", "none"),
        ):
            tk.Radiobutton(
                double_click_panel,
                text=label,
                variable=self.double_click_var,
                value=value,
                bg=self.PANEL,
                fg=self.FG,
                selectcolor=self.OUTLINE,
                activebackground=self.PANEL,
                activeforeground=self.ACCENT,
                font=("Segoe UI", 10),
                anchor="w",
                padx=2,
                pady=3,
                cursor="hand2",
            ).pack(anchor="w", fill="x")

        tk.Label(
            double_click_panel,
            text="Очистка удаляет файлы из Корзины.",
            bg=self.PANEL,
            fg=self.MUTED,
            font=("Segoe UI", 8),
        ).pack(anchor="w", padx=28, pady=(2, 0))

        interval_panel = tk.Frame(
            window,
            bg=self.PANEL,
            padx=16,
            pady=14,
        )
        interval_panel.pack(fill="x", padx=24, pady=(0, 12))

        tk.Label(
            interval_panel,
            text="Интервал очистки",
            bg=self.PANEL,
            fg=self.FG,
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w")

        tk.Label(
            interval_panel,
            text="Укажите промежуток от 1 до 168 часов",
            bg=self.PANEL,
            fg=self.MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(2, 10))

        self.interval_var = tk.StringVar(value=str(config["interval_hours"]))
        spinbox = tk.Spinbox(
            interval_panel,
            from_=1,
            to=168,
            textvariable=self.interval_var,
            bg=self.OUTLINE,
            fg=self.FG,
            insertbackground=self.FG,
            buttonbackground=self.PANEL_HOVER,
            relief="flat",
            font=("Segoe UI", 12),
            width=9,
            justify="left",
            highlightthickness=0,
        )
        spinbox.pack(anchor="w")

        save_button = tk.Button(
            window,
            text="Сохранить настройки",
            command=self.save_settings,
            bg=self.ACCENT,
            fg="#101318",
            activebackground=self.ACCENT_HOVER,
            activeforeground="#101318",
            relief="flat",
            bd=0,
            font=("Segoe UI", 10, "bold"),
            padx=20,
            pady=11,
            cursor="hand2",
        )
        save_button.pack(fill="x", padx=24, pady=(0, 12))

        tk.Label(
            window,
            text="Настройки хранятся на этом компьютере",
            bg=self.BG,
            fg=self.MUTED,
            font=("Segoe UI", 8),
        ).pack(side="bottom", pady=12)

    def save_settings(self):
        try:
            interval = int(self.interval_var.get())
            if not 1 <= interval <= 168:
                raise ValueError
        except (TypeError, ValueError):
            messagebox.showerror(
                "Неверный интервал",
                "Введите целое число от 1 до 168.",
                parent=self.settings_window,
            )
            return

        config = load_config()
        config["auto_clean"] = self.auto_var.get()
        config["interval_hours"] = interval
        config["double_click_action"] = self.double_click_var.get()

        try:
            save_config(config)
        except OSError as error:
            messagebox.showerror(
                "Ошибка сохранения",
                f"Не удалось сохранить настройки:\n{error}",
                parent=self.settings_window,
            )
            return

        self.hide_settings()

    def hide_settings(self):
        if self.settings_window is not None:
            try:
                self.settings_window.destroy()
            except tk.TclError:
                pass
            self.settings_window = None

    def background_worker(self):
        """Проверяет расписание и обновляет значок Корзины."""
        last_full_state = None

        while not STOP_EVENT.is_set():
            try:
                config = load_config()

                if config["auto_clean"]:
                    value = config["last_clean_time"]

                    if not value:
                        config["last_clean_time"] = datetime.now().isoformat(
                            timespec="seconds"
                        )
                        save_config(config)
                    else:
                        last_clean_time = datetime.fromisoformat(value)

                        if last_clean_time.tzinfo is not None:
                            last_clean_time = (
                                last_clean_time.astimezone().replace(tzinfo=None)
                            )

                        interval = timedelta(hours=config["interval_hours"])
                        if datetime.now() - last_clean_time >= interval:
                            empty_recycle_bin()

                is_full = check_recycle_bin_status()
                if is_full != last_full_state and self.icon is not None:
                    self.icon.icon = load_custom_icon(is_full=is_full)
                    last_full_state = is_full

            except Exception as error:
                print(f"Ошибка фоновой проверки: {error}")

            STOP_EVENT.wait(20)

    def run(self):
        self.create_tray_icon()

        # Значок работает отдельно, а Tkinter остаётся в главном потоке.
        self.icon.run_detached()

        threading.Thread(
            target=self.background_worker,
            daemon=True,
        ).start()

        self.root.mainloop()


if __name__ == "__main__":
    try:
        MiniBinApp().run()
    except KeyboardInterrupt:
        STOP_EVENT.set()