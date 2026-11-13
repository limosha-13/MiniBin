import ctypes
import os
import queue
import sys
import threading
import tkinter as tk
from ctypes import wintypes

from PIL import Image, ImageDraw
import pystray
import winshell


STOP_EVENT = threading.Event()


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
        return None


def empty_recycle_bin():
    """Очищает Корзину только по явной команде пользователя."""
    try:
        winshell.recycle_bin().empty(
            confirm=False,
            show_progress=False,
            sound=False,
        )
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
    """Приложение для просмотра и ручной очистки Корзины из системного трея."""

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

        self.commands = queue.Queue()
        self.icon = None
        self.tray_menu_window = None

        self.root.after(100, self.process_commands)

    def create_tray_icon(self):
        is_full = check_recycle_bin_status()
        self.icon = MiniBinTrayIcon(
            "minibin",
            load_custom_icon(is_full=is_full is True),
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

    def on_exit(self, icon, item):
        STOP_EVENT.set()
        icon.stop()
        self.commands.put("quit")

    def process_commands(self):
        try:
            while True:
                command = self.commands.get_nowait()

                if command == "double_click":
                    self.on_clear(self.icon, None)
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

        is_full = check_recycle_bin_status()
        if is_full is None:
            status = "Не удалось получить статус Корзины"
        else:
            status = "Корзина полная" if is_full else "Корзина пуста"
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

    def background_worker(self):
        """Обновляет значок в соответствии с содержимым Корзины."""
        last_full_state = None

        while not STOP_EVENT.is_set():
            try:
                is_full = check_recycle_bin_status()
                if (
                    is_full is not None
                    and is_full != last_full_state
                    and self.icon is not None
                ):
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
