"""
GoodbyeDPI GUI  —  современная графическая обёртка
Python 3.8+  |  только встроенный tkinter  |  Windows
Запуск от имени Администратора обязателен
"""

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
import subprocess, threading, os, sys, json, ctypes
import urllib.request
import zipfile
import tempfile
import shutil
from pathlib import Path

CONFIG_FILE = "goodbyedpi_gui_config.json"
GDPI_EXE    = "goodbyedpi.exe"
GDPI_RELEASES_URL = "https://api.github.com/repos/ValdikSS/GoodbyeDPI/releases/latest"

# ── Palette ───────────────────────────────────────────────────────────────────
BG       = "#0f1117"
SURFACE  = "#181c27"
SURFACE2 = "#1e2333"
BORDER   = "#2a2f42"
ACCENT   = "#5b6ef5"
ACCENT_H = "#7b8eff"
GREEN    = "#22c55e"
GREEN_H  = "#16a34a"
RED      = "#ef4444"
RED_H    = "#b91c1c"
TEXT     = "#f1f5f9"
TEXT2    = "#8892aa"
TEXT3    = "#535b72"

PRESETS = {
    "1 — минимальный":          ["-1"],
    "2 — базовый":              ["-2"],
    "3 — фрагментация":         ["-3"],
    "4 — HTTPS":                ["-4"],
    "5 — усиленный":            ["-5"],
    "6 — агрессивный":          ["-6"],
    "7 — максимальный":         ["-7"],
    "8 — экспер.":              ["-8"],
    "9 — рекомендуемый":        ["-9"],
    "9 + DNS Яндекс":           ["-9","--dns-addr","77.88.8.8","--dns-port","1253"],
    "9 + DNS Google":           ["-9","--dns-addr","8.8.8.8","--dns-port","53"],
    "9 + DNS Cloudflare":       ["-9","--dns-addr","1.1.1.1","--dns-port","53"],
    "9 + wrong-chksum":         ["-9","--wrong-chksum","--native-frag"],
}


def is_admin():
    try:    return ctypes.windll.shell32.IsUserAnAdmin()
    except: return False


def restart_as_admin():
    ctypes.windll.shell32.ShellExecuteW(None,"runas",sys.executable," ".join(sys.argv),None,1)
    sys.exit()


# ── Downloader ────────────────────────────────────────────────────────────────

import queue

