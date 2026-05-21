import ctypes
import json
import logging
import math
import os
import sys
import threading
import webbrowser
import winreg
from tkinter import BooleanVar

import customtkinter as ctk
import pystray
from PIL import Image, ImageDraw, ImageTk
from config import CURRENT_SESSION, UI_STATE, Config
from single_instance import acquire_single_instance, notify_already_running
from main import start_background_service, stop_background_service
from sender import FAILED_ACCOUNTS, Sender
from updater import UpdateManager
from utils import verify_api_key

COLOR_BG = '#0a0a0f'
COLOR_BORDER = '#2a2a2f'
COLOR_ACCENT = '#f97316'
COLOR_GREEN = '#22c55e'
COLOR_RED = '#ef4444'
COLOR_TEXT_WHITE = '#ffffff'
COLOR_TEXT_GRAY = '#9ca3af'
PORTAL_BASE_RGB = (60, 20, 20)
PORTAL_GLOW_RGB = (220, 40, 40)

ctk.set_appearance_mode('Dark')

RUN_KEY = 'Software\\Microsoft\\Windows\\CurrentVersion\\Run'
REG_VALUE_NAME = 'SkyLinkAgent'
APP_ICON_ICO = os.path.join('assets', 'icon.ico')
APP_ICON_PNG = os.path.join('assets', 'icon.png')
WINDOW_ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)
TRAY_ICON_SIZE = 128
HEADER_LOGO_SIZE = 28


def lerp_color(color1, color2, t):
    r = int(color1[0] + (color2[0] - color1[0]) * t)
    g = int(color1[1] + (color2[1] - color1[1]) * t)
    b = int(color1[2] + (color2[2] - color1[2]) * t)
    return f'#{r:02x}{g:02x}{b:02x}'


def set_windows_taskbar_icons(hwnd, icon_ico_path):
    if not hwnd or not icon_ico_path or not os.path.isfile(icon_ico_path):
        return
    try:
        user32 = ctypes.windll.user32
        LR_LOADFROMFILE = 0x0010
        LR_DEFAULTSIZE = 0x0040
        IMAGE_ICON = 1
        WM_SETICON = 0x0080
        ICON_SMALL = 0
        ICON_BIG = 1
        hicon = user32.LoadImageW(
            None, icon_ico_path, IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE
        )
        if hicon:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon)
            user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon)
    except Exception as e:
        logging.warning('Taskbar icon error: %s', e)


def apply_taskbar_fix(window_id, icon_ico_path=None):
    try:
        hwnd = ctypes.windll.user32.GetParent(window_id)
        if hwnd == 0:
            hwnd = window_id
        GWL_EXSTYLE = -20
        WS_EX_APPWINDOW = 262144
        WS_EX_TOOLWINDOW = 128
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if not style & WS_EX_APPWINDOW:
            style = style & ~WS_EX_TOOLWINDOW
            style = style | WS_EX_APPWINDOW
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
            ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 39)
        set_windows_taskbar_icons(hwnd, icon_ico_path)
    except Exception as e:
        print(f'WinAPI Error: {e}')


def _get_startup_command():
    if getattr(sys, 'frozen', False):
        path = sys.executable
        return f'"{path}"' if ' ' in path else path
    return f'"{sys.executable}" "{os.path.abspath(__file__)}"'


def is_app_in_startup():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ)
        try:
            winreg.QueryValueEx(key, REG_VALUE_NAME)
            return True
        except OSError:
            return False
        finally:
            winreg.CloseKey(key)
    except OSError:
        return False


def add_app_to_startup():
    cmd = _get_startup_command()
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE)
        try:
            winreg.SetValueEx(key, REG_VALUE_NAME, 0, winreg.REG_SZ, cmd)
        finally:
            winreg.CloseKey(key)
        return True
    except OSError as e:
        logging.warning('Could not add to startup: %s', e)
        return False


def remove_app_from_startup():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE)
        try:
            winreg.DeleteValue(key, REG_VALUE_NAME)
        except FileNotFoundError:
            pass
        finally:
            winreg.CloseKey(key)
        return True
    except OSError as e:
        logging.warning('Could not remove from startup: %s', e)
        return False