class DownloadDialog(tk.Toplevel):
    """Диалог загрузки GoodbyeDPI"""
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Загрузка GoodbyeDPI")
        self.configure(bg=SURFACE)
        self.geometry("500x300")
        self.resizable(False, False)
        
        # Центрирование
        self.transient(parent)
        self.grab_set()
        self.focus_set()
        
        self._result = None
        self._download_complete = False
        self._error_message = None
        
        # Очередь для передачи обновлений из фонового потока
        self._update_queue = queue.Queue()
        
        self._ui()
        
        # Запускаем загрузку в отдельном потоке
        self._download_thread = threading.Thread(target=self._download_thread_func, daemon=True)
        self._download_thread.start()
        
        # Запускаем обработку очереди
        self._process_queue()
        
    def _ui(self):
        # Заголовок
        title = tk.Label(self, text="Загрузка GoodbyeDPI", 
                        bg=SURFACE, fg=TEXT, font=("Segoe UI", 16, "bold"))
        title.pack(pady=(30, 10))
        
        # Статус
        self.status_label = tk.Label(self, text="Подготовка к загрузке...",
                                    bg=SURFACE, fg=TEXT2, font=("Segoe UI", 10))
        self.status_label.pack(pady=(10, 20))
        
        # Прогресс-бар
        self.progress = ttk.Progressbar(self, length=400, mode='determinate')
        self.progress.pack(pady=10)
        
        # Детали
        self.detail_label = tk.Label(self, text="", bg=SURFACE, fg=TEXT3, 
                                     font=("Segoe UI", 9))
        self.detail_label.pack(pady=5)
        
        # Кнопки
        btn_frame = tk.Frame(self, bg=SURFACE)
        btn_frame.pack(pady=20)
        
        self.cancel_btn = Btn(btn_frame, "Отмена", self._cancel, 
                              bg=SURFACE2, fg=TEXT2, px=12, py=5)
        self.cancel_btn.pack(side="left", padx=5)
        
        self.manual_btn = Btn(btn_frame, "Выбрать вручную", self._manual,
                             bg=SURFACE2, fg=TEXT2, px=12, py=5)
        self.manual_btn.pack(side="left", padx=5)
    
    def _process_queue(self):
        """Обрабатывает сообщения из очереди в главном потоке"""
        try:
            while True:
                msg = self._update_queue.get_nowait()
                if msg['type'] == 'status':
                    self.status_label.config(text=msg['text'])
                elif msg['type'] == 'progress':
                    self.progress.config(value=msg['value'])
                elif msg['type'] == 'detail':
                    self.detail_label.config(text=msg['text'])
                elif msg['type'] == 'error':
                    self._error_message = msg['text']
                elif msg['type'] == 'complete':
                    self._result = msg['result']
                    self._download_complete = True
        except queue.Empty:
            pass
        
        if self._error_message:
            messagebox.showerror("Ошибка загрузки", self._error_message)
            self._error_message = None
        
        if self._download_complete:
            if self._result:
                self.after(1500, self.destroy)
            else:
                self.after(100, self.destroy)
        else:
            # Продолжаем обработку очереди
            self.after(100, self._process_queue)
    
    def _queue_status(self, text):
        """Добавляет обновление статуса в очередь"""
        self._update_queue.put({'type': 'status', 'text': text})
    
    def _queue_progress(self, value):
        """Добавляет обновление прогресса в очередь"""
        self._update_queue.put({'type': 'progress', 'value': value})
    
    def _queue_detail(self, text):
        """Добавляет обновление деталей в очередь"""
        self._update_queue.put({'type': 'detail', 'text': text})
    
    def _queue_error(self, text):
        """Добавляет сообщение об ошибке в очередь"""
        self._update_queue.put({'type': 'error', 'text': text})
    
    def _queue_complete(self, result):
        """Отмечает завершение загрузки"""
        self._update_queue.put({'type': 'complete', 'result': result})
    
    def _cancel(self):
        self._result = None
        self._download_complete = True
        self.destroy()
        
    def _manual(self):
        path = filedialog.askopenfilename(
            title="Выберите goodbyedpi.exe",
            filetypes=[("Executable", "*.exe"), ("All files", "*.*")]
        )
        if path:
            self._result = path
            self._download_complete = True
            self.destroy()
    
    def _download_thread_func(self):
        """Фоновая загрузка GoodbyeDPI и WinDivert.dll"""
        try:
            # Получаем информацию о последнем релизе
            self._queue_status("Получение информации о релизе...")
            self._queue_progress(5)
            self._queue_detail("5%")
            
            req = urllib.request.Request(GDPI_RELEASES_URL)
            req.add_header('User-Agent', 'Mozilla/5.0')
            
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
            
            # Ищем assets для Windows
            assets = data.get('assets', [])
            download_url = None
            version = data.get('tag_name', 'latest')
            
            for asset in assets:
                name = asset.get('name', '').lower()
                if name.endswith('.zip') and ('x86_64' in name or 'win64' in name or 'windows' in name):
                    download_url = asset.get('browser_download_url')
                    break
            
            if not download_url:
                # Если не нашли конкретную версию, пробуем любой zip
                for asset in assets:
                    if asset.get('name', '').lower().endswith('.zip'):
                        download_url = asset.get('browser_download_url')
                        break
            
            if not download_url:
                raise Exception("Не удалось найти файл для загрузки")
            
            # Загружаем файл
            self._queue_status(f"Загрузка GoodbyeDPI {version}...")
            self._queue_progress(10)
            self._queue_detail("10%")
            
            # Создаем временную директорию
            with tempfile.TemporaryDirectory() as temp_dir:
                zip_path = os.path.join(temp_dir, "goodbyedpi.zip")
                
                # Загружаем с прогрессом
                def report_progress(block_num, block_size, total_size):
                    if total_size > 0:
                        downloaded = block_num * block_size
                        percent = min(10 + int(downloaded * 60 / total_size), 70)
                        self._queue_status(f"Загрузка архива: {downloaded // 1024} KB / {total_size // 1024} KB")
                        self._queue_progress(percent)
                        self._queue_detail(f"{percent}%")
                
                urllib.request.urlretrieve(download_url, zip_path, reporthook=report_progress)
                
                # Распаковываем
                self._queue_status("Распаковка архива...")
                self._queue_progress(75)
                self._queue_detail("75%")
                
                extract_dir = os.path.join(temp_dir, "extracted")
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
                
                # Ищем goodbyedpi.exe
                exe_path = None
                for root, dirs, files in os.walk(extract_dir):
                    for file in files:
                        if file.lower() == "goodbyedpi.exe":
                            exe_path = os.path.join(root, file)
                            break
                    if exe_path:
                        break
                
                if not exe_path:
                    raise Exception("goodbyedpi.exe не найден в архиве")
                
                # Проверяем наличие WinDivert.dll в архиве
                self._queue_status("Проверка WinDivert.dll...")
                self._queue_progress(80)
                self._queue_detail("80%")
                
                windivert_path = None
                windivert_versions = ['WinDivert.dll', 'WinDivert64.dll', 'WinDivert32.dll']
                
                for root, dirs, files in os.walk(extract_dir):
                    for file in files:
                        if file in windivert_versions:
                            windivert_path = os.path.join(root, file)
                            break
                    if windivert_path:
                        break
                
                # Копируем goodbyedpi.exe в текущую директорию
                target_path = os.path.join(os.getcwd(), "goodbyedpi.exe")
                shutil.copy2(exe_path, target_path)
                self._queue_status("GoodbyeDPI.exe установлен")
                self._queue_progress(90)
                self._queue_detail("90%")
                
                # Копируем WinDivert.dll если нашли
                if windivert_path:
                    windivert_target = os.path.join(os.getcwd(), "WinDivert.dll")
                    shutil.copy2(windivert_path, windivert_target)
                    self._queue_status("WinDivert.dll установлен")
                else:
                    # Если WinDivert.dll нет в архиве, пробуем скачать отдельно
                    self._queue_status("Загрузка WinDivert.dll...")
                    self._queue_progress(92)
                    self._queue_detail("92%")
                    
                    if self._download_windivert():
                        self._queue_status("WinDivert.dll установлен")
                    else:
                        self._queue_status("WinDivert.dll не найден, но может работать без него")
                
                self._queue_progress(100)
                self._queue_detail("Готово")
                
                # Показываем сообщение об успешной установке
                message = "GoodbyeDPI успешно установлен!"
                if windivert_path or os.path.exists(os.path.join(os.getcwd(), "WinDivert.dll")):
                    message += "\n\nWinDivert.dll также установлен."
                else:
                    message += "\n\nWinDivert.dll не найден. Возможно, потребуется установить его вручную:\nhttps://github.com/ValdikSS/GoodbyeDPI/releases"
                
                self._queue_status("Установка завершена!")
                self._queue_complete(target_path)
                
                # Показываем информационное сообщение в главном потоке
                def show_success():
                    messagebox.showinfo("Установка завершена", message)
                self.after(100, show_success)
                
        except Exception as e:
            error_msg = f"Не удалось загрузить GoodbyeDPI:\n{str(e)}\n\nВы можете скачать его вручную с:\nhttps://github.com/ValdikSS/GoodbyeDPI/releases"
            self._queue_status(f"Ошибка: {str(e)}")
            self._queue_progress(0)
            self._queue_detail("Ошибка")
            self._queue_error(error_msg)
            self._queue_complete(None)

    def _download_windivert(self):
        """Пытается скачать WinDivert.dll отдельно"""
        try:
            # URL для WinDivert.dll (можно обновить при необходимости)
            windivert_urls = [
                "https://github.com/ValdikSS/GoodbyeDPI/releases/download/0.2.3rc3/WinDivert.dll",
                "https://github.com/ValdikSS/GoodbyeDPI/releases/download/0.2.2/WinDivert.dll",
            ]
            
            for url in windivert_urls:
                try:
                    req = urllib.request.Request(url)
                    req.add_header('User-Agent', 'Mozilla/5.0')
                    
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.dll') as tmp:
                        urllib.request.urlretrieve(url, tmp.name)
                        target_path = os.path.join(os.getcwd(), "WinDivert.dll")
                        shutil.copy2(tmp.name, target_path)
                        os.unlink(tmp.name)
                        return True
                except:
                    continue
            
            return False
        except:
            return False

def check_and_download_gdpi(parent):
    """Проверяет наличие goodbyedpi.exe и предлагает скачать"""
    exe_path = os.path.join(os.getcwd(), GDPI_EXE)
    
    # Проверяем в текущей директории
    if os.path.exists(exe_path):
        return exe_path
    
    # Проверяем в PATH
    import shutil
    path_exe = shutil.which(GDPI_EXE)
    if path_exe:
        return path_exe
    
    # Предлагаем скачать
    result = messagebox.askyesno(
        "GoodbyeDPI не найден",
        "GoodbyeDPI не найден в текущей директории.\n\n"
        "Хотите скачать последнюю версию с GitHub?\n"
        "https://github.com/ValdikSS/GoodbyeDPI/releases"
    )
    
    if result:
        dialog = DownloadDialog(parent)
        parent.wait_window(dialog)
        
        if dialog._result and os.path.exists(dialog._result):
            return dialog._result
        elif os.path.exists(exe_path):
            return exe_path
    
    # Если отказался или ошибка - показываем диалог выбора
    path = filedialog.askopenfilename(
        title="Выберите goodbyedpi.exe",
        filetypes=[("Executable", "*.exe"), ("All files", "*.*")]
    )
    
    if path:
        return path
    
    return None


# ── Tiny widget helpers ───────────────────────────────────────────────────────

class Checkbox(tk.Frame):
    """Dark-themed checkbox with label."""
    def __init__(self, parent, variable, text, sub="", **kw):
        super().__init__(parent, bg=SURFACE, **kw)
        self.var = variable
        c = tk.Canvas(self, width=18, height=18, bg=SURFACE, highlightthickness=0, cursor="hand2")
        c.pack(side="left", padx=(0,8), pady=2)
        self._c = c; self._draw()
        c.bind("<Button-1>", self._toggle)
        tf = tk.Frame(self, bg=SURFACE); tf.pack(side="left", fill="x", expand=True)
        lbl = tk.Label(tf, text=text, bg=SURFACE, fg=TEXT, font=("Segoe UI",10), anchor="w", cursor="hand2")
        lbl.pack(anchor="w")
        lbl.bind("<Button-1>", self._toggle)
        if sub:
            tk.Label(tf, text=sub, bg=SURFACE, fg=TEXT3, font=("Segoe UI",8), anchor="w").pack(anchor="w")
        variable.trace_add("write", lambda *_: self._draw())

    def _draw(self):
        self._c.delete("all")
        if self.var.get():
            self._c.create_rectangle(0,0,18,18, fill=ACCENT, outline=ACCENT)
            self._c.create_line(4,9, 7,13, 14,5, fill="white", width=2.5, capstyle="round", joinstyle="round")
        else:
            self._c.create_rectangle(0,0,18,18, fill=SURFACE2, outline=BORDER)

    def _toggle(self, _=None): self.var.set(not self.var.get())


class Inp(tk.Entry):
    def __init__(self, parent, textvariable=None, width=9, **kw):
        super().__init__(parent, textvariable=textvariable, width=width,
            bg=SURFACE2, fg=TEXT, insertbackground=TEXT, relief="flat", bd=0,
            highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT,
            font=("Segoe UI",10), **kw)


class Btn(tk.Label):
    def __init__(self, parent, text, command, bg=ACCENT, fg="white", px=14, py=7, **kw):
        super().__init__(parent, text=text, bg=bg, fg=fg, font=("Segoe UI",10,"bold"),
            padx=px, pady=py, cursor="hand2", relief="flat", **kw)
        self._bg = bg; self._hbg = ACCENT_H if bg==ACCENT else self._lighten(bg)
        self.bind("<Button-1>", lambda _: command())
        self.bind("<Enter>", lambda _: self.config(bg=self._hbg))
        self.bind("<Leave>", lambda _: self.config(bg=self._bg))

    @staticmethod
    def _lighten(hex_col):
        r,g,b = int(hex_col[1:3],16),int(hex_col[3:5],16),int(hex_col[5:7],16)
        return "#{:02x}{:02x}{:02x}".format(min(r+20,255),min(g+20,255),min(b+20,255))


class NavItem(tk.Frame):
    def __init__(self, parent, text, icon, command, **kw):
        super().__init__(parent, bg=BG, cursor="hand2", **kw)
        self._active = False; self._cmd = command
        self._ic = tk.Label(self, text=icon, bg=BG, fg=TEXT3, font=("Segoe UI",12), width=3)
        self._ic.pack(side="left", padx=(8,4))
        self._tx = tk.Label(self, text=text, bg=BG, fg=TEXT3, font=("Segoe UI",10), anchor="w")
        self._tx.pack(side="left", fill="x", expand=True, pady=11)
        self._bar = tk.Frame(self, bg=BG, width=3)
        self._bar.place(x=0, y=0, relheight=1)
        for w in (self, self._ic, self._tx):
            w.bind("<Button-1>", lambda _: self._cmd())
            w.bind("<Enter>",    self._hover_on)
            w.bind("<Leave>",    self._hover_off)

    def _hover_on(self, _=None):
        if not self._active:
            for w in (self, self._ic, self._tx): w.config(bg=SURFACE2)
    def _hover_off(self, _=None):
        if not self._active:
            for w in (self, self._ic, self._tx): w.config(bg=BG)

    def activate(self, on):
        self._active = on
        bg = SURFACE if on else BG
        fg = TEXT    if on else TEXT3
        for w in (self, self._ic, self._tx): w.config(bg=bg)
        self._tx.config(fg=fg); self._ic.config(fg=ACCENT if on else TEXT3)
        self._bar.config(bg=ACCENT if on else bg)