class AccountRow(ctk.CTkFrame):
    def __init__(self, master, name, api_key, app, is_new=False):
        super().__init__(master, fg_color='transparent')
        self.app = app
        self.commander_name = name
        self.is_new = is_new
        self.grid_columnconfigure(1, weight=1)

        self.lbl_name = ctk.CTkLabel(
            self, text=name, font=('PLAY', 14), text_color=COLOR_TEXT_WHITE, anchor='w'
        )
        self.lbl_name.grid(row=0, column=0, padx=10, pady=(6, 2), sticky='w')

        separator = ctk.CTkFrame(self, height=2, fg_color='#333333', corner_radius=0)
        separator.grid(row=1, column=0, columnspan=2, sticky='ew', padx=30, pady=(5, 0))

        self.status_frame = ctk.CTkFrame(self, fg_color='transparent')
        self.status_frame.grid(row=0, column=1, padx=5, sticky='e')

        self.lbl_status = ctk.CTkLabel(
            self.status_frame, text='LINKED ✓', text_color=COLOR_GREEN, font=('PLAY', 11, 'bold')
        )
        self.lbl_status.pack(side='left', padx=10)

        self.btn_change = ctk.CTkButton(
            self.status_frame,
            text='CHANGE API',
            width=90,
            height=24,
            fg_color='transparent',
            border_width=1,
            border_color='#333333',
            text_color='#9ca3af',
            hover_color='#18181b',
            command=self.show_edit_mode,
        )
        self.btn_change.pack(side='left', padx=5)

        self.btn_delete = ctk.CTkButton(
            self.status_frame,
            text='✕',
            width=30,
            height=30,
            fg_color='transparent',
            text_color='#555555',
            font=('PLAY', 16, 'bold'),
            hover_color='#ef4444',
            command=self.show_confirm_delete,
        )
        self.btn_delete.pack(side='left')

        self.confirm_frame = ctk.CTkFrame(self, fg_color='transparent')
        lbl_confirm = ctk.CTkLabel(self.confirm_frame, text='Delete?', text_color=COLOR_TEXT_GRAY)
        lbl_confirm.pack(side='left', padx=10)
        btn_yes = ctk.CTkButton(
            self.confirm_frame,
            text='YES',
            width=60,
            fg_color=COLOR_RED,
            hover_color='#B91C1C',
            command=self.confirm_delete,
        )
        btn_yes.pack(side='left', padx=5)
        btn_no = ctk.CTkButton(
            self.confirm_frame,
            text='NO',
            width=60,
            fg_color='#333333',
            hover_color='#444444',
            command=self.show_view_mode,
        )
        btn_no.pack(side='left')

        self.edit_frame = ctk.CTkFrame(self, fg_color='transparent')
        self.entry_key = ctk.CTkEntry(
            self.edit_frame, placeholder_text='Paste NEW API Key...', width=300, height=28
        )
        self.entry_key.pack(side='left', padx=5)
        self._bind_key_paste()

        self.btn_paste = ctk.CTkButton(
            self.edit_frame,
            text='PASTE',
            width=50,
            height=28,
            fg_color='#333333',
            hover_color='#444444',
            command=self.paste_from_clipboard,
        )
        self.btn_paste.pack(side='left', padx=(0, 5))

        self.btn_save = ctk.CTkButton(
            self.edit_frame,
            text='SAVE',
            width=60,
            height=28,
            fg_color=COLOR_ACCENT,
            hover_color='#c2410c',
            command=self.save_key,
        )
        self.btn_save.pack(side='left', padx=5)

        self.btn_cancel = ctk.CTkButton(
            self.edit_frame,
            text='✕',
            width=30,
            height=28,
            fg_color='#333333',
            hover_color='#444444',
            command=self.cancel_edit,
        )
        self.btn_cancel.pack(side='left')

    def cancel_edit(self):
        if self.is_new:
            self.destroy()
        else:
            self.show_view_mode()

    def _bind_key_paste(self):
        def on_paste(_event=None):
            self.paste_from_clipboard()
            return 'break'

        for seq in ('<Control-v>', '<Control-V>', '<<Paste>>'):
            self.entry_key.bind(seq, on_paste)
        inner = getattr(self.entry_key, '_entry', None)
        if inner is not None:
            for seq in ('<Control-v>', '<Control-V>', '<<Paste>>'):
                inner.bind(seq, on_paste)

    def paste_from_clipboard(self):
        try:
            text = self.clipboard_get().strip()
            if not text:
                return
            self.entry_key.delete(0, 'end')
            self.entry_key.insert(0, text)
        except Exception:
            pass

    def show_edit_mode(self):
        self.status_frame.grid_forget()
        self.edit_frame.grid(row=0, column=1, padx=5, sticky='e')

    def show_view_mode(self):
        self.edit_frame.grid_forget()
        self.confirm_frame.grid_forget()
        self.status_frame.grid(row=0, column=1, padx=5, sticky='e')

    def show_confirm_delete(self):
        self.status_frame.grid_forget()
        self.edit_frame.grid_forget()
        self.confirm_frame.grid(row=0, column=1, padx=5, sticky='e')

    def confirm_delete(self):
        cache_file = self.app.config.app_data_dir / 'deduplication_cache.json'
        self.app.config.delete_account(self.commander_name)
        Sender.purge_commander_cache(self.commander_name, cache_file)
        self.destroy()

    def save_key(self):
        if not self.winfo_exists():
            return
        new_key = self.entry_key.get().strip()
        if not new_key:
            return
        try:
            self.btn_save.configure(text='...', state='disabled')
            self.app.update()
        except Exception:
            return
        is_valid, result_name = verify_api_key(new_key, self.app.config.API_URL)
        if is_valid:
            self.app.config.save_account(result_name, new_key)
            FAILED_ACCOUNTS.discard(result_name)
            self.app.refresh_account_list()
        else:
            self.entry_key.delete(0, 'end')
            self.entry_key.configure(placeholder_text='Invalid Key')
            self.btn_save.configure(text='SAVE', state='normal')

    def update_auth_status(self):
        if self.commander_name in FAILED_ACCOUNTS:
            self.lbl_status.configure(text='INVALID ✕', text_color=COLOR_RED)
        else:
            self.lbl_status.configure(text='LINKED ✓', text_color=COLOR_GREEN)


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath('.')
    return os.path.join(base_path, relative_path)


def load_font_windows(font_path):
    if not os.path.exists(font_path):
        return False
    path_buf = ctypes.create_unicode_buffer(font_path)
    if ctypes.windll.gdi32.AddFontResourceExW(path_buf, 16, None):
        return True
    return False


_play_font_path = resource_path(os.path.join('assets', 'fonts', 'Play-Regular.ttf'))
if not load_font_windows(_play_font_path):
    logging.warning('Play font not loaded from %s, UI may use fallback font.', _play_font_path)


class SkyLinkGUI(ctk.CTk):
    _DISCLAIMER_EN = {
        'title': 'SkyLink Privacy & Data Policy',
        'body': (
            'ATTENTION: Data Transmission Policy\n\n'
            'This application automatically synchronizes your game data with two systems:\n\n'
            '1. EDDN (Elite Dangerous Data Network) - Global Public Network:\n'
            '   - Sent: Star coordinates, planet scan data, signals, FSD jumps.\n'
            '   - Purpose: Updating public databases (Inara, Spansh, EDSM).\n'
            '   - Privacy: Commander name is anonymized/hashed by the network protocol. '
            'Personal data is NOT sent.\n\n'
            '2. SkyBioML Portal - Private Squadron Server:\n'
            '   - Sent: Ship status, loadouts, cargo, location, credits.\n'
            '   - Purpose: Squadron management tools and analytics.\n'
            '   - Privacy: Data is accessible only to authorized squadron members.\n\n'
            'By using SkyLink, you explicitly consent to the automated transmission of '
            'navigation and exploration data to these networks.'
        ),
        'accept': 'I Accept & Continue',
        'decline': 'Decline & Exit',
    }
    _DISCLAIMER_RU = {
        'title': 'Политика конфиденциальности SkyLink',
        'body': (
            'ВНИМАНИЕ: Политика передачи данных\n\n'
            'Это приложение автоматически синхронизирует ваши данные с двумя системами:\n\n'
            '1. Глобальная сеть EDDN (Elite Dangerous Data Network):\n'
            '   - Отправляются: Координаты звезд, данные сканирования планет, сигналы.\n'
            '   - Цель: Обновление общедоступных баз (Inara, Spansh, EDSM).\n'
            '   - Приватность: Имя пилота анонимизируется протоколом. Личные данные НЕ отправляются.\n\n'
            '2. Портал SkyBioML (Приватный сервер):\n'
            '   - Отправляются: Статус корабля, фиты, груз, местоположение.\n'
            '   - Цель: Работа инструментов эскадрильи.\n'
            '   - Приватность: Данные доступны только авторизованным членам эскадрильи.\n\n'
            'Используя SkyLink, вы подтверждаете согласие на автоматическую отправку '
            'навигационных и исследовательских данных.'
        ),
        'accept': 'Принимаю и Продолжить',
        'decline': 'Отказаться и Выйти',
    }

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.running = True
        self.tray_icon = None
        self.last_tray_color = None
        self._icon_ico_path = resource_path(APP_ICON_ICO)
        self._icon_png_path = resource_path(APP_ICON_PNG)
        self._icon_refs = []
        self._header_logo = None
        self.pulse_phase = 0.0
        self._current_view = None
        self._service_started = False

        self.overrideredirect(True)
        self.geometry('640x420')
        self.configure(fg_color=COLOR_BORDER)
        self.title(f'{config.APP_NAME} {config.SOFTWARE_VERSION} — {config.SOFTWARE_AUTHOR}')
        self.center_window()

        myappid = 'skybioml.skylink.agent.1.02'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

        self._apply_window_icons()

        self.bind('<Map>', self.on_window_map)

        self.inner_frame = ctk.CTkFrame(self, fg_color=COLOR_BG, corner_radius=0)
        self.inner_frame.pack(expand=True, fill='both', padx=1, pady=(1, 4))

        self.create_header()
        self.create_footer()
        self.create_body()

        if self.config.last_accepted_version != self.config.SOFTWARE_VERSION:
            self._draw_disclaimer_view()
        else:
            self._draw_main_view()

        self.start_tray_icon()
        self.update_ui_loop()

        self.updater = UpdateManager(self.config)
        self._update_info = None
        self._update_info_clicked = None
        threading.Thread(target=self._check_for_updates_worker, daemon=True).start()

        if self._load_start_minimized_setting() and self._current_view == 'MAIN':
            self.withdraw()
        else:
            self.show_window()

    def on_window_map(self, event):
        if event.widget == self:
            apply_taskbar_fix(self.winfo_id(), self._icon_ico_path)
            self.unbind('<Map>')

    def _apply_window_icons(self):
        if os.path.isfile(self._icon_ico_path):
            try:
                self.iconbitmap(self._icon_ico_path)
            except Exception as e:
                logging.warning('iconbitmap error: %s', e)
        if not os.path.isfile(self._icon_png_path):
            logging.warning('App icon not found: %s', self._icon_png_path)
            return
        try:
            logo = Image.open(self._icon_png_path).convert('RGBA')
            for size in WINDOW_ICON_SIZES:
                photo = ImageTk.PhotoImage(
                    logo.resize((size, size), Image.Resampling.LANCZOS)
                )
                self._icon_refs.append(photo)
                self.iconphoto(True, self._icon_refs[-1])
        except Exception as e:
            logging.warning('Icon load error: %s', e)

    def center_window(self):
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = screen_width / 2 - 640 / 2
        y = screen_height / 2 - 420 / 2
        self.geometry(f'640x420+{int(x)}+{int(y)}')

    def create_header(self):
        self.header = ctk.CTkFrame(self.inner_frame, fg_color='#18181b', height=44, corner_radius=0)
        self.header.pack(side='top', fill='x')
        self.header.bind('<Button-1>', self.start_move)
        self.header.bind('<B1-Motion>', self.do_move)

        try:
            if os.path.isfile(self._icon_png_path):
                logo_small = Image.open(self._icon_png_path).convert('RGBA')
                logo_small = logo_small.resize(
                    (HEADER_LOGO_SIZE, HEADER_LOGO_SIZE), Image.Resampling.LANCZOS
                )
                self._header_logo = ctk.CTkImage(
                    light_image=logo_small,
                    dark_image=logo_small,
                    size=(HEADER_LOGO_SIZE, HEADER_LOGO_SIZE),
                )
                logo_lbl = ctk.CTkLabel(
                    self.header, text='', image=self._header_logo, width=HEADER_LOGO_SIZE, height=HEADER_LOGO_SIZE
                )
                logo_lbl.pack(side='left', padx=(12, 6))
                logo_lbl.bind('<Button-1>', self.start_move)
                logo_lbl.bind('<B1-Motion>', self.do_move)
        except Exception as e:
            logging.warning('Header logo error: %s', e)
            ctk.CTkLabel(self.header, text='⚡', text_color=COLOR_ACCENT, font=('PLAY', 16)).pack(
                side='left', padx=(15, 5)
            )
        ctk.CTkLabel(
            self.header, text='SKYLINK AGENT', font=('PLAY', 12, 'bold'), text_color='white'
        ).pack(side='left')

        ctk.CTkButton(
            self.header,
            text='✕',
            width=30,
            height=30,
            fg_color='transparent',
            hover_color=COLOR_RED,
            command=self.minimize_to_tray,
        ).pack(side='right', padx=5)

        self.btn_portal = ctk.CTkButton(
            self.header,
            text='SkyBioML Portal',
            width=120,
            height=28,
            fg_color='#2a0a0a',
            hover_color='#551a1a',
            border_width=1,
            border_color='#5a2020',
            text_color='#ffcccc',
            command=lambda: webbrowser.open(self.config.PORTAL_BASE),
        )
        self.btn_portal.pack(side='right', padx=10)

    def create_footer(self):
        self.footer = ctk.CTkFrame(self.inner_frame, fg_color='transparent', height=40)
        self.footer.pack(side='bottom', fill='x', padx=15, pady=10)

        self.btn_add = ctk.CTkButton(
            self.footer,
            text='+ ADD ACCOUNT',
            font=('PLAY', 11, 'bold'),
            fg_color='transparent',
            border_width=1,
            border_color='#3f3f46',
            text_color='#9ca3af',
            hover_color='#27272a',
            width=120,
            height=32,
            command=self.add_manual_account,
        )
        self.btn_add.pack(side='left')

        self._start_minimized_var = BooleanVar(value=self._load_start_minimized_setting())
        self.chk_start_minimized = ctk.CTkCheckBox(
            self.footer,
            text='Start minimized',
            variable=self._start_minimized_var,
            font=('PLAY', 11),
            text_color=COLOR_TEXT_GRAY,
            fg_color='#3f3f46',
            hover_color='#52525b',
            command=self._on_start_minimized_changed,
        )
        self.chk_start_minimized.pack(side='left', padx=(15, 0))

        self._run_at_startup_var = BooleanVar(value=is_app_in_startup())
        self.chk_run_at_startup = ctk.CTkCheckBox(
            self.footer,
            text='RUN AT STARTUP',
            variable=self._run_at_startup_var,
            font=('PLAY', 11),
            text_color=COLOR_TEXT_GRAY,
            fg_color='#3f3f46',
            hover_color='#52525b',
            command=self._on_run_at_startup_changed,
        )
        self.chk_run_at_startup.pack(side='left', padx=(15, 0))

        self.btn_update = ctk.CTkButton(
            self.footer,
            text='',
            font=('PLAY', 11),
            fg_color=COLOR_GREEN,
            hover_color='#16a34a',
            width=140,
            height=28,
            command=self._on_update_click,
        )
        self.btn_update.pack(side='right', padx=(5, 0))
        self.btn_update.pack_forget()

        self.lbl_version = ctk.CTkLabel(
            self.footer,
            text=f'v{self.config.SOFTWARE_VERSION} · {self.config.SOFTWARE_AUTHOR}',
            text_color=COLOR_TEXT_GRAY,
            font=('PLAY', 10),
        )
        self.lbl_version.pack(side='right', padx=(8, 0))

        self.lbl_footer_status = ctk.CTkLabel(
            self.footer, text='Initializing...', text_color=COLOR_TEXT_GRAY, font=('PLAY', 11)
        )
        self.lbl_footer_status.pack(side='right')

    def _settings_path(self):
        return self.config.app_data_dir / 'settings.json'

    def _load_start_minimized_setting(self):
        try:
            p = self._settings_path()
            if p.exists():
                with open(p, 'r', encoding='utf-8') as f:
                    return json.load(f).get('start_minimized', False)
        except Exception:
            pass
        return False

    def _save_start_minimized_setting(self, value):
        self.config.set_setting('start_minimized', bool(value))

    def _on_start_minimized_changed(self):
        self._save_start_minimized_setting(self._start_minimized_var.get())

    def _on_run_at_startup_changed(self):
        want = self._run_at_startup_var.get()
        if want:
            if not add_app_to_startup():
                self._run_at_startup_var.set(False)
        elif not remove_app_from_startup():
            self._run_at_startup_var.set(True)

    def _check_for_updates_worker(self):
        try:
            result = self.updater.check_for_updates()
            if result and getattr(sys, 'frozen', False):
                self.after(0, lambda r=result: (self._clear_body(), self._draw_update_view(r)))
            elif result:
                self.after(0, lambda r=result: self._show_update_button(r))
        except Exception as e:
            logging.debug('Update check error: %s', e)

    def _show_update_button(self, update_info):
        self._update_info = update_info
        version = update_info.get('version', '')
        self.btn_update.configure(text=f'Install {version}')
        self.btn_update.pack(side='right', padx=(5, 0))

    def _on_update_click(self):
        self._update_info_clicked = self._update_info or getattr(self, '_update_info_clicked', None)
        self._update_info = None
        if not self._update_info_clicked:
            return
        if (
            self._current_view == 'UPDATE'
            and getattr(self, '_update_install_btn', None)
            and self._update_install_btn.winfo_exists()
        ):
            self._update_install_btn.configure(state='disabled', text='Downloading...')
        elif getattr(self, 'btn_update', None) and self.btn_update.winfo_exists():
            self.btn_update.configure(state='disabled', text='Downloading...')
        threading.Thread(target=self._download_update_worker, daemon=True).start()

    def _download_update_worker(self):
        try:
            url, portable = self.updater.find_update_asset(
                self._update_info_clicked.get('assets') or []
            )
            if not url:
                self.after(0, self._on_update_download_failed)
                return
            path = self.updater.download_installer(url, portable=portable)
            self.after(
                0,
                lambda p=path, pt=portable: self.updater.run_update_and_exit(p, pt),
            )
        except Exception as e:
            logging.warning('Update download failed: %s', e)
            self.after(0, self._on_update_download_failed)

    def _on_update_download_failed(self):
        if not self.winfo_exists():
            return
        self.show_window()
        info = getattr(self, '_update_info_clicked', None)
        version = info.get('version', '?') if info else '?'
        if (
            self._current_view == 'UPDATE'
            and getattr(self, '_update_install_btn', None)
            and self._update_install_btn.winfo_exists()
        ):
            self._update_install_btn.configure(state='normal', text=f'INSTALL {version}')
        elif getattr(self, 'btn_update', None) and self.btn_update.winfo_exists():
            self.btn_update.configure(state='normal', text=f'Install {version}')

    def _clear_body(self):
        for widget in self.body_frame.winfo_children():
            widget.destroy()

    def create_body(self):
        self.body_frame = ctk.CTkFrame(self.inner_frame, fg_color='transparent')
        self.body_frame.pack(side='top', fill='both', expand=True, padx=5, pady=5)

    def _draw_main_view(self):
        self._current_view = 'MAIN'
        self._clear_body()

        self.active_frame = ctk.CTkFrame(self.body_frame, fg_color='transparent')
        self.active_frame.pack(fill='x', padx=10, pady=(10, 5))

        ctk.CTkLabel(
            self.active_frame,
            text='ACTIVE COMMANDER:',
            text_color=COLOR_TEXT_GRAY,
            font=('PLAY', 10, 'bold'),
        ).pack(anchor='w')

        pilot_row = ctk.CTkFrame(self.active_frame, fg_color='transparent')
        pilot_row.pack(fill='x', pady=(0, 5))
        pilot_row.grid_columnconfigure(1, weight=1)

        self.lbl_commander = ctk.CTkLabel(
            pilot_row, text='WAITING...', font=('PLAY', 20, 'bold'), text_color=COLOR_TEXT_WHITE
        )
        self.lbl_commander.grid(row=0, column=0, sticky='w')

        main_width = 640
        status_win_width = int(main_width * 0.4 * 33 / 22)
        status_win_height = 28
        self._marquee_visible_chars = 33
        self._marquee_offset = 0
        self._marquee_tick = 0
        self._marquee_full_text = ''

        self.status_win = ctk.CTkFrame(
            pilot_row, width=status_win_width, height=status_win_height, fg_color='transparent'
        )
        self.status_win.grid(row=0, column=2, padx=(0, 30), sticky='e')
        self.status_win.grid_propagate(False)

        self.lbl_full_status = ctk.CTkLabel(
            self.status_win,
            text='Initializing...',
            text_color=COLOR_TEXT_GRAY,
            font=('PLAY', 20, 'bold'),
            anchor='e',
        )
        self.lbl_full_status.place(relx=1, rely=0.5, anchor='e', x=-8)

        header_row = ctk.CTkFrame(self.body_frame, fg_color='transparent')
        header_row.pack(fill='x', padx=10, pady=(15, 5))
        ctk.CTkLabel(
            header_row,
            text='REGISTERED ACCOUNTS',
            text_color=COLOR_TEXT_GRAY,
            font=('PLAY', 10, 'bold'),
        ).pack(side='left')
        line = ctk.CTkFrame(header_row, height=2, fg_color='#333333', corner_radius=0)
        line.pack(side='left', fill='x', expand=True, padx=(15, 0), pady=(5, 0))

        self.scroll_frame = ctk.CTkScrollableFrame(
            self.body_frame,
            fg_color='transparent',
            scrollbar_button_color='#1a1a1a',
            scrollbar_button_hover_color='#333333',
        )
        self.scroll_frame.pack(fill='both', expand=True, padx=0, pady=5)

        self.refresh_account_list()

        if not self._service_started:
            threading.Thread(target=start_background_service, args=(self.config,), daemon=True).start()
            self._service_started = True

    def _draw_disclaimer_view(self):
        self._current_view = 'DISCLAIMER'
        self._clear_body()

        def current_content():
            return self._DISCLAIMER_RU if self.config.language == 'ru' else self._DISCLAIMER_EN

        top_frame = ctk.CTkFrame(self.body_frame, fg_color=COLOR_BG, corner_radius=0)
        top_frame.pack(side='top', fill='x', padx=1, pady=(1, 0))

        title_label = ctk.CTkLabel(
            top_frame,
            text=current_content()['title'],
            font=('PLAY', 12, 'bold'),
            text_color=COLOR_TEXT_WHITE,
        )
        title_label.pack(side='left', padx=15, pady=10)

        textbox = ctk.CTkTextbox(
            self.body_frame,
            wrap='word',
            state='disabled',
            font=('PLAY', 11),
            fg_color='#0a0a0f',
        )
        textbox.pack(side='top', fill='both', expand=True, padx=10, pady=10)

        def apply_content():
            c = current_content()
            title_label.configure(text=c['title'])
            textbox.configure(state='normal')
            textbox.delete('1.0', 'end')
            textbox.insert('1.0', c['body'])
            textbox.configure(state='disabled')
            btn_accept.configure(text=c['accept'])
            btn_exit.configure(text=c['decline'])
            lang_btn.configure(text='RU' if self.config.language == 'en' else 'EN')

        def toggle_lang():
            self.config.language = 'ru' if self.config.language == 'en' else 'en'
            apply_content()

        lang_btn = ctk.CTkButton(
            top_frame,
            text='RU' if self.config.language == 'en' else 'EN',
            width=50,
            height=28,
            fg_color='#3f3f46',
            command=toggle_lang,
        )
        lang_btn.pack(side='right', padx=15, pady=8)

        bot_frame = ctk.CTkFrame(self.body_frame, fg_color='transparent')
        bot_frame.pack(side='bottom', fill='x', padx=1, pady=(0, 10))

        btn_frame = ctk.CTkFrame(bot_frame, fg_color='transparent')
        btn_frame.pack(pady=10, padx=15)

        def on_accept():
            self.config.disclaimer_accepted = True
            self.config.set_setting('accepted_version', self.config.SOFTWARE_VERSION)
            self.config.last_accepted_version = self.config.SOFTWARE_VERSION
            self.config.save_disclaimer_state()
            self._clear_body()
            self._draw_main_view()

        def on_exit():
            self.quit_app()

        btn_accept = ctk.CTkButton(
            btn_frame,
            text=current_content()['accept'],
            fg_color=COLOR_GREEN,
            hover_color='#16a34a',
            command=on_accept,
        )
        btn_accept.pack(side='left', padx=(0, 10))

        btn_exit = ctk.CTkButton(
            btn_frame,
            text=current_content()['decline'],
            fg_color=COLOR_RED,
            hover_color='#dc2626',
            command=on_exit,
        )
        btn_exit.pack(side='left')

        apply_content()
        self.show_window()

    def _draw_update_view(self, update_info):
        self._current_view = 'UPDATE'
        self._update_info = update_info
        self._clear_body()

        title = ctk.CTkLabel(
            self.body_frame,
            text='CRITICAL UPDATE',
            font=('PLAY', 14, 'bold'),
            text_color=COLOR_ACCENT,
        )
        title.pack(side='top', padx=15, pady=(15, 5))

        textbox = ctk.CTkTextbox(
            self.body_frame, wrap='word', state='disabled', font=('PLAY', 11), fg_color='#0a0a0f'
        )
        textbox.pack(side='top', fill='both', expand=True, padx=10, pady=5)
        textbox.configure(state='normal')
        textbox.insert('1.0', update_info.get('body', '') or '')
        textbox.configure(state='disabled')

        btn_frame = ctk.CTkFrame(self.body_frame, fg_color='transparent')
        btn_frame.pack(side='bottom', fill='x', pady=15, padx=15)

        version = update_info.get('version', '')
        self._update_install_btn = ctk.CTkButton(
            btn_frame,
            text=f'INSTALL {version}',
            font=('PLAY', 12, 'bold'),
            fg_color=COLOR_GREEN,
            hover_color='#16a34a',
            height=40,
            command=self._on_update_click,
        )
        self._update_install_btn.pack(pady=5)
        self.show_window()

    def start_move(self, event):
        self.x = event.x
        self.y = event.y

    def do_move(self, event):
        x = self.winfo_x() + event.x - self.x
        y = self.winfo_y() + event.y - self.y
        self.geometry(f'+{x}+{y}')

    def start_tray_icon(self):
        threading.Thread(target=self.setup_tray, daemon=True).start()

    def setup_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem('Open SkyLink', self.show_window, default=True),
            pystray.MenuItem('Exit', self.quit_app),
        )
        self.tray_icon = pystray.Icon(
            'SkyLink',
            self.create_tray_image('gray'),
            f'SkyLink {self.config.SOFTWARE_VERSION}',
            menu,
        )
        self.tray_icon.run()

    def create_tray_image(self, color):
        tray_map = {
            'red': 'tray_red.png',
            'green': 'tray_green.png',
            'yellow': 'tray_yellow.png',
            'gray': 'tray_gray.png',
        }
        fname = tray_map.get(color, 'tray_gray.png')
        path = resource_path(os.path.join('assets', fname))
        try:
            if os.path.isfile(path):
                img = Image.open(path).convert('RGBA')
                if img.size != (TRAY_ICON_SIZE, TRAY_ICON_SIZE):
                    img = img.resize((TRAY_ICON_SIZE, TRAY_ICON_SIZE), Image.Resampling.LANCZOS)
                return img
        except OSError:
            pass
        width, height = (TRAY_ICON_SIZE, TRAY_ICON_SIZE)
        image = Image.new('RGB', (width, height), (30, 30, 30))
        dc = ImageDraw.Draw(image)
        fill_map = {
            'red': (239, 68, 68),
            'green': (34, 197, 94),
            'yellow': (255, 193, 7),
            'gray': (100, 100, 100),
        }
        margin = TRAY_ICON_SIZE // 4
        dc.ellipse(
            (margin, margin, TRAY_ICON_SIZE - margin, TRAY_ICON_SIZE - margin),
            fill=fill_map.get(color, (100, 100, 100)),
        )
        return image

    def minimize_to_tray(self):
        self.withdraw()

    def show_window(self, icon=None, item=None):
        self.deiconify()
        self.lift()
        self.focus_force()
        apply_taskbar_fix(self.winfo_id(), self._icon_ico_path)

    def quit_app(self, icon=None, item=None):
        self.running = False
        if self.tray_icon:
            self.tray_icon.stop()
        stop_background_service()
        self.destroy()
        sys.exit(0)

    def update_ui_loop(self):
        if not self.running or not self.winfo_exists():
            return
        if self._current_view != 'MAIN':
            self.after(50, self.update_ui_loop)
            return
        try:
            if UI_STATE.pop('request_show_window', False):
                self.show_window()

            status_text = UI_STATE.get('status', 'Idle')
            current_cmdr = CURRENT_SESSION.get('commander')
            api_key = CURRENT_SESSION.get('api_key')

            if current_cmdr and (not api_key):
                status_text = 'API KEY is required!!!'

            st_lower = status_text.lower()

            if status_text != self._marquee_full_text:
                self._marquee_full_text = status_text
                self._marquee_offset = 0
                self._marquee_tick = 0

            n = self._marquee_visible_chars
            if len(status_text) > n:
                loop_text = (status_text + '   ') * 2
                start = self._marquee_offset % len(loop_text)
                display = (loop_text[start:] + loop_text[:start])[:n]
                self._marquee_tick += 1
                if self._marquee_tick % 3 == 0:
                    self._marquee_offset += 1
                self.lbl_full_status.configure(text=display)
            else:
                self.lbl_full_status.configure(text=status_text)

            if current_cmdr:
                self.lbl_commander.configure(text=current_cmdr)
            else:
                self.lbl_commander.configure(text='WAITING FOR SIGNAL...')

            if current_cmdr:
                if current_cmdr and (not api_key):
                    self.lbl_footer_status.configure(text='NO KEY ●', text_color=COLOR_RED)
                elif 'waiting' in st_lower or 'standby' in st_lower or 'closed' in st_lower:
                    self.lbl_footer_status.configure(text='STANDBY ●', text_color='#FFC107')
                elif (
                    'error' in st_lower
                    or 'failed' in st_lower
                    or 'invalid' in st_lower
                    or 'network' in st_lower
                ):
                    self.lbl_footer_status.configure(text='ERROR ●', text_color=COLOR_RED)
                else:
                    self.lbl_footer_status.configure(text='CONNECTED ●', text_color=COLOR_GREEN)
            else:
                self.lbl_footer_status.configure(text='', text_color=COLOR_TEXT_GRAY)

            for widget in self.scroll_frame.winfo_children():
                if isinstance(widget, AccountRow):
                    widget.update_auth_status()

            target_color = 'gray'
            if current_cmdr and (not api_key):
                target_color = 'red'
            elif 'waiting' in st_lower or 'standby' in st_lower or 'closed' in st_lower:
                target_color = 'yellow'
            elif 'running' in st_lower or 'sent' in st_lower or 'monitoring' in st_lower:
                target_color = 'green'
            elif 'error' in st_lower or 'failed' in st_lower or 'invalid' in st_lower:
                target_color = 'red'

            if self.tray_icon and target_color != self.last_tray_color:
                self.tray_icon.icon = self.create_tray_image(target_color)
                self.last_tray_color = target_color

            self.pulse_phase += 0.15
            t = (math.sin(self.pulse_phase) + 1) / 2
            new_text_color = lerp_color((255, 200, 200), (255, 100, 100), t)
            new_border_color = lerp_color(PORTAL_BASE_RGB, PORTAL_GLOW_RGB, t)
            self.btn_portal.configure(text_color=new_text_color, border_color=new_border_color)
        except (KeyboardInterrupt, RuntimeError, Exception):
            pass
        self.after(50, self.update_ui_loop)

    def refresh_account_list(self):
        if not self.winfo_exists():
            return
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        accounts = self.config.accounts
        if not accounts:
            ctk.CTkLabel(
                self.scroll_frame, text='No accounts linked yet.', text_color='gray'
            ).pack(pady=10)
        else:
            for name, key in accounts.items():
                AccountRow(self.scroll_frame, name, key, self).pack(fill='x', pady=1)

    def add_manual_account(self):
        row = AccountRow(self.scroll_frame, 'NEW CMDR', '', self, is_new=True)
        row.pack(fill='x', pady=2)
        row.show_edit_mode()


if __name__ == '__main__':
    if not acquire_single_instance():
        notify_already_running()
        sys.exit(0)
    config = Config()
    app = SkyLinkGUI(config)
    app.protocol('WM_DELETE_WINDOW', app.minimize_to_tray)
    try:
        app.mainloop()
    except KeyboardInterrupt:
        app.quit_app()