# ── App ───────────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("GoodbyeDPI  GUI")
        self.configure(bg=BG)
        self.minsize(820, 580)
        self.geometry("900,660".replace(",","x"))

        self.proc     = None
        self.running  = False
        self._cfg     = {}
        self._pages   = {}
        self._navitems= {}
        self._cur_page= None

        self._vars()
        self._load_cfg()
        
        # Проверяем и при необходимости скачиваем GoodbyeDPI
        self._check_gdpi()
        
        self._ui()
        self._apply_cfg()
        self._show("home")
        self._preview()
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _check_gdpi(self):
        """Проверяет наличие GoodbyeDPI и предлагает скачать"""
        exe_path = check_and_download_gdpi(self)
        if exe_path:
            self.v_exe.set(exe_path)
        else:
            # Если не удалось получить - используем путь по умолчанию
            if not os.path.exists(self.v_exe.get()):
                messagebox.showwarning(
                    "GoodbyeDPI не найден",
                    "GoodbyeDPI не найден. Вы можете указать путь вручную\n"
                    "или скачать с https://github.com/ValdikSS/GoodbyeDPI/releases"
                )

    # ── Vars ──────────────────────────────────────────────────────────────────

    def _vars(self):
        B = tk.BooleanVar; S = tk.StringVar
        self.v_exe   = S(value=GDPI_EXE)
        self.v_preset= S(value="9 — рекомендуемый")
        self.o_p=B(); self.o_q=B(); self.o_r=B(); self.o_s=B()
        self.o_a=B(); self.o_m=B(); self.o_w=B()
        self.o_f=B(); self.v_f=S(value="2")
        self.o_e=B(); self.v_e=S(value="40")
        self.o_k=B(); self.v_k=S(value="2")
        self.o_n=B(); self.o_nat=B(); self.o_rev=B(); self.o_snifr=B()
        self.o_dns=B(); self.v_daddr=S(value="77.88.8.8"); self.v_dport=S(value="1253")
        self.o_dns6=B(); self.v_d6addr=S(); self.v_d6port=S(value="53")
        self.o_dv=B()
        self.o_wc=B(); self.o_ws=B()
        self.o_sttl=B(); self.v_sttl=S(value="5")
        self.o_attl=B(); self.v_attl=S(value="1-4-10")
        self.o_mttl=B(); self.v_mttl=S(value="3")
        self.o_fg=B();   self.v_fg=S(value="4")
        self.o_fr=B();   self.v_fr=S(value="2")
        self.o_fs=B();   self.v_fs=S(value="www.google.com")
        self.o_bl=B();   self.v_bl=S()
        self.o_ns=B()
        self.o_mp=B();   self.v_mp=S(value="1200")
        self.o_pt=B();   self.v_pt=S(value="443")
        all_v = [
            self.o_p,self.o_q,self.o_r,self.o_s,self.o_a,self.o_m,self.o_w,
            self.o_f,self.v_f,self.o_e,self.v_e,self.o_k,self.v_k,self.o_n,self.o_nat,self.o_rev,self.o_snifr,
            self.o_dns,self.v_daddr,self.v_dport,self.o_dns6,self.v_d6addr,self.v_d6port,self.o_dv,
            self.o_wc,self.o_ws,self.o_sttl,self.v_sttl,self.o_attl,self.v_attl,
            self.o_mttl,self.v_mttl,self.o_fg,self.v_fg,self.o_fr,self.v_fr,self.o_fs,self.v_fs,
            self.o_bl,self.v_bl,self.o_ns,self.o_mp,self.v_mp,self.o_pt,self.v_pt,
        ]
        for v in all_v: v.trace_add("write", lambda *_: self._preview())

    # ── Config ────────────────────────────────────────────────────────────────

    _CFG_KEYS = [
        "v_exe","v_preset",
        "o_p","o_q","o_r","o_s","o_a","o_m","o_w",
        "o_f","v_f","o_e","v_e","o_k","v_k","o_n","o_nat","o_rev","o_snifr",
        "o_dns","v_daddr","v_dport","o_dns6","v_d6addr","v_d6port","o_dv",
        "o_wc","o_ws","o_sttl","v_sttl","o_attl","v_attl","o_mttl","v_mttl",
        "o_fg","v_fg","o_fr","v_fr","o_fs","v_fs",
        "o_bl","v_bl","o_ns","o_mp","v_mp","o_pt","v_pt",
    ]

    def _load_cfg(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE,"r",encoding="utf-8") as f: self._cfg=json.load(f)
            except: self._cfg={}

    def _save_cfg(self):
        data = {k: getattr(self,k).get() for k in self._CFG_KEYS}
        try:
            with open(CONFIG_FILE,"w",encoding="utf-8") as f: json.dump(data,f,ensure_ascii=False,indent=2)
        except: pass

    def _apply_cfg(self):
        for k,v in self._cfg.items():
            try: getattr(self,k).set(v)
            except: pass

    # ── UI ────────────────────────────────────────────────────────────────────

    def _ui(self):
        # ── Sidebar ──────────────────────────────────────────────────────────
        sb = tk.Frame(self, bg=BG, width=188)
        sb.pack(side="left", fill="y"); sb.pack_propagate(False)

        # Logo
        logo = tk.Frame(sb, bg=BG); logo.pack(fill="x", pady=(22,14))
        dot = tk.Canvas(logo, width=10, height=10, bg=BG, highlightthickness=0)
        dot.create_oval(0,0,10,10, fill=ACCENT, outline="")
        dot.pack(side="left", padx=(16,8), pady=2)
        tk.Label(logo, text="GoodbyeDPI", bg=BG, fg=TEXT,
                 font=("Segoe UI",13,"bold")).pack(side="left")
        tk.Frame(sb, bg=BORDER, height=1).pack(fill="x", padx=14, pady=(0,6))

        nav = [("home","⬡","Главная"),("basic","☰","Основные"),
               ("frag","⋮","Фрагментация"),("dns","◈","DNS"),
               ("fake","◇","Fake Request"),("misc","⊕","Дополнительно"),
               ("log","▤","Лог вывода")]
        for key,icon,name in nav:
            item = NavItem(sb, name, icon, lambda k=key: self._show(k))
            item.pack(fill="x"); self._navitems[key] = item

        tk.Frame(sb, bg=BORDER, height=1).pack(fill="x", padx=14, pady=10)

        # Status in sidebar
        sf = tk.Frame(sb, bg=BG); sf.pack(fill="x", padx=16)
        self._sdot = tk.Canvas(sf, width=10, height=10, bg=BG, highlightthickness=0)
        self._sdot.create_oval(0,0,10,10, fill=TEXT3, tags="d")
        self._sdot.pack(side="left", padx=(0,6))
        self._slbl = tk.Label(sf, text="Остановлен", bg=BG, fg=TEXT3, font=("Segoe UI",9))
        self._slbl.pack(side="left")

        # ── Main ─────────────────────────────────────────────────────────────
        main = tk.Frame(self, bg=BG); main.pack(side="left", fill="both", expand=True)

        # Top bar
        tb = tk.Frame(main, bg=SURFACE, height=54)
        tb.pack(fill="x"); tb.pack_propagate(False)
        tk.Label(tb, text="Путь:", bg=SURFACE, fg=TEXT2, font=("Segoe UI",9)).pack(side="left",padx=(14,4))
        Inp(tb, textvariable=self.v_exe, width=30).pack(side="left", pady=10)
        
        # Кнопка загрузки
        download_btn = Btn(tb, "↓", self._download_gdpi, bg=SURFACE2, fg=TEXT2, px=8, py=4)
        download_btn.pack(side="left", padx=2)
        
        Btn(tb,"…",self._browse_exe, bg=SURFACE2, fg=TEXT2, px=10, py=4).pack(side="left",padx=5)

        self._run_btn = Btn(tb,"▶  Запустить",self._start, bg=GREEN, px=14, py=6)
        self._run_btn.pack(side="right", padx=(0,10), pady=10)
        self._stp_btn = Btn(tb,"■  Стоп",self._stop, bg=RED, px=14, py=6)
        self._stp_btn.pack(side="right", padx=4, pady=10)
        self._stp_btn.config(bg=SURFACE2, fg=TEXT3, cursor="arrow")
        self._stp_btn.unbind("<Button-1>")

        tk.Frame(main, bg=BORDER, height=1).pack(fill="x")

        # Page host
        self._host = tk.Frame(main, bg=BG)
        self._host.pack(fill="both", expand=True)

        self._pg_home()
        self._pg_basic()
        self._pg_frag()
        self._pg_dns()
        self._pg_fake()
        self._pg_misc()
        self._pg_log()

    def _download_gdpi(self):
        """Загружает GoodbyeDPI"""
        exe_path = check_and_download_gdpi(self)
        if exe_path:
            self.v_exe.set(exe_path)

    # ── Page factory ──────────────────────────────────────────────────────────

    def _scrollable(self, key):
        cv = tk.Canvas(self._host, bg=BG, highlightthickness=0)
        vb = tk.Scrollbar(self._host, orient="vertical", command=cv.yview,
                          bg=SURFACE, troughcolor=SURFACE, bd=0, width=8)
        cv.configure(yscrollcommand=vb.set)
        inner = tk.Frame(cv, bg=BG)
        win = cv.create_window((0,0), window=inner, anchor="nw")
        cv.bind("<Configure>",  lambda e: cv.itemconfig(win, width=e.width))
        inner.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.bind_all("<MouseWheel>", lambda e: cv.yview_scroll(int(-e.delta/120),"units"))
        self._pages[key] = (cv, vb, inner)
        return inner

    def _ptitle(self, p, title, sub=""):
        f = tk.Frame(p, bg=BG); f.pack(fill="x", padx=18, pady=(18,6))
        tk.Label(f, text=title, bg=BG, fg=TEXT, font=("Segoe UI",17,"bold")).pack(anchor="w")
        if sub: tk.Label(f, text=sub, bg=BG, fg=TEXT2, font=("Segoe UI",9)).pack(anchor="w",pady=(2,0))

    def _card(self, p, pad_bottom=14):
        c = tk.Frame(p, bg=SURFACE); c.pack(fill="x", padx=18, pady=(0,8))
        return c

    def _sec(self, card, text):
        f = tk.Frame(card, bg=SURFACE); f.pack(fill="x", padx=16, pady=(14,4))
        tk.Label(f, text=text.upper(), bg=SURFACE, fg=TEXT3,
                 font=("Segoe UI",8,"bold")).pack(anchor="w")
        tk.Frame(f, bg=BORDER, height=1).pack(fill="x", pady=(4,0))

    def _row(self, card, chk_var, text, sub="", entry_var=None, ew=8, unit=""):
        r = tk.Frame(card, bg=SURFACE); r.pack(fill="x", padx=16, pady=3)
        Checkbox(r, chk_var, text, sub=sub).pack(side="left", fill="x", expand=True)
        if entry_var is not None:
            Inp(r, textvariable=entry_var, width=ew).pack(side="right", padx=(8,0))
        if unit:
            tk.Label(r, text=unit, bg=SURFACE, fg=TEXT3, font=("Segoe UI",9)).pack(side="right", padx=(4,0))

    # ── Home page ─────────────────────────────────────────────────────────────

    def _pg_home(self):
        p = self._scrollable("home")
        self._ptitle(p,"Добро пожаловать","Выберите пресет или настройте параметры вручную")

        # Preset grid
        pc = self._card(p)
        self._sec(pc,"Быстрые пресеты")
        pg = tk.Frame(pc, bg=SURFACE); pg.pack(fill="x", padx=16, pady=(0,14))
        self._preset_btns = {}
        for i,(name,_) in enumerate(PRESETS.items()):
            short = name.split("—")[-1].strip() if "—" in name else name
            b = tk.Label(pg, text=short, bg=SURFACE2, fg=TEXT2,
                         font=("Segoe UI",9), padx=8, pady=7, cursor="hand2", relief="flat")
            b.grid(row=i//3, column=i%3, padx=3, pady=3, sticky="ew")
            pg.columnconfigure(i%3, weight=1)
            b.bind("<Button-1>", lambda e, n=name: self._pick(n))
            b.bind("<Enter>", lambda e, bt=b, n=name: bt.config(
                bg=ACCENT if self.v_preset.get()==n else BORDER))
            b.bind("<Leave>", lambda e, bt=b, n=name: bt.config(
                bg=ACCENT if self.v_preset.get()==n else SURFACE2))
            self._preset_btns[name] = b

        # Command preview
        cc = self._card(p)
        self._sec(cc,"Команда запуска")
        cw = tk.Frame(cc, bg="#0a0c14"); cw.pack(fill="x", padx=16, pady=(0,14))
        self._cmd_lbl = tk.Label(cw, text="", bg="#0a0c14", fg=ACCENT_H,
                                  font=("Consolas",9), anchor="w", justify="left",
                                  wraplength=600, padx=12, pady=10)
        self._cmd_lbl.pack(fill="x")

        # Action row
        ar = tk.Frame(cc, bg=SURFACE); ar.pack(fill="x", padx=16, pady=(0,14))
        Btn(ar,"Сохранить настройки",self._save_cfg, bg=SURFACE2, fg=TEXT2, px=12, py=5).pack(side="left",padx=(0,8))
        Btn(ar,"Сбросить всё",lambda: self._reset(), bg=SURFACE2, fg=TEXT2, px=12, py=5).pack(side="left")

        tk.Frame(p, bg=BG, height=12).pack()

    # ── Basic ─────────────────────────────────────────────────────────────────

    def _pg_basic(self):
        p = self._scrollable("basic")
        self._ptitle(p,"Основные параметры","HTTP-заголовки и базовые обходы")
        c = self._card(p)
        self._sec(c,"HTTP header manipulation")
        self._row(c,self.o_p,"Блокировать пассивный DPI",       sub="-p  |  Отбрасывать RST/302 от провайдера")
        self._row(c,self.o_q,"Блокировать QUIC / HTTP3",         sub="-q  |  Форсировать HTTP/2 + TLS")
        self._row(c,self.o_r,"Заменить Host → hoSt",             sub="-r  |  Сбивает поиск заголовка в DPI")
        self._row(c,self.o_s,"Убрать пробел после Host:",        sub="-s  |  Валидно по RFC, путает DPI")
        self._row(c,self.o_a,"Лишний пробел перед URI",          sub="-a  |  Включает -s автоматически")
        self._row(c,self.o_m,"Перемешать регистр Host",          sub="-m  |  test.com → tEsT.cOm")
        self._row(c,self.o_w,"HTTP-трюки на всех портах",        sub="-w  |  По умолчанию только порт 80")
        tk.Frame(c, bg=SURFACE, height=10).pack()

    # ── Fragmentation ─────────────────────────────────────────────────────────

    def _pg_frag(self):
        p = self._scrollable("frag")
        self._ptitle(p,"Фрагментация","Разбиение TCP-пакетов для обхода DPI")
        c = self._card(p)
        self._sec(c,"Размеры фрагментов")
        self._row(c,self.o_f,"HTTP фрагментация",         sub="-f  |  Размер первого HTTP фрагмента",   entry_var=self.v_f, unit="байт")
        self._row(c,self.o_e,"HTTPS фрагментация",        sub="-e  |  Размер первого TLS фрагмента",    entry_var=self.v_e, unit="байт")
        self._row(c,self.o_k,"HTTP keep-alive",            sub="-k  |  Включает --native-frag",          entry_var=self.v_k, unit="байт")
        self._row(c,self.o_n,"Не ждать ACK при -k",       sub="-n  |  Быстрее, но менее стабильно")
        tk.Frame(c, bg=SURFACE, height=8).pack()

        c2 = self._card(p)
        self._sec(c2,"Метод отправки")
        self._row(c2,self.o_nat,"Native fragmentation",   sub="--native-frag  |  Меньшие пакеты, без изменения Window Size")
        self._row(c2,self.o_rev,"Reverse fragmentation",  sub="--reverse-frag  |  Обратный порядок фрагментов")
        self._row(c2,self.o_snifr,"Fragment by SNI",      sub="--frag-by-sni  |  Разрез прямо перед полем SNI в TLS")
        tk.Frame(c2, bg=SURFACE, height=10).pack()

    # ── DNS ───────────────────────────────────────────────────────────────────

    def _pg_dns(self):
        p = self._scrollable("dns")
        self._ptitle(p,"DNS перенаправление","Защита от DNS-спуфинга и отравления")

        qc = self._card(p)
        self._sec(qc,"Популярные DNS")
        qr = tk.Frame(qc, bg=SURFACE); qr.pack(fill="x", padx=16, pady=(0,14))
        for name, addr, port in [("Яндекс\n77.88.8.8:1253","77.88.8.8","1253"),
                                  ("Google\n8.8.8.8:53","8.8.8.8","53"),
                                  ("Cloudflare\n1.1.1.1:53","1.1.1.1","53"),
                                  ("AdGuard\n94.140.14.14:5353","94.140.14.14","5353")]:
            label = name.split("\n")[0]
            addr_port = name.split("\n")[1]
            bf = tk.Frame(qr, bg=SURFACE2, cursor="hand2")
            bf.pack(side="left", padx=(0,8))
            tk.Label(bf, text=label, bg=SURFACE2, fg=TEXT, font=("Segoe UI",9,"bold"),
                     padx=12, pady=4, anchor="w").pack(anchor="w")
            tk.Label(bf, text=addr_port, bg=SURFACE2, fg=TEXT3, font=("Consolas",8),
                     padx=12, pady=4, anchor="w").pack(anchor="w")
            for w in (bf,):
                w.bind("<Button-1>", lambda e, a=addr, pt=port: (
                    self.v_daddr.set(a), self.v_dport.set(pt), self.o_dns.set(True)))
            for child in bf.winfo_children():
                child.bind("<Button-1>", lambda e, a=addr, pt=port: (
                    self.v_daddr.set(a), self.v_dport.set(pt), self.o_dns.set(True)))
            bf.bind("<Enter>", lambda e, b=bf: b.config(bg=BORDER))
            bf.bind("<Leave>", lambda e, b=bf: b.config(bg=SURFACE2))

        c = self._card(p)
        self._sec(c,"IPv4")
        self._row(c,self.o_dns,"Перенаправить DNS (IPv4)", sub="--dns-addr", entry_var=self.v_daddr, ew=18)
        fr = tk.Frame(c, bg=SURFACE); fr.pack(fill="x", padx=16, pady=3)
        tk.Label(fr, text="Порт:", bg=SURFACE, fg=TEXT2, font=("Segoe UI",10), width=20, anchor="w").pack(side="left")
        Inp(fr, textvariable=self.v_dport, width=8).pack(side="left")

        c2 = self._card(p)
        self._sec(c2,"IPv6")
        self._row(c2,self.o_dns6,"Перенаправить DNS (IPv6)", sub="--dnsv6-addr", entry_var=self.v_d6addr, ew=26)
        fr2 = tk.Frame(c2, bg=SURFACE); fr2.pack(fill="x", padx=16, pady=3)
        tk.Label(fr2, text="Порт:", bg=SURFACE, fg=TEXT2, font=("Segoe UI",10), width=20, anchor="w").pack(side="left")
        Inp(fr2, textvariable=self.v_d6port, width=8).pack(side="left")
        self._row(c2,self.o_dv,"Verbose DNS лог", sub="--dns-verb")
        tk.Frame(c2, bg=SURFACE, height=10).pack()

    # ── Fake request ──────────────────────────────────────────────────────────

    def _pg_fake(self):
        p = self._scrollable("fake")
        self._ptitle(p,"Fake Request Mode","Поддельные пакеты для запутывания DPI")

        c = self._card(p)
        self._sec(c,"Метод инвалидации")
        self._row(c,self.o_wc,"Wrong checksum", sub="--wrong-chksum  |  Неверная TCP-контрольная сумма. Безопасный вариант")
        self._row(c,self.o_ws,"Wrong sequence", sub="--wrong-seq  |  TCP SEQ/ACK из прошлого")
        tk.Frame(c, bg=SURFACE, height=8).pack()

        c2 = self._card(p)
        self._sec(c2,"TTL манипуляции")
        self._row(c2,self.o_sttl,"Set TTL (фиксированный)", sub="--set-ttl  |  Фейк доходит до DPI, не до сервера", entry_var=self.v_sttl)
        self._row(c2,self.o_attl,"Auto TTL (автоопределение)", sub="--auto-ttl  |  Формат: a1-a2-max, например 1-4-10", entry_var=self.v_attl, ew=10)
        self._row(c2,self.o_mttl,"Min TTL distance", sub="--min-ttl  |  Мин. дистанция до отправки фейка", entry_var=self.v_mttl)
        tk.Frame(c2, bg=SURFACE, height=8).pack()

        c3 = self._card(p)
        self._sec(c3,"Содержимое фейков")
        self._row(c3,self.o_fg,"Случайные фейки (--fake-gen)",      entry_var=self.v_fg, sub="Количество генерируемых фейков (макс. 30)")
        self._row(c3,self.o_fr,"Повторов каждого (--fake-resend)",   entry_var=self.v_fr, sub="По умолчанию 1")
        self._row(c3,self.o_fs,"SNI в фейк-пакете (--fake-with-sni)", sub="Имитирует TLS ClientHello Firefox", entry_var=self.v_fs, ew=22)
        tk.Frame(c3, bg=SURFACE, height=10).pack()

    # ── Misc ──────────────────────────────────────────────────────────────────

    def _pg_misc(self):
        p = self._scrollable("misc")
        self._ptitle(p,"Дополнительные настройки")

        c = self._card(p)
        self._sec(c,"Фильтрация хостов")
        blr = tk.Frame(c, bg=SURFACE); blr.pack(fill="x", padx=16, pady=3)
        Checkbox(blr, self.o_bl, "Blacklist (только для хостов из файла)", sub="--blacklist  |  .txt с именами хостов").pack(side="left",fill="x",expand=True)
        Inp(blr, textvariable=self.v_bl, width=20).pack(side="right", padx=(8,0))
        Btn(blr,"…",self._browse_bl, bg=SURFACE2, fg=TEXT2, px=8, py=4).pack(side="right", padx=4)
        self._row(c,self.o_ns,"Allow no SNI", sub="--allow-no-sni  |  Обход без SNI (с --blacklist)")
        tk.Frame(c, bg=SURFACE, height=8).pack()

        c2 = self._card(p)
        self._sec(c2,"Производительность")
        self._row(c2,self.o_mp,"Макс. payload для обработки", sub="--max-payload  |  Пропускать большие пакеты (меньше нагрузка)", entry_var=self.v_mp, unit="байт")
        self._row(c2,self.o_pt,"Доп. TCP-порт для фрагментации", sub="--port  |  Опцию можно указывать несколько раз", entry_var=self.v_pt)
        tk.Frame(c2, bg=SURFACE, height=10).pack()

    # ── Log ───────────────────────────────────────────────────────────────────

    def _pg_log(self):
        self._log_widget = scrolledtext.ScrolledText(
            self._host, font=("Consolas",9),
            bg="#080a10", fg="#8892aa",
            insertbackground=TEXT, selectbackground=ACCENT,
            relief="flat", bd=0, state="disabled", wrap="word")
        self._pages["log"] = ("direct", None, self._log_widget)

    # ── Navigation ────────────────────────────────────────────────────────────

    def _show(self, key):
        if self._cur_page:
            ni = self._navitems.get(self._cur_page)
            if ni: ni.activate(False)
            pg = self._pages.get(self._cur_page)
            if pg:
                if pg[0] == "direct": pg[2].pack_forget()
                else: pg[0].pack_forget(); pg[1].pack_forget()
        self._cur_page = key
        ni = self._navitems.get(key)
        if ni: ni.activate(True)
        pg = self._pages.get(key)
        if pg:
            if pg[0] == "direct": pg[2].pack(fill="both", expand=True)
            else:
                pg[1].pack(side="right", fill="y")
                pg[0].pack(side="left", fill="both", expand=True)

    # ── Logic ─────────────────────────────────────────────────────────────────

    def _args(self):
        a = []
        for f,v in [("-p",self.o_p),("-q",self.o_q),("-r",self.o_r),("-s",self.o_s),
                    ("-a",self.o_a),("-m",self.o_m),("-w",self.o_w)]:
            if v.get(): a.append(f)
        for f,c,v in [("-f",self.o_f,self.v_f),("-e",self.o_e,self.v_e),("-k",self.o_k,self.v_k)]:
            if c.get() and v.get(): a += [f, v.get()]
        if self.o_n.get():   a.append("-n")
        if self.o_nat.get(): a.append("--native-frag")
        if self.o_rev.get(): a.append("--reverse-frag")
        if self.o_snifr.get(): a.append("--frag-by-sni")
        if self.o_dns.get() and self.v_daddr.get():
            a += ["--dns-addr", self.v_daddr.get()]
            if self.v_dport.get(): a += ["--dns-port", self.v_dport.get()]
        if self.o_dns6.get() and self.v_d6addr.get():
            a += ["--dnsv6-addr", self.v_d6addr.get()]
            if self.v_d6port.get(): a += ["--dnsv6-port", self.v_d6port.get()]
        if self.o_dv.get(): a.append("--dns-verb")
        if self.o_wc.get(): a.append("--wrong-chksum")
        if self.o_ws.get(): a.append("--wrong-seq")
        if self.o_sttl.get() and self.v_sttl.get(): a += ["--set-ttl",  self.v_sttl.get()]
        if self.o_attl.get():
            a.append("--auto-ttl")
            if self.v_attl.get(): a.append(self.v_attl.get())
        if self.o_mttl.get() and self.v_mttl.get(): a += ["--min-ttl",     self.v_mttl.get()]
        if self.o_fg.get()   and self.v_fg.get():   a += ["--fake-gen",    self.v_fg.get()]
        if self.o_fr.get()   and self.v_fr.get():   a += ["--fake-resend", self.v_fr.get()]
        if self.o_fs.get()   and self.v_fs.get():   a += ["--fake-with-sni",self.v_fs.get()]
        if self.o_bl.get()   and self.v_bl.get():   a += ["--blacklist",   self.v_bl.get()]
        if self.o_ns.get(): a.append("--allow-no-sni")
        if self.o_mp.get()   and self.v_mp.get():   a += ["--max-payload", self.v_mp.get()]
        if self.o_pt.get()   and self.v_pt.get():   a += ["--port",        self.v_pt.get()]
        return a

    def _preview(self, *_):
        exe  = self.v_exe.get()
        args = self._args()
        cmd  = (exe + " " + " ".join(args)) if args else f"{exe}  →  режим -9 по умолчанию"
        try: self._cmd_lbl.config(text=cmd)
        except: pass

    def _pick(self, name):
        self.v_preset.set(name)
        for n,b in self._preset_btns.items():
            b.config(bg=ACCENT if n==name else SURFACE2,
                     fg="white" if n==name else TEXT2)
        args = PRESETS.get(name, [])
        self._reset(silent=True)
        i = 0
        while i < len(args):
            a = args[i]
            m = {"-p":self.o_p,"-q":self.o_q,"-r":self.o_r,"-s":self.o_s,
                 "-m":self.o_m,"-w":self.o_w,"--native-frag":self.o_nat,
                 "--wrong-chksum":self.o_wc,"--wrong-seq":self.o_ws}
            if a in m: m[a].set(True)
            elif a == "--dns-addr" and i+1<len(args): self.o_dns.set(True); self.v_daddr.set(args[i+1]); i+=1
            elif a == "--dns-port" and i+1<len(args): self.v_dport.set(args[i+1]); i+=1
            elif len(a)==2 and a[0]=="-" and a[1].isdigit(): self._mode(int(a[1:]))
            i += 1
        self._preview()

    def _mode(self, n):
        if n >= 1: self.o_p.set(True)
        if n >= 2: self.o_r.set(True); self.o_s.set(True); self.o_m.set(True)
        if n >= 3: self.o_f.set(True); self.v_f.set("2"); self.o_nat.set(True)
        if n >= 4: self.o_e.set(True); self.v_e.set("40"); self.o_nat.set(True)
        if n >= 9:
            self.o_p.set(True); self.o_r.set(True); self.o_s.set(True)
            self.o_m.set(True); self.o_w.set(True)
            self.o_f.set(True); self.v_f.set("2")
            self.o_e.set(True); self.v_e.set("40")
            self.o_nat.set(True)

    def _reset(self, silent=False):
        for v in [self.o_p,self.o_q,self.o_r,self.o_s,self.o_a,self.o_m,self.o_w,
                  self.o_f,self.o_e,self.o_k,self.o_n,self.o_nat,self.o_rev,self.o_snifr,
                  self.o_dns,self.o_dns6,self.o_dv,
                  self.o_wc,self.o_ws,self.o_sttl,self.o_attl,self.o_mttl,
                  self.o_fg,self.o_fr,self.o_fs,
                  self.o_bl,self.o_ns,self.o_mp,self.o_pt]:
            v.set(False)
        if not silent: self._preview()

    def _write_log(self, text):
        self._log_widget.configure(state="normal")
        self._log_widget.insert("end", text)
        self._log_widget.see("end")
        self._log_widget.configure(state="disabled")

    def _set_run(self, on):
        self.running = on
        self._sdot.itemconfig("d", fill=GREEN if on else TEXT3)
        self._slbl.config(text="Работает" if on else "Остановлен",
                          fg=GREEN if on else TEXT3)
        if on:
            self._run_btn.config(bg=SURFACE2, fg=TEXT3, cursor="arrow")
            self._run_btn.unbind("<Button-1>")
            self._stp_btn.config(bg=RED, fg="white", cursor="hand2")
            self._stp_btn.bind("<Button-1>", lambda _: self._stop())
            self._stp_btn.bind("<Enter>", lambda _: self._stp_btn.config(bg=RED_H))
            self._stp_btn.bind("<Leave>", lambda _: self._stp_btn.config(bg=RED))
        else:
            self._run_btn.config(bg=GREEN, fg="white", cursor="hand2")
            self._run_btn.bind("<Button-1>", lambda _: self._start())
            self._run_btn.bind("<Enter>", lambda _: self._run_btn.config(bg=GREEN_H))
            self._run_btn.bind("<Leave>", lambda _: self._run_btn.config(bg=GREEN))
            self._stp_btn.config(bg=SURFACE2, fg=TEXT3, cursor="arrow")
            self._stp_btn.unbind("<Button-1>")

    def _start(self):
        exe = self.v_exe.get()
        if not os.path.exists(exe):
            # Предлагаем скачать если файл не найден
            result = messagebox.askyesno(
                "Файл не найден",
                f"Не могу найти:\n{exe}\n\nХотите скачать GoodbyeDPI с GitHub?"
            )
            if result:
                new_path = check_and_download_gdpi(self)
                if new_path:
                    self.v_exe.set(new_path)
                    exe = new_path
                else:
                    return
            else:
                return
        
        args = self._args()
        cmd  = [exe] + args
        self._write_log(f"\n[+] Запуск: {' '.join(cmd)}\n")
        self._show("log")
        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception as e:
            self._write_log(f"[!] Ошибка запуска: {e}\n"); return
        self._set_run(True)
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.proc.stdout: self.after(0, self._write_log, line)
        self.proc.wait()
        code = self.proc.returncode
        self.after(0, self._write_log, f"\n[*] Завершён (код {code})\n")
        self.after(0, self._set_run, False)

    def _stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self._write_log("\n[*] Сигнал остановки отправлен\n")

    def _browse_exe(self):
        p = filedialog.askopenfilename(title="goodbyedpi.exe",
            filetypes=[("Executable","*.exe"),("All files","*.*")])
        if p: self.v_exe.set(p)

    def _browse_bl(self):
        p = filedialog.askopenfilename(title="Blacklist",
            filetypes=[("Text files","*.txt"),("All files","*.*")])
        if p: self.v_bl.set(p); self.o_bl.set(True)

    def _close(self):
        self._stop(); self._save_cfg(); self.destroy()


if __name__ == "__main__":
    if sys.platform == "win32" and not is_admin():
        ans = messagebox.askyesno("Права администратора",
            "GoodbyeDPI требует прав администратора.\nЗапустить с повышенными правами?")
        if ans: restart_as_admin()
    App().mainloop()