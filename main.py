import tkinter as tk
from tkinter import filedialog, messagebox, Scrollbar, Toplevel, Entry, Label
from tkinter import ttk
from PIL import Image
from PIL import ImageTk
import base64
import json
import urllib.parse
import os
import random
import string
from datetime import datetime
import tempfile
import zipfile
import shutil
import locale
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
import webbrowser
import re
import platform
from translations import TRANSLATIONS
from save_analyzer import SaveAnalyzer
from utils import set_window_icon
from backup_restore import BackupRestore
from toast import Toast
from styles import get_cjk_font, get_parent_bg, init_styles, Colors, Debouncer

# From the sky bereft of stars

# Windows注册表支持，查找Steam路径使用
if platform.system() == "Windows":
    try:
        import winreg
    except ImportError:
        winreg = None
else:
    winreg = None

class SavTool:
    def __init__(self, root):
        self.root = root
        self.translations = TRANSLATIONS
        self.current_language = self.detect_system_language()
        self.root.title(self.t("window_title"))
        self.root.geometry("800x600")
        
        # 设置窗口图标
        set_window_icon(self.root)
        
        # 初始化统一样式（解决文字底色问题）
        init_styles(self.root)

        # 创建菜单栏
        self.menubar = tk.Menu(root)
        root.config(menu=self.menubar)
        
        # Directory 菜单
        self.directory_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label=self.t("directory_menu"), menu=self.directory_menu)
        self.directory_menu.add_command(label=self.t("browse_dir"), command=self.select_dir)
        self.directory_menu.add_command(label=self.t("auto_detect_steam"), command=self.auto_detect_steam)
        
        # Language 菜单
        self.language_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="Language", menu=self.language_menu)
        self.language_var = tk.StringVar(value=self.current_language)
        self.language_menu.add_radiobutton(label="日本語", variable=self.language_var, 
                                          value="ja_JP", command=lambda: self.change_language("ja_JP"))
        self.language_menu.add_radiobutton(label="中文", variable=self.language_var, 
                                           value="zh_CN", command=lambda: self.change_language("zh_CN"))
        self.language_menu.add_radiobutton(label="English", variable=self.language_var, 
                                          value="en_US", command=lambda: self.change_language("en_US"))
        
        # Help 菜单
        help_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="Help", command=self.show_help)

        # 创建 Notebook (Tab 容器)
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=0, pady=0)

        # Tab 1: 存档分析界面（默认显示）
        self.analyzer_frame = tk.Frame(self.notebook)
        self.notebook.add(self.analyzer_frame, text=self.t("save_analyzer_tab"))
        
        # 在存档分析界面显示提示（如果还没有选择目录）
        self.analyzer_hint_label = tk.Label(self.analyzer_frame, text=self.t("select_dir_hint"), 
                                            fg="#D554BC", font=get_cjk_font(12))
        self.analyzer_hint_label.pack(pady=50)
        
        # Tab 2: 截图管理界面
        self.screenshot_frame = tk.Frame(self.notebook)
        self.notebook.add(self.screenshot_frame, text=self.t("screenshot_management_tab"))

        # Tab 3: 备份/还原界面
        self.backup_restore_frame = tk.Frame(self.notebook)
        self.notebook.add(self.backup_restore_frame, text=self.t("backup_restore_tab"))
        
        # 备份/还原界面的提示标签
        self.backup_restore_hint_label = tk.Label(self.backup_restore_frame, text=self.t("select_dir_hint"), 
                                                  fg="#D554BC", font=get_cjk_font(12))
        self.backup_restore_hint_label.pack(pady=50)

        # 初始化存档分析界面（延迟到选择目录后）
        self.save_analyzer = None
        
        # 初始化备份/还原管理器（延迟到选择目录后）
        self.backup_restore = None
        
        # 绑定 tab 切换事件，切换到存档分析页面时自动刷新
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)
        
        # 绑定窗口关闭事件，清理监控
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # 没有选择目录时的提示标签（在截图管理界面）
        self.hint_label = tk.Label(self.screenshot_frame, text=self.t("select_dir_hint"), 
                                   fg="#D554BC", font=get_cjk_font(10))
        self.hint_label.pack(pady=10)
        
        # 成功检测到Steam路径标签（在截图管理界面）
        self.success_label = tk.Label(self.screenshot_frame, text="", 
                                      fg="#6DB8AC", font=get_cjk_font(10))
        self.success_label_timer = None  # 用于存储定时器ID

        # 截图列表（在截图管理界面）
        list_header_frame = tk.Frame(self.screenshot_frame)
        list_header_frame.pack(pady=5, fill="x")
        list_header_frame.columnconfigure(0, weight=1)  
        list_header_frame.columnconfigure(2, weight=1)  
        
        left_spacer = tk.Frame(list_header_frame)
        left_spacer.grid(row=0, column=0, sticky="ew")
        
        # 左侧：标题（全选复选框在Treeview的header中）
        left_header = tk.Frame(list_header_frame)
        left_header.grid(row=0, column=1)
        self.list_label = ttk.Label(left_header, text=self.t("screenshot_list"))
        self.list_label.pack(side="left", padx=5)
        
        # 右侧区域
        right_area = tk.Frame(list_header_frame)
        right_area.grid(row=0, column=2, sticky="ew")
        right_area.columnconfigure(0, weight=1) 
        
        right_spacer = tk.Frame(right_area)
        right_spacer.grid(row=0, column=0, sticky="ew")
        
        # 右侧按钮区域
        button_container = tk.Frame(right_area)
        button_container.grid(row=0, column=1, sticky="e")
        ttk.Button(button_container, text=self.t("refresh"), command=self.load_screenshots, width=3).pack(side="left", padx=2)
        self.sort_asc_button = ttk.Button(button_container, text=self.t("sort_asc"), command=self.sort_ascending)
        self.sort_asc_button.pack(side="left", padx=2)
        self.sort_desc_button = ttk.Button(button_container, text=self.t("sort_desc"), command=self.sort_descending)
        self.sort_desc_button.pack(side="left", padx=2)
        
        # 创建包含预览和列表的容器（在截图管理界面）
        list_frame = tk.Frame(self.screenshot_frame)
        list_frame.pack(pady=5)
        
        # 预览区域（左侧）
        preview_frame = tk.Frame(list_frame, bg=Colors.WHITE)
        preview_frame.pack(side="left", padx=5)
        # 使用 tk.Label 并设置与父容器相同的背景色，避免底色问题
        self.preview_label_text = tk.Label(preview_frame, text=self.t("preview"), 
                                          font=get_cjk_font(10), bg=Colors.WHITE)
        self.preview_label_text.pack()

        # 限制预览Label的大小
        preview_container = tk.Frame(preview_frame, width=160, height=120, 
                                    bg=Colors.PREVIEW_BG, relief="sunken")
        preview_container.pack()
        preview_container.pack_propagate(False) 
        # 预览 Label 使用与容器相同的背景色
        self.preview_label = Label(preview_container, bg=Colors.PREVIEW_BG)
        self.preview_label.pack(fill="both", expand=True)
        self.preview_photo = None
        
        # 导出图片按钮（初始隐藏）
        self.export_button = ttk.Button(preview_frame, text=self.t("export_image"), command=self.export_image)
        self.export_button.pack(pady=5)
        self.export_button.pack_forget()
        
        # 批量导出图片按钮（初始隐藏）
        self.batch_export_button = ttk.Button(preview_frame, text=self.t("batch_export"), command=self.batch_export_images)
        self.batch_export_button.pack(pady=5)
        self.batch_export_button.pack_forget() 
        
        # 列表区域（右侧）
        list_right_frame = tk.Frame(list_frame)
        list_right_frame.pack(side="right")
        
        # 使用Treeview支持复选框
        tree_frame = tk.Frame(list_right_frame)
        tree_frame.pack(side="left", fill="both", expand=True)
        
        scrollbar = Scrollbar(tree_frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        
        # 使用两列：select列用于复选框，info列用于信息
        self.tree = ttk.Treeview(tree_frame, columns=("select", "info"), show="headings", height=15)
        # 隐藏#0列（tree列）
        self.tree.heading("#0", text="", anchor="w")
        self.tree.column("#0", width=0, stretch=False, minwidth=0)
        
        # 复选框列（标题是全选复选框）
        self.tree.heading("select", text="☐", anchor="center", command=self.toggle_select_all)
        self.tree.column("select", width=40, stretch=False, anchor="center")
        
        # 信息列
        self.tree.heading("info", text=self.t("list_header"), anchor="w")
        self.tree.column("info", width=600, stretch=True)
        
        # 配置tag样式用于显示带颜色的箭头指示器，使用tag_configure来设置不同tag的颜色
        self.tree.tag_configure("DragIndicatorUp", foreground="#85A9A5")
        self.tree.tag_configure("DragIndicatorDown", foreground="#D06CAA")
        self.tree.tag_configure("NewIndicator", foreground="#FED491")
        self.tree.tag_configure("ReplaceIndicator", foreground="#BDC9B2")
        # 配置页面标题行的tag样式
        self.tree.tag_configure("PageHeaderLeft", foreground="#D26FAB", font=get_cjk_font(10, "bold"))
        self.tree.tag_configure("PageHeaderRight", foreground="#85A9A5", font=get_cjk_font(10, "bold"))
        # 配置拖动时的视觉反馈tag
        self.tree.tag_configure("Dragging", background="#E3F2FD", foreground="#1976D2")
        
        scrollbar.config(command=self.tree.yview)
        self.tree.config(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        
        # 创建拖动指示线（使用Frame，通过place定位）
        self.drag_indicator_line = tk.Frame(tree_frame, bg="black", height=3)
        self.drag_indicator_line.place_forget()  # 初始隐藏
        
        # 存储复选框状态 {item_id: BooleanVar}
        self.checkbox_vars = {}
        
        # 绑定选择事件（用于预览）
        self.tree.bind('<<TreeviewSelect>>', self.on_tree_select)
        
        # 拖拽相关变量
        self.drag_start_item = None
        self.drag_start_y = None
        self.is_dragging = False
        self.drag_target_item = None  # 当前拖动目标位置
        self.current_indicator_target = None  # 当前显示指示线的目标项（用于避免重复更新）
        self.current_indicator_position = None  # 当前指示线的位置（用于避免重复更新）
        
        # 箭头指示器相关变量
        self.drag_indicators = []  # 存储当前显示的指示器信息 [(item_id, original_text, after_id), ...]
        
        # 新截图和替换截图的标记相关变量
        self.status_indicators = []  # 存储当前显示的状态指示器信息 [(item_id, original_text, after_id, indicator_type), ...]
        
        # 绑定事件：统一处理点击事件，先检查复选框，再处理拖拽
        self.tree.bind('<Button-1>', self.on_button1_click)
        self.tree.bind('<B1-Motion>', self.on_drag_motion)
        self.tree.bind('<ButtonRelease-1>', self.on_drag_end)

        # 操作按钮（在截图管理界面）
        button_frame = ttk.Frame(self.screenshot_frame)
        button_frame.pack(pady=5)
        self.add_button = ttk.Button(button_frame, text=self.t("add_new"), command=self.add_new)
        self.add_button.pack(side='left', padx=5)
        self.replace_button = ttk.Button(button_frame, text=self.t("replace_selected"), command=self.replace_selected)
        self.replace_button.pack(side='left', padx=5)
        self.delete_button = ttk.Button(button_frame, text=self.t("delete_selected"), command=self.delete_selected)
        self.delete_button.pack(side='left', padx=5)
        self.gallery_preview_button = ttk.Button(button_frame, text=self.t("gallery_preview"), command=self.show_gallery_preview)
        self.gallery_preview_button.pack(side='left', padx=5)

        self.storage_dir = None
        self.ids_data = []
        self.all_ids_data = []
        self.sav_pairs = {}  # {id: (main_sav, thumb_sav)}
        
        # 添加图片缓存字典 {id_str: PhotoImage} | 快速获取画廊用
        self.image_cache = {}
        self.cache_lock = threading.Lock()  # 用于线程安全的缓存访问
        
        # 文件列表缓存，避免重复扫描
        self._file_list_cache = None
        self._file_list_cache_time = 0
        self._file_list_cache_ttl = 5  # 缓存5秒
        
        # 存档文件监控相关
        self.save_file_path = None
        self.temp_file_path = None  # 临时文件路径 .temp_sf.sav
        self.monitor_thread = None  # 监控线程
        self.monitor_running = False  # 监控运行标志
        self.active_toasts = []  # 活跃的toast列表
        
        # 默认显示存档分析 tab（索引 0）
        self.notebook.select(0)
    
    def detect_system_language(self):
        """检测系统语言并返回支持的语言代码"""
        # 优先使用 locale.getdefaultlocale 检测（虽然已弃用，但就经验来说更可靠）
        try:
            default_locale = locale.getdefaultlocale()
            if default_locale[0]:
                language_code = default_locale[0].split('_')[0]
                if language_code == "zh":
                    return "zh_CN"
                elif language_code == "ja":
                    return "ja_JP"
                elif language_code == "en":
                    return "en_US"
        except Exception:
            pass
        
        # 检查自定义环境变量
        for env_key in ['APP_LANG', 'SCREENSHOT_TOOL_LANG', 'LANGUAGE']:
            env_lang = os.environ.get(env_key)
            if env_lang:
                env_lang = env_lang.strip().replace('-', '_').split('.')[0].lower()
                if env_lang.startswith('zh'):
                    return "zh_CN"
                elif env_lang.startswith('ja'):
                    return "ja_JP"
                elif env_lang.startswith('en'):
                    return "en_US"

        # 标准locale.getlocale
        try:
            system_locale, _ = locale.getlocale()
            if not system_locale:
                # 检查系统环境变量 LANG, LC_ALL, LC_MESSAGES，LANGUAGE
                for env_key in ['LANG', 'LC_ALL', 'LC_MESSAGES', 'LANGUAGE']:
                    system_locale = os.environ.get(env_key)
                    if system_locale:
                        break
            if not system_locale:
                # 尝试设置默认locale后重新获取
                try:
                    locale.setlocale(locale.LC_ALL, '')
                    system_locale, _ = locale.getlocale()
                except Exception:
                    pass
            # Windows平台使用系统API获取语言
            if not system_locale:
                import sys
                if sys.platform == "win32":
                    import ctypes
                    try:
                        windll = ctypes.windll
                        GetUserDefaultUILanguage = windll.kernel32.GetUserDefaultUILanguage
                        lang_id = GetUserDefaultUILanguage()
                        if lang_id in (0x804, 0x404, 0xc04, 0x1004, 0x1404, 0x7c04):
                            return "zh_CN"
                        elif lang_id in (0x411, 0x814):
                            return "ja_JP"
                        elif lang_id in (0x409, 0x809):
                            return "en_US"
                    except Exception:
                        pass
            # 转换语言代码
            if system_locale:
                locale_lower = system_locale.replace('-', '_').split('.')[0].lower()
                if locale_lower.startswith('zh'):
                    return "zh_CN"
                if locale_lower.startswith('ja'):
                    return "ja_JP"
                if locale_lower.startswith('en'):
                    return "en_US"
        except Exception:
            pass
        # 默认返回英语
        return "en_US"
    
    def t(self, key, **kwargs):
        """翻译函数，支持格式化字符串"""
        text = self.translations[self.current_language].get(key, key)
        if kwargs:
            return text.format(**kwargs)
        return text
    
    def change_language(self, lang):
        """切换语言"""
        self.current_language = lang
        self.language_var.set(lang)
        self.update_ui_texts()
        # 更新存档分析器的语言（如果已初始化）
        if self.save_analyzer is not None:
            self.save_analyzer.current_language = lang
            self.save_analyzer.refresh()
    
    def ask_yesno(self, title, message, icon='question'):
        """自定义确认对话框，使用翻译的按钮文本"""
        popup = Toplevel(self.root)
        popup.title(title)
        popup.geometry("400x150")
        popup.transient(self.root)
        popup.grab_set()
        
        # 设置窗口图标
        set_window_icon(popup)
        
        # 设置图标
        if icon == 'warning':
            popup.iconname('warning')
        
        # 显示消息
        ttk.Label(popup, text=message, wraplength=350, justify="left").pack(pady=20, padx=20)
        
        confirmed = False
        
        def yes():
            nonlocal confirmed
            confirmed = True
            popup.destroy()
        
        def no():
            popup.destroy()
        
        # 按钮框架
        button_frame = tk.Frame(popup)
        button_frame.pack(pady=10)
        
        ttk.Button(button_frame, text=self.t("yes_button"), command=yes).pack(side="left", padx=10)
        ttk.Button(button_frame, text=self.t("no_button"), command=no).pack(side="right", padx=10)
        
        # 绑定回车键和ESC键
        popup.bind('<Return>', lambda e: yes())
        popup.bind('<Escape>', lambda e: no())
        
        # 等待窗口关闭
        self.root.wait_window(popup)
        return confirmed
    
    def init_save_analyzer(self):
        """初始化存档分析界面"""
        if not self.storage_dir:
            return
        
        # 清除 analyzer_frame 中的所有子组件（包括提示标签）
        for widget in self.analyzer_frame.winfo_children():
            widget.destroy()
        
        # 创建新的存档分析界面
        self.save_analyzer = SaveAnalyzer(self.analyzer_frame, self.storage_dir, 
                                          self.translations, self.current_language)
    
    def init_backup_restore(self):
        """初始化备份/还原界面"""
        if not self.storage_dir:
            return
        
        # 清除 backup_restore_frame 中的所有子组件（包括提示标签）
        for widget in self.backup_restore_frame.winfo_children():
            widget.destroy()
        
        # 创建BackupRestore实例
        self.backup_restore = BackupRestore(self.storage_dir)
        
        # 创建UI布局（上下布局）
        # 上方：备份按钮区域
        backup_frame = tk.Frame(self.backup_restore_frame, bg=Colors.WHITE)
        backup_frame.pack(pady=20, fill="x")
        
        self.backup_button = ttk.Button(backup_frame, text=self.t("backup_button"), 
                                   command=self.create_backup)
        self.backup_button.pack(pady=10)
        
        # 进度条（初始隐藏）
        self.backup_progress = ttk.Progressbar(backup_frame, mode='determinate', length=300)
        self.backup_progress.pack(pady=5)
        self.backup_progress.pack_forget()
        
        # 进度标签（初始隐藏）
        self.backup_progress_label = tk.Label(backup_frame, text="", bg=Colors.WHITE, fg="#666")
        self.backup_progress_label.pack(pady=2)
        self.backup_progress_label.pack_forget()
        
        # 下方：还原列表区域
        restore_frame = tk.Frame(self.backup_restore_frame, bg=Colors.WHITE)
        restore_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 还原列表标题和刷新按钮
        restore_header = tk.Frame(restore_frame, bg=Colors.WHITE)
        restore_header.pack(fill="x", pady=5)
        
        self.backup_list_title = ttk.Label(restore_header, text=self.t("backup_list_title"), 
                                 font=get_cjk_font(12, "bold"))
        self.backup_list_title.pack(side="left", padx=5)
        
        self.backup_refresh_button = ttk.Button(restore_header, text=self.t("refresh"), 
                                    command=self.refresh_backup_list)
        self.backup_refresh_button.pack(side="right", padx=5)
        
        # 创建Treeview显示备份列表
        list_container = tk.Frame(restore_frame, bg=Colors.WHITE)
        list_container.pack(fill="both", expand=True)
        
        restore_scrollbar = Scrollbar(list_container, orient="vertical")
        restore_scrollbar.pack(side="right", fill="y")
        
        self.backup_tree = ttk.Treeview(list_container, 
                                        columns=("timestamp", "filename", "size", "status"), 
                                        show="headings", height=15,
                                        yscrollcommand=restore_scrollbar.set)
        
        self.backup_tree.heading("timestamp", text=self.t("backup_timestamp"))
        self.backup_tree.column("timestamp", width=180)
        
        self.backup_tree.heading("filename", text=self.t("backup_filename"))
        self.backup_tree.column("filename", width=250)
        
        self.backup_tree.heading("size", text=self.t("backup_size"))
        self.backup_tree.column("size", width=100)
        
        self.backup_tree.heading("status", text=self.t("backup_status"))
        self.backup_tree.column("status", width=150)
        
        restore_scrollbar.config(command=self.backup_tree.yview)
        self.backup_tree.pack(side="left", fill="both", expand=True)
        
        # 绑定选择事件
        self.backup_tree.bind('<<TreeviewSelect>>', self.on_backup_select)
        
        # 按钮区域
        button_area = tk.Frame(restore_frame, bg=Colors.WHITE)
        button_area.pack(pady=10)
        
        # 还原按钮（初始隐藏）
        self.restore_button = ttk.Button(button_area, text=self.t("restore_button"), 
                                         command=self.restore_backup)
        self.restore_button.pack(side="left", padx=5)
        self.restore_button.pack_forget()
        
        # 删除按钮（初始隐藏）
        self.delete_backup_button = ttk.Button(button_area, text=self.t("delete_backup_button"), 
                                                command=self.delete_backup)
        self.delete_backup_button.pack(side="left", padx=5)
        self.delete_backup_button.pack_forget()
        
        # 存储选中的备份路径
        self.selected_backup_path = None
        
        # 刷新备份列表
        self.refresh_backup_list()
    
    def create_backup(self):
        """创建备份"""
        if not self.storage_dir or not self.backup_restore:
            messagebox.showerror(self.t("error"), self.t("select_dir_hint"))
            return
        
        # 估算压缩后大小
        estimated_size = self.backup_restore.estimate_compressed_size(self.storage_dir)
        if estimated_size is None:
            messagebox.showerror(self.t("error"), self.t("backup_estimate_failed"))
            return
        
        # 格式化大小
        size_str = self.backup_restore.format_size(estimated_size)
        
        # 确认对话框
        result = self.ask_yesno(
            self.t("backup_confirm_title"),
            self.t("backup_confirm_text", size=size_str),
            icon='question'
        )
        
        if not result:
            return
        
        # 显示进度条
        self.backup_progress.pack(pady=5)
        self.backup_progress_label.pack(pady=2)
        self.backup_progress['value'] = 0
        self.backup_progress_label.config(text="0%")
        self.root.update()
        
        # 定义进度回调函数
        def progress_callback(current, total):
            progress = int((current / total) * 100)
            self.root.after(0, lambda: self._update_backup_progress(progress, current, total))
        
        # 在后台线程中执行备份
        def backup_thread():
            try:
                result = self.backup_restore.create_backup(self.storage_dir, progress_callback)
                self.root.after(0, lambda: self._backup_completed(result))
            except Exception as e:
                self.root.after(0, lambda: self._backup_completed(None))
        
        threading.Thread(target=backup_thread, daemon=True).start()
    
    def _update_backup_progress(self, progress, current, total):
        """更新备份进度条"""
        self.backup_progress['value'] = progress
        self.backup_progress_label.config(text=f"{progress}% ({current}/{total})")
        self.root.update()
    
    def _backup_completed(self, result):
        """备份完成回调"""
        # 隐藏进度条
        self.backup_progress.pack_forget()
        self.backup_progress_label.pack_forget()
        
        if result is None:
            messagebox.showerror(self.t("error"), self.t("backup_failed"))
            return
        
        backup_path, actual_size, abs_path = result
        
        # 格式化实际大小
        actual_size_str = self.backup_restore.format_size(actual_size)
        
        # 显示成功消息
        filename = os.path.basename(backup_path)
        success_msg = self.t("backup_success_text", 
                            filename=filename, 
                            size=actual_size_str, 
                            path=abs_path)
        messagebox.showinfo(self.t("backup_success_title"), success_msg)
        
        # 刷新备份列表
        self.refresh_backup_list()
    
    def refresh_backup_list(self):
        """刷新备份列表"""
        if not self.backup_restore:
            return
        
        # 清除现有项目
        for item in self.backup_tree.get_children():
            self.backup_tree.delete(item)
        
        # 获取备份目录
        backup_dir = self.backup_restore.get_backup_dir()
        if not backup_dir:
            return
        
        # 扫描备份
        backups = self.backup_restore.scan_backups(backup_dir)
        
        # 添加到列表
        for zip_path, timestamp, has_info, file_size in backups:
            filename = os.path.basename(zip_path)
            size_str = self.backup_restore.format_size(file_size)
            
            if timestamp:
                timestamp_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
            else:
                timestamp_str = ""
            
            if has_info:
                status = ""
            else:
                status = self.t("no_info_file")
            
            self.backup_tree.insert("", tk.END, 
                                   values=(timestamp_str, filename, size_str, status),
                                   tags=(zip_path,))
    
    def on_backup_select(self, event):
        """处理备份列表选择事件"""
        selected = self.backup_tree.selection()
        if selected:
            item_id = selected[0]
            tags = self.backup_tree.item(item_id, "tags")
            if tags:
                self.selected_backup_path = tags[0]
                self.restore_button.pack(side="left", padx=5)
                self.delete_backup_button.pack(side="left", padx=5)
        else:
            self.selected_backup_path = None
            self.restore_button.pack_forget()
            self.delete_backup_button.pack_forget()
    
    def delete_backup(self):
        """删除备份"""
        if not self.selected_backup_path:
            return
        
        if not self.backup_restore:
            return
        
        # 确认删除
        filename = os.path.basename(self.selected_backup_path)
        result = self.ask_yesno(
            self.t("delete_backup_confirm_title"),
            self.t("delete_backup_confirm_text", filename=filename),
            icon='warning'
        )
        
        if not result:
            return
        
        # 执行删除
        success = self.backup_restore.delete_backup(self.selected_backup_path)
        
        if success:
            messagebox.showinfo(self.t("success"), self.t("delete_backup_success"))
            # 清除选择
            self.selected_backup_path = None
            self.restore_button.pack_forget()
            self.delete_backup_button.pack_forget()
            # 刷新备份列表
            self.refresh_backup_list()
        else:
            messagebox.showerror(self.t("error"), self.t("delete_backup_failed"))
    
    def restore_backup(self):
        """还原备份"""
        if not self.selected_backup_path:
            return
        
        if not self.backup_restore:
            return
        
        # 第一次确认
        result = self.ask_yesno(
            self.t("restore_confirm_title"),
            self.t("restore_confirm_text"),
            icon='warning'
        )
        
        if not result:
            return
        
        # 检查必需文件
        missing_files = self.backup_restore.check_required_files(self.selected_backup_path)
        
        if missing_files:
            # 第二次确认（如果有缺失文件）
            files_str = ", ".join(missing_files)
            result = self.ask_yesno(
                self.t("restore_missing_files_title"),
                self.t("restore_missing_files_text", files=files_str),
                icon='warning'
            )
            
            if not result:
                return
        
        # 执行还原
        success = self.backup_restore.restore_backup(self.selected_backup_path, self.storage_dir)
        
        if success:
            messagebox.showinfo(self.t("success"), self.t("restore_success"))
            # 刷新其他tab的数据
            if self.storage_dir:
                self.load_screenshots()
                if self.save_analyzer:
                    self.save_analyzer.refresh()
        else:
            messagebox.showerror(self.t("error"), self.t("restore_failed"))
    
    def on_tab_changed(self, event=None):
        """处理 tab 切换事件，切换到存档分析页面时自动刷新"""
        try:
            # 获取当前选中的 tab 索引
            current_tab = self.notebook.index(self.notebook.select())
            # 如果切换到存档分析 tab（索引 0）且 save_analyzer 已初始化
            if current_tab == 0 and self.save_analyzer is not None:
                # 自动刷新存档分析页面
                self.save_analyzer.refresh()
            # 如果切换到备份/还原 tab（索引 2）且 backup_restore 已初始化
            elif current_tab == 2 and self.backup_restore is not None:
                # 刷新备份列表
                self.refresh_backup_list()
        except Exception:
            # 忽略错误，避免影响正常的 tab 切换
            pass
    
    def _start_file_monitor(self):
        """启动存档文件监控"""
        if not self.storage_dir:
            return
        
        # 停止之前的监控（如果存在）
        self._stop_file_monitor()
        
        # 设置存档文件路径和临时文件路径
        self.save_file_path = os.path.join(self.storage_dir, 'DevilConnection_sf.sav')
        self.temp_file_path = os.path.join(self.storage_dir, '.temp_sf.sav')
        
        # 清理可能存在的旧临时文件（防止上次异常退出遗留）
        self._cleanup_temp_file()
        
        # 初始化临时文件：如果不存在或已存在，都尝试写入当前存档内容
        self._initialize_temp_file()
        
        # 启动监控线程
        self.monitor_running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
    
    def _initialize_temp_file(self):
        """初始化临时文件：读取当前存档并写入临时文件"""
        if not os.path.exists(self.save_file_path):
            # 如果存档文件不存在，删除临时文件（如果存在）
            if os.path.exists(self.temp_file_path):
                try:
                    os.remove(self.temp_file_path)
                except:
                    pass
            return
        
        # 尝试读取当前存档文件（可能需要重试）
        save_content = None
        for retry in range(5):
            save_content = self._read_file_raw(self.save_file_path)
            if save_content is not None:
                break
            time.sleep(0.2)
        
        # 如果成功读取，写入临时文件
        if save_content is not None:
            self._write_temp_file(save_content)
    
    def _read_file_raw(self, file_path):
        """读取文件的原始内容（未解码的字符串）"""
        if not os.path.exists(file_path):
            return None
        
        try:
            # 方法1: 尝试正常打开
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read().strip()
            except (IOError, OSError, PermissionError):
                # 方法2: 如果失败，尝试二进制模式读取
                try:
                    with open(file_path, 'rb') as f:
                        raw_data = f.read()
                    return raw_data.decode('utf-8', errors='ignore').strip()
                except (IOError, OSError, PermissionError):
                    return None
        except Exception:
            return None
    
    def _write_temp_file(self, content):
        """写入临时文件"""
        try:
            with open(self.temp_file_path, 'w', encoding='utf-8') as f:
                f.write(content)
        except Exception:
            pass
    
    def _read_temp_file(self):
        """读取临时文件内容"""
        if not os.path.exists(self.temp_file_path):
            return None
        return self._read_file_raw(self.temp_file_path)
    
    def _get_file_content_hash(self, content):
        """获取文件内容的哈希值"""
        if content is None:
            return None
        try:
            import hashlib
            return hashlib.md5(content.encode('utf-8')).hexdigest()
        except:
            return None
    
    def _stop_file_monitor(self):
        """停止存档文件监控"""
        self.monitor_running = False
        if self.monitor_thread is not None:
            # 等待线程结束（最多等待1秒）
            self.monitor_thread.join(timeout=1.0)
            self.monitor_thread = None
        
        # 清理临时文件
        self._cleanup_temp_file()
    
    def _cleanup_temp_file(self):
        """清理临时文件"""
        if self.temp_file_path and os.path.exists(self.temp_file_path):
            try:
                os.remove(self.temp_file_path)
            except Exception:
                pass
    
    def _monitor_loop(self):
        """监控循环（在后台线程中运行）"""
        # 记录上次检测到的文件修改时间
        self._last_mtime = 0
        
        while self.monitor_running:
            try:
                self._check_file_changes()
                # 性能优化：增加轮询间隔到0.3秒，对于游戏存档足够了
                time.sleep(0.3)
            except Exception:
                # 出错继续监控
                pass
    
    def _check_file_changes(self):
        """检查文件是否有变动（通过比较真实文件和临时文件）"""
        if not self.save_file_path or not os.path.exists(self.save_file_path):
            return
        
        # 性能优化：先检查文件修改时间，避免不必要的内容读取
        try:
            current_mtime = os.path.getmtime(self.save_file_path)
            if hasattr(self, '_last_mtime') and current_mtime == self._last_mtime:
                # 文件未修改，跳过内容检查
                return
            self._last_mtime = current_mtime
        except (OSError, IOError):
            pass
        
        # 读取临时文件（应该总是成功，因为是我们自己创建的）
        temp_content = self._read_temp_file()
        if temp_content is None:
            # 如果临时文件不存在，重新初始化
            self._initialize_temp_file()
            return
        
        # 尝试读取真实存档文件（可能需要重试，因为可能被游戏锁定）
        save_content = None
        for retry in range(3):
            save_content = self._read_file_raw(self.save_file_path)
            if save_content is not None:
                break
            time.sleep(0.1)
        
        # 如果读取失败，跳过本次检查（下次再试）
        if save_content is None:
            return
        
        # 比较两个文件的内容
        temp_hash = self._get_file_content_hash(temp_content)
        save_hash = self._get_file_content_hash(save_content)
        
        # 如果内容不同，说明文件有变动
        if temp_hash is not None and save_hash is not None and temp_hash != save_hash:
            # 解析两个文件的数据并比较差异
            try:
                # 解析临时文件数据
                temp_data = self._parse_save_content(temp_content)
                # 解析真实文件数据
                save_data = self._parse_save_content(save_content)
                
                if temp_data is not None and save_data is not None:
                    # 直接使用深度比较（更可靠）
                    changes = self._deep_compare_data(temp_data, save_data)
                    if changes:
                        # 使用 after() 安全地更新 UI（tkinter 不是线程安全的）
                        # 使用默认参数避免lambda闭包问题
                        self.root.after(0, lambda c=changes: self._show_change_notification(c))
                    # 注意：即使changes为空，文件哈希已经不同，说明文件确实有变化
                    # 但为了不显示无意义的通知，我们只在检测到具体变化时才显示
                    # 如果文件哈希不同但changes为空，可能是比较逻辑的问题，暂时不显示通知
                    
                    # 无论是否检测到变化，都更新临时文件（因为文件哈希已经不同）
                    self._write_temp_file(save_content)
                elif temp_data is None or save_data is None:
                    # 如果解析失败，至少更新临时文件内容（避免重复检测）
                    self._write_temp_file(save_content)
            except Exception as e:
                # 如果解析失败，至少更新临时文件内容
                self._write_temp_file(save_content)
    
    def _parse_save_content(self, content):
        """解析存档文件内容为JSON对象"""
        if not content:
            return None
        
        try:
            unquoted = urllib.parse.unquote(content)
            data = json.loads(unquoted)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, ValueError):
            pass
        return None
    
    def _load_save_file(self):
        """加载存档文件（处理文件锁定问题）"""
        if not self.save_file_path or not os.path.exists(self.save_file_path):
            return None
        
        # 尝试多种方式读取文件，处理文件锁定问题
        try:
            # 方法1: 尝试正常打开（Python在Windows上默认支持共享读取）
            try:
                with open(self.save_file_path, 'r', encoding='utf-8') as f:
                    encoded = f.read().strip()
            except (IOError, OSError, PermissionError):
                # 方法2: 如果失败，尝试二进制模式读取
                try:
                    with open(self.save_file_path, 'rb') as f:
                        raw_data = f.read()
                    encoded = raw_data.decode('utf-8', errors='ignore').strip()
                except (IOError, OSError, PermissionError):
                    # 方法3: 如果还是失败，尝试使用临时副本（Windows特有）
                    if platform.system() == "Windows":
                        try:
                            # 使用shutil.copy2创建临时副本，然后读取
                            import tempfile
                            temp_fd, temp_path = tempfile.mkstemp(suffix='.sav')
                            try:
                                os.close(temp_fd)
                                shutil.copy2(self.save_file_path, temp_path)
                                with open(temp_path, 'r', encoding='utf-8') as f:
                                    encoded = f.read().strip()
                            finally:
                                # 清理临时文件
                                try:
                                    os.remove(temp_path)
                                except:
                                    pass
                        except:
                            return None
                    else:
                        return None
            
            # 如果文件为空，返回None
            if not encoded:
                return None
            
            unquoted = urllib.parse.unquote(encoded)
            data = json.loads(unquoted)
            
            # 确保返回的是有效的字典
            if isinstance(data, dict):
                return data
            return None
        except (IOError, OSError, PermissionError, json.JSONDecodeError, ValueError, UnicodeDecodeError):
            # 文件读取失败、权限错误、JSON解析失败等，返回None
            return None
        except Exception:
            # 其他未知错误，也返回None
            return None
    
    def _values_equal(self, old_val, new_val):
        """比较两个值是否相等（处理类型转换问题）"""
        # None值处理
        if old_val is None and new_val is None:
            return True
        if old_val is None or new_val is None:
            return False
        
        # 如果类型相同，直接比较
        if type(old_val) == type(new_val):
            # 对于列表和字典，需要深度比较
            if isinstance(old_val, list):
                return old_val == new_val
            if isinstance(old_val, dict):
                return old_val == new_val
            return old_val == new_val
        
        # 处理数字类型：int和float的数值比较
        if isinstance(old_val, (int, float)) and isinstance(new_val, (int, float)):
            # 对于整数，直接比较整数值
            if isinstance(old_val, int) and isinstance(new_val, int):
                return old_val == new_val
            # 对于浮点数，使用很小的误差范围来比较
            if isinstance(old_val, float) or isinstance(new_val, float):
                # 如果都是整数（但类型是float），转换为int比较
                if old_val.is_integer() and new_val.is_integer():
                    return int(old_val) == int(new_val)
                return abs(float(old_val) - float(new_val)) < 1e-10
            return int(old_val) == int(new_val)
        
        # 处理布尔值：True/False 和 1/0 的比较
        if isinstance(old_val, bool) and isinstance(new_val, (int, float)):
            return old_val == (new_val != 0)
        if isinstance(new_val, bool) and isinstance(old_val, (int, float)):
            return new_val == (old_val != 0)
        
        # 处理字符串：去除首尾空白后比较
        if isinstance(old_val, str) and isinstance(new_val, str):
            return old_val.strip() == new_val.strip()
        
        # 其他情况，转换为字符串比较（但排除列表和字典）
        if not isinstance(old_val, (dict, list)) and not isinstance(new_val, (dict, list)):
            return str(old_val) == str(new_val)
        
        # 如果一个是列表/字典，另一个不是，肯定不相等
        return False
    
    def _deep_compare_data(self, old_data, new_data, prefix=""):
        """深度比较数据，找出所有差异（使用严格比较）"""
        changes = []
        
        # 确保都是字典
        if not isinstance(old_data, dict):
            old_data = {}
        if not isinstance(new_data, dict):
            new_data = {}
        
        # 比较所有字段
        all_keys = set(old_data.keys()) | set(new_data.keys())
        
        for key in all_keys:
            full_key = f"{prefix}.{key}" if prefix else key
            
            old_value = old_data.get(key)
            new_value = new_data.get(key)
            
            # 字段被删除
            if key in old_data and key not in new_data:
                changes.append(f"-{full_key}")
            # 字段被新增
            elif key not in old_data and key in new_data:
                if isinstance(new_value, dict):
                    nested_changes = self._deep_compare_data({}, new_value, full_key)
                    changes.extend(nested_changes)
                else:
                    changes.append(f"+{full_key} = {self._format_value(new_value)}")
            # 字段值发生变化
            else:
                # 先检查值是否相等（使用_values_equal进行智能比较）
                if not self._values_equal(old_value, new_value):
                    if isinstance(old_value, dict) and isinstance(new_value, dict):
                        nested_changes = self._deep_compare_data(old_value, new_value, full_key)
                        changes.extend(nested_changes)
                    elif isinstance(old_value, list) and isinstance(new_value, list):
                        list_changes = self._compare_lists(full_key, old_value, new_value)
                        changes.extend(list_changes)
                    else:
                        # 普通值变化
                        changes.append(f"{full_key} {self._format_value(old_value)}→{self._format_value(new_value)}")
                # 如果值相等但类型不同，也记录变化（可能是游戏写入时的类型变化）
                elif type(old_value) != type(new_value):
                    # 对于数值类型，如果数值相同但类型不同，也记录
                    if isinstance(old_value, (int, float)) and isinstance(new_value, (int, float)):
                        if float(old_value) == float(new_value):
                            # 数值相同但类型不同，也记录（比如int(7) vs float(7.0)）
                            changes.append(f"{full_key} {self._format_value(old_value)} ({type(old_value).__name__})→{self._format_value(new_value)} ({type(new_value).__name__})")
        
        return changes
    
    def _compare_save_data(self, old_data, new_data, prefix=""):
        """比较两个存档数据，返回变更列表"""
        changes = []
        
        # 确保都是字典
        if not isinstance(old_data, dict):
            old_data = {}
        if not isinstance(new_data, dict):
            new_data = {}
        
        # 比较所有字段
        all_keys = set(old_data.keys()) | set(new_data.keys())
        
        for key in all_keys:
            # 构建完整键名（支持嵌套）
            full_key = f"{prefix}.{key}" if prefix else key
            
            old_value = old_data.get(key)
            new_value = new_data.get(key)
            
            # 字段被删除
            if key in old_data and key not in new_data:
                changes.append(f"- {full_key}")
            # 字段被新增
            elif key not in old_data and key in new_data:
                if isinstance(new_value, dict):
                    # 如果是字典，递归比较
                    nested_changes = self._compare_save_data({}, new_value, full_key)
                    changes.extend(nested_changes)
                else:
                    changes.append(f"+ {full_key} = {self._format_value(new_value)}")
            # 字段值发生变化
            else:
                # 先使用严格比较（直接 !=）
                if old_value != new_value:
                    # 如果是字典，递归比较
                    if isinstance(old_value, dict) and isinstance(new_value, dict):
                        nested_changes = self._compare_save_data(old_value, new_value, full_key)
                        changes.extend(nested_changes)
                    # 如果是列表，比较列表差异
                    elif isinstance(old_value, list) and isinstance(new_value, list):
                        list_changes = self._compare_lists(full_key, old_value, new_value)
                        changes.extend(list_changes)
                    else:
                        # 普通值变化（使用严格比较，确保所有变化都能检测到）
                        changes.append(f"{full_key} {self._format_value(old_value)}→{self._format_value(new_value)}")
                # 如果严格比较相等，但类型不同，也记录变化（可能是游戏写入时的类型变化）
                elif type(old_value) != type(new_value):
                    # 对于数字类型，如果数值相同但类型不同，也记录
                    if isinstance(old_value, (int, float)) and isinstance(new_value, (int, float)):
                        if float(old_value) == float(new_value):
                            # 数值相同但类型不同，也记录（比如int(7) vs float(7.0)）
                            changes.append(f"{full_key} {self._format_value(old_value)} ({type(old_value).__name__})→{self._format_value(new_value)} ({type(new_value).__name__})")
        
        return changes
    
    def _compare_lists(self, key, old_list, new_list):
        """比较两个列表的差异"""
        changes = []
        old_set = set(old_list)
        new_set = set(new_list)
        
        # 添加的元素
        added = new_set - old_set
        for item in added:
            changes.append(f"{key}.append({self._format_value(item)})")
        
        # 移除的元素
        removed = old_set - new_set
        for item in removed:
            changes.append(f"{key}.remove({self._format_value(item)})")
        
        return changes
    
    def _format_value(self, value):
        """格式化值用于显示"""
        if isinstance(value, (dict, list)):
            return str(value)
        elif isinstance(value, str):
            return f'"{value}"'
        elif isinstance(value, float):
            # 如果是浮点数，检查是否为整数
            if value.is_integer():
                return str(int(value))
            return str(value)
        elif isinstance(value, bool):
            return str(value)
        else:
            return str(value)
    
    def _show_change_notification(self, changes):
        """显示存档文件变动通知"""
        # 构建消息（硬编码中文）
        message_lines = ["sf.sav文件有如下更改："]
        message_lines.extend(changes)
        message = "\n".join(message_lines)
        
        # 创建新的通知（自动堆叠在上方）
        toast = Toast(
            self.root,
            message,
            duration=15000,  # 显示时间
            fade_in=200,     # 淡入
            fade_out=200     # 淡出
        )
        
        # 添加到活跃列表（Toast类会自动管理）
        self.active_toasts.append(toast)
    
    def on_closing(self):
        """窗口关闭事件处理"""
        # 停止文件监控（会清理临时文件）
        self._stop_file_monitor()
        # 关闭窗口
        self.root.destroy()
    
    def show_save_analyzer(self):
        """切换到存档分析 tab（保留此方法以兼容菜单，但菜单将被移除）"""
        if not self.storage_dir:
            messagebox.showerror(self.t("error"), self.t("select_dir_hint"))
            return
        
        if self.save_analyzer is None:
            self.init_save_analyzer()
        self.notebook.select(0)
    
    def show_help(self):
        """浏览器打开GitHub页面"""
        webbrowser.open("https://github.com/Hxueit/Devil-Connection-Screenshot-Tool")
    
    def update_ui_texts(self):
        """更新所有UI文本"""
        # 更新窗口标题
        self.root.title(self.t("window_title"))
        
        # 更新Directory菜单
        # 更新菜单项标签
        self.directory_menu.delete(0, tk.END)
        self.directory_menu.add_command(label=self.t("browse_dir"), command=self.select_dir)
        self.directory_menu.add_command(label=self.t("auto_detect_steam"), command=self.auto_detect_steam)
        
        # 更新Notebook tab标签
        try:
            self.notebook.tab(0, text=self.t("save_analyzer_tab"))
            self.notebook.tab(1, text=self.t("screenshot_management_tab"))
            self.notebook.tab(2, text=self.t("backup_restore_tab"))
        except:
            pass
        
        # 更新菜单栏标签 - 必须删除并重新插入才能更新标签
        try:
            # 查找所有Directory菜单的索引（可能有多个旧的）
            indices_to_delete = []
            try:
                menu_count = self.menubar.index(tk.END)
                if menu_count is not None:
                    menu_count = menu_count + 1
                    directory_menu_str = str(self.directory_menu)
                    for i in range(menu_count):
                        try:
                            menu_obj = self.menubar.entrycget(i, "menu")
                            if str(menu_obj) == directory_menu_str:
                                indices_to_delete.append(i)
                        except:
                            continue
            except:
                pass
            
            indices_to_delete.sort(reverse=True)  # 从后往前删除，避免索引变化
            for idx in indices_to_delete:
                try:
                    self.menubar.delete(idx)
                except:
                    pass
            
            # 重新插入Directory菜单到第一个位置
            self.menubar.insert_cascade(0, label=self.t("directory_menu"), menu=self.directory_menu)
        except Exception:
            try:
                self.menubar.entryconfig(0, label=self.t("directory_menu"))
            except:
                pass
        
        self.hint_label.config(text=self.t("select_dir_hint"))
        if self.storage_dir and self.success_label.winfo_viewable():
            success_text = self.t("steam_detect_success_text", path=self.storage_dir)
            self.success_label.config(text=success_text)
        if self.storage_dir:
            self.hint_label.pack_forget()
        else:
            self.hint_label.pack(pady=10)
            if self.success_label_timer is not None:
                self.root.after_cancel(self.success_label_timer)
                self.success_label_timer = None
            self.hide_success_label()
        
        self.list_label.config(text=self.t("screenshot_list"))
        self.preview_label_text.config(text=self.t("preview"))
        self.tree.heading("info", text=self.t("list_header"))
        self.sort_asc_button.config(text=self.t("sort_asc"))
        self.sort_desc_button.config(text=self.t("sort_desc"))
        self.add_button.config(text=self.t("add_new"))
        self.replace_button.config(text=self.t("replace_selected"))
        self.delete_button.config(text=self.t("delete_selected"))
        self.gallery_preview_button.config(text=self.t("gallery_preview"))
        self.export_button.config(text=self.t("export_image"))
        self.batch_export_button.config(text=self.t("batch_export"))
        
        # 更新备份/还原界面文本（如果已初始化）
        if hasattr(self, 'backup_button') and self.backup_button:
            self.backup_button.config(text=self.t("backup_button"))
        if hasattr(self, 'backup_list_title') and self.backup_list_title:
            self.backup_list_title.config(text=self.t("backup_list_title"))
        if hasattr(self, 'backup_refresh_button') and self.backup_refresh_button:
            self.backup_refresh_button.config(text=self.t("refresh"))
        if hasattr(self, 'backup_tree') and self.backup_tree:
            self.backup_tree.heading("timestamp", text=self.t("backup_timestamp"))
            self.backup_tree.heading("filename", text=self.t("backup_filename"))
            self.backup_tree.heading("size", text=self.t("backup_size"))
            self.backup_tree.heading("status", text=self.t("backup_status"))
        if hasattr(self, 'restore_button') and self.restore_button:
            self.restore_button.config(text=self.t("restore_button"))
        if hasattr(self, 'delete_backup_button') and self.delete_backup_button:
            self.delete_backup_button.config(text=self.t("delete_backup_button"))
        
        if self.storage_dir:
            self.load_screenshots()

    def hide_success_label(self):
        """隐藏成功信息标签"""
        if self.success_label_timer is not None:
            self.root.after_cancel(self.success_label_timer)
            self.success_label_timer = None
        self.success_label.pack_forget()
    
    def select_dir(self):
        dir_path = filedialog.askdirectory()
        # 支持Windows和Unix路径分隔符
        if dir_path and (dir_path.endswith('/_storage') or dir_path.endswith('\\_storage')):
            self.storage_dir = dir_path
            self.hint_label.pack_forget()
            self.hide_success_label()
            self.load_screenshots()
            self.update_batch_export_button()
            self.init_save_analyzer()
            self.init_backup_restore()
            # 启动文件监控
            self._start_file_monitor()
        else:
            messagebox.showerror(self.t("error"), self.t("dir_error"))
    
    def get_steam_path(self):
        """从Windows注册表获取Steam主路径，如果不是Windows则使用默认路径"""
        if platform.system() == "Windows" and winreg:
            try:
                # 读取Steam注册表路径
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")
                steam_path = winreg.QueryValueEx(key, "InstallPath")[0]
                winreg.CloseKey(key)
                return steam_path
            except:
                # 尝试32位注册表
                try:
                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam")
                    steam_path = winreg.QueryValueEx(key, "InstallPath")[0]
                    winreg.CloseKey(key)
                    return steam_path
                except:
                    pass
        
        # 非Windows系统或注册表读取失败，使用默认路径
        if platform.system() == "Windows":
            return os.path.expanduser(r"C:\Program Files (x86)\Steam")
        elif platform.system() == "Darwin":  # macOS
            return os.path.expanduser("~/Library/Application Support/Steam")
        else:  # Linux
            return os.path.expanduser("~/.steam/steam")
    
    def parse_libraryfolders_vdf(self, vdf_path):
        """解析libraryfolders.vdf文件，返回所有Steam库路径列表"""
        library_paths = []
        
        if not os.path.exists(vdf_path):
            return library_paths
        
        try:
            with open(vdf_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # VDF文件格式：使用引号和制表符
            # 查找所有 "path" 字段的值
            # 格式类似: "path"		"D:\\SteamLibrary" 或 "path"		"/home/user/SteamLibrary"
            # 支持Windows和Unix路径
            pattern = r'"path"\s+"([^"]+)"'
            matches = re.findall(pattern, content)
            
            for match in matches:
                # 处理转义字符（Windows路径中的双反斜杠）
                path = match.replace('\\\\', '\\').replace('\\/', '/')
                # 规范化路径
                path = os.path.normpath(path)
                if os.path.exists(path):
                    library_paths.append(path)
        except Exception as e:
            pass
        
        return library_paths
    
    def get_steam_libraries(self, steam_path):
        """获取所有Steam库路径"""
        libraries = []
        
        # 添加Steam主目录作为第一个库
        if os.path.exists(steam_path):
            libraries.append(steam_path)
        
        # 读取libraryfolders.vdf
        vdf_path = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
        additional_libraries = self.parse_libraryfolders_vdf(vdf_path)
        
        # 合并并去重
        for lib in additional_libraries:
            if lib not in libraries:
                libraries.append(lib)
        
        return libraries
    
    def parse_appmanifest_acf(self, acf_path):
        """解析appmanifest_3054820.acf文件，获取installdir字段"""
        if not os.path.exists(acf_path):
            return None
        
        try:
            with open(acf_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 查找 "installdir" 字段
            pattern = r'"installdir"\s+"([^"]+)"'
            match = re.search(pattern, content)
            if match:
                return match.group(1)
        except Exception as e:
            pass
        
        return None
    
    def find_game_directory(self, library_path):
        """在指定的Steam库中查找游戏目录"""
        steamapps_common = os.path.join(library_path, "steamapps", "common")
        
        if not os.path.exists(steamapps_common):
            return None
        
        game_folder_name = "でびるコネクショん"
        game_folder_path = os.path.join(steamapps_common, game_folder_name)
        
        if os.path.exists(game_folder_path) and os.path.isdir(game_folder_path):
            return game_folder_path
        
        # 从appmanifest文件获取安装目录
        appmanifest_path = os.path.join(library_path, "steamapps", "appmanifest_3054820.acf")
        installdir = self.parse_appmanifest_acf(appmanifest_path)
        
        if installdir:
            game_folder_path = os.path.join(steamapps_common, installdir)
            if os.path.exists(game_folder_path) and os.path.isdir(game_folder_path):
                return game_folder_path
        
        return None
    
    def auto_detect_steam_storage(self):
        """自动检测Steam游戏目录的_storage文件夹"""
        # 获取Steam主路径
        steam_path = self.get_steam_path()
        
        if not steam_path or not os.path.exists(steam_path):
            return None
        
        # 获取所有Steam库
        libraries = self.get_steam_libraries(steam_path)
        
        # 在每个库中查找游戏
        for library in libraries:
            game_dir = self.find_game_directory(library)
            if game_dir:
                # 检查_storage目录是否存在
                storage_path = os.path.join(game_dir, "_storage")
                if os.path.exists(storage_path) and os.path.isdir(storage_path):
                    return os.path.abspath(storage_path)
        
        return None
    
    def auto_detect_steam(self):
        """自动检测Steam游戏目录并设置"""
        storage_path = self.auto_detect_steam_storage()
        
        if storage_path:
            self.storage_dir = storage_path
            # 隐藏提示标签
            self.hint_label.pack_forget()
            # 取消之前的定时器（如果存在）
            if self.success_label_timer is not None:
                self.root.after_cancel(self.success_label_timer)
                self.success_label_timer = None
            # 显示成功信息
            success_text = self.t("steam_detect_success_text", path=storage_path)
            self.success_label.config(text=success_text)
            self.success_label.pack(anchor="nw", padx=10, pady=10)
            # 15秒后自动隐藏
            self.success_label_timer = self.root.after(15000, self.hide_success_label)
            self.load_screenshots()
            # 更新批量导出按钮状态
            self.update_batch_export_button()
            # 初始化存档分析界面
            self.init_save_analyzer()
            # 初始化备份/还原界面
            self.init_backup_restore()
            # 启动文件监控
            self._start_file_monitor()
        else:
            messagebox.showinfo(self.t("warning"), self.t("steam_detect_not_found"))

    def load_screenshots(self):
        if not self.storage_dir:
            return

        ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_ids.sav')
        all_ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_all_ids.sav')

        if not (os.path.exists(ids_path) and os.path.exists(all_ids_path)):
            messagebox.showerror(self.t("error"), self.t("missing_files"))
            return

        # 加载 ids 和 all_ids
        self.ids_data = self.load_and_decode(ids_path)
        self.all_ids_data = self.load_and_decode(all_ids_path)

        # 扫描 sav 对（使用缓存优化）
        import time
        current_time = time.time()
        
        # 检查缓存是否有效
        if (self._file_list_cache is None or 
            current_time - self._file_list_cache_time > self._file_list_cache_ttl or
            self._file_list_cache[0] != self.storage_dir):
            # 缓存失效，重新扫描
            self.sav_pairs = {}
            try:
                file_list = os.listdir(self.storage_dir)
                for file in file_list:
                    if file.startswith('DevilConnection_photo_') and file.endswith('.sav'):
                        base_name = file.rsplit('.sav', 1)[0] 
                        parts = base_name.split('_')
                        if len(parts) == 3:  
                            id_str = parts[2]
                            if id_str not in self.sav_pairs:
                                self.sav_pairs[id_str] = [None, None]
                            self.sav_pairs[id_str][0] = file
                        elif len(parts) == 4 and parts[3] == 'thumb': 
                            id_str = parts[2]
                            if id_str not in self.sav_pairs:
                                self.sav_pairs[id_str] = [None, None]
                            self.sav_pairs[id_str][1] = file
                
                # 更新缓存
                self._file_list_cache = (self.storage_dir, self.sav_pairs.copy())
                self._file_list_cache_time = current_time
            except OSError:
                # 如果目录访问失败，清空缓存
                self.sav_pairs = {}
                self._file_list_cache = None
        else:
            # 使用缓存
            _, self.sav_pairs = self._file_list_cache
            self.sav_pairs = self.sav_pairs.copy()  # 创建副本，避免修改缓存

        # 更新列表
        # 清除所有状态指示器的定时器
        for item_id, original_text, after_id, indicator_type in self.status_indicators:
            try:
                if after_id:
                    self.root.after_cancel(after_id)
            except:
                pass
        self.status_indicators.clear()
        
        # 清除所有项目
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.checkbox_vars.clear()
        
        # 添加复选框和项目，每6个截图插入一个标题行
        screenshot_count = 0
        page_number = 1
        
        for idx, item in enumerate(self.ids_data):
            # 每12个截图的开始插入"页面X ←"标题行
            if screenshot_count % 12 == 0:
                # 插入"页面X ←"标题行
                page_text_left = f"{self.t('page')} {page_number} ←"
                header_item_id_left = self.tree.insert("", tk.END, text="", 
                                                      values=("", page_text_left), 
                                                      tags=("PageHeaderLeft",))
                # 标题行不添加到checkbox_vars，不能被选择
            
            id_str = item['id']
            date_str = item['date']
            main_file = self.sav_pairs.get(id_str, [None, None])[0] or self.t("missing_main_file")
            display = f"{id_str} - {main_file} - {date_str}"
            
            # 创建复选框变量
            var = tk.BooleanVar()
            var.trace('w', lambda *args, v=var, iid=id_str: self.on_checkbox_change(v, iid))
            
            # 插入Treeview项目（select列显示复选框，info列显示信息）
            item_id = self.tree.insert("", tk.END, text="", values=("", display), tags=(id_str,))
            self.checkbox_vars[item_id] = (var, id_str)
            
            # 更新复选框显示
            self.update_checkbox_display(item_id)
            
            screenshot_count += 1
            
            # 每6个截图后插入"页面X →"标题行
            # 如果是12的倍数，则跳过
            # （第6, 18, 30...个截图后）
            if screenshot_count % 6 == 0 and screenshot_count % 12 != 0:
                # 插入"页面X →"标题行
                page_text_right = f"{self.t('page')} {page_number} →"
                header_item_id_right = self.tree.insert("", tk.END, text="", 
                                                       values=("", page_text_right), 
                                                       tags=("PageHeaderRight",))
                # 标题行不添加到checkbox_vars，不能被选择
            
            # 每12个截图后，页面号递增
            if screenshot_count % 12 == 0:
                page_number += 1
        
        # 更新全选标题显示
        self.update_select_all_header()

    def sort_ascending(self):
        """按时间正序排序"""
        if not self.storage_dir:
            messagebox.showerror(self.t("error"), self.t("select_dir_hint"))
            return
        
        # 确认对话框
        result = self.ask_yesno(
            self.t("confirm_sort"),
            self.t("sort_warning"),
            icon='warning'
        )
        
        if not result:
            return
        
        # 按时间正序排序
        self.ids_data.sort(key=lambda x: datetime.strptime(x['date'], '%Y/%m/%d %H:%M:%S'), reverse=False)
        
        # 更新all_ids_data的顺序
        self.all_ids_data = [item['id'] for item in self.ids_data]
        
        # 保存到文件
        ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_ids.sav')
        all_ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_all_ids.sav')
        self.encode_and_save(self.ids_data, ids_path)
        self.encode_and_save(self.all_ids_data, all_ids_path)
        
        # 重新加载列表以更新显示
        self.load_screenshots()
        
        messagebox.showinfo(self.t("success"), self.t("sort_asc_success"))

    def sort_descending(self):
        """按时间倒序排序"""
        if not self.storage_dir:
            messagebox.showerror(self.t("error"), self.t("select_dir_hint"))
            return
        
        # 确认对话框
        result = self.ask_yesno(
            self.t("confirm_sort"),
            self.t("sort_warning"),
            icon='warning'
        )
        
        if not result:
            return
        
        # 按时间倒序排序
        self.ids_data.sort(key=lambda x: datetime.strptime(x['date'], '%Y/%m/%d %H:%M:%S'), reverse=True)
        
        # 更新all_ids_data的顺序
        self.all_ids_data = [item['id'] for item in self.ids_data]
        
        # 保存到文件
        ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_ids.sav')
        all_ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_all_ids.sav')
        self.encode_and_save(self.ids_data, ids_path)
        self.encode_and_save(self.all_ids_data, all_ids_path)
        
        # 重新加载列表以更新显示
        self.load_screenshots()
        
        messagebox.showinfo(self.t("success"), self.t("sort_desc_success"))

    def update_checkbox_display(self, item_id):
        """更新复选框显示"""
        if item_id in self.checkbox_vars:
            var, id_str = self.checkbox_vars[item_id]
            checkbox_text = "☑" if var.get() else "☐"
            # 更新select列的值
            current_values = list(self.tree.item(item_id, "values"))
            if len(current_values) >= 2:
                current_values[0] = checkbox_text
                self.tree.item(item_id, values=tuple(current_values))
    
    def on_checkbox_change(self, var, id_str):
        """复选框状态变化时的处理"""
        # 更新显示
        for item_id, (v, iid) in self.checkbox_vars.items():
            if iid == id_str:
                self.update_checkbox_display(item_id)
                break
        
        # 更新全选复选框状态
        self.update_select_all_state()
        
        # 更新按钮状态
        self.update_button_states()
        
        # 更新批量导出按钮显示
        self.update_batch_export_button()
    
    def update_select_all_state(self):
        """更新全选复选框状态"""
        # 更新标题显示
        self.update_select_all_header()
    
    def toggle_select_all(self):
        """全选/取消全选"""
        # 检查当前是否全选
        if not self.checkbox_vars:
            return
        
        all_selected = all(var.get() for var, _ in self.checkbox_vars.values())
        select_all = not all_selected  # 切换状态
        
        for var, _ in self.checkbox_vars.values():
            var.set(select_all)
        # 更新所有复选框显示
        for item_id in self.checkbox_vars.keys():
            self.update_checkbox_display(item_id)
        # 更新标题显示
        self.update_select_all_header()
        self.update_button_states()
        self.update_batch_export_button()
    
    def update_select_all_header(self):
        """更新全选标题显示"""
        if not self.checkbox_vars:
            self.tree.heading("select", text="☐", anchor="center", command=self.toggle_select_all)
            return
        
        all_selected = all(var.get() for var, _ in self.checkbox_vars.values())
        checkbox_text = "☑" if all_selected else "☐"
        self.tree.heading("select", text=checkbox_text, anchor="center", command=self.toggle_select_all)
    
    def get_selected_ids(self):
        """获取所有选中的ID列表"""
        selected_ids = []
        for var, id_str in self.checkbox_vars.values():
            if var.get():
                selected_ids.append(id_str)
        return selected_ids
    
    def get_selected_count(self):
        """获取选中的数量"""
        return len(self.get_selected_ids())
    
    def update_button_states(self):
        """更新按钮状态"""
        selected_count = self.get_selected_count()
        # 如果选择了大于等于2个，禁用替换按钮
        if selected_count >= 2:
            self.replace_button.config(state="disabled")
        else:
            self.replace_button.config(state="normal")
    
    def update_batch_export_button(self):
        """更新批量导出按钮显示"""
        if not self.storage_dir:
            self.batch_export_button.pack_forget()
            return
        
        selected_count = self.get_selected_count()
        if selected_count > 0:
            self.batch_export_button.pack(pady=5)
        else:
            self.batch_export_button.pack_forget()
    
    def on_tree_select(self, event):
        """处理Treeview选择事件，显示预览"""
        selected = self.tree.selection()
        if not selected:
            # 清空预览
            self.preview_label.config(image='', bg="lightgray")
            self.preview_photo = None
            # 隐藏导出按钮
            self.export_button.pack_forget()
            return
        
        item_id = selected[0]
        # 检查是否是标题行，如果是则清除选择
        item_tags = self.tree.item(item_id, "tags")
        if item_tags and ("PageHeaderLeft" in item_tags or "PageHeaderRight" in item_tags):
            self.tree.selection_remove(item_id)
            return
        
        if item_id in self.checkbox_vars:
            _, id_str = self.checkbox_vars[item_id]
            self.show_preview(id_str)
            # 显示导出按钮
            self.export_button.pack(pady=5)
    
    def on_button1_click(self, event):
        """统一处理Button-1点击事件：先检查复选框，再处理拖拽"""
        region = self.tree.identify_region(event.x, event.y)
        
        # 检查是否是复选框点击
        if region == "cell":
            column = self.tree.identify_column(event.x)  # 只传x坐标
            # 检查是否是select列（复选框列）
            # ***即使#0列被隐藏，仍然存在，所以select列是#1*** ★
            # 为了兼容性，也检查x坐标范围（select列宽度是40）
            if column == "#1" or (event.x < 40 and event.x > 0):
                item_id = self.tree.identify_row(event.y)
                if item_id:
                    # 检查是否是标题行，标题行不能点击复选框
                    item_tags = self.tree.item(item_id, "tags")
                    if item_tags and ("PageHeaderLeft" in item_tags or "PageHeaderRight" in item_tags):
                        return "break"
                    if item_id in self.checkbox_vars:
                        var, _ = self.checkbox_vars[item_id]
                        var.set(not var.get())
                        # 阻止后续事件处理（包括拖拽和选择）
                        return "break"
        elif region == "heading":
            column = self.tree.identify_column(event.x)
            if column == "#1" or (event.x < 40 and event.x > 0): 
                # toggle_select_all 已经在 heading 的 command 中处理了
                # 不返回 "break"，让 command 回调正常执行
                # 但阻止拖拽
                self.drag_start_item = None
                self.drag_target_item = None
                return
        
        # 如果不是复选框点击，则处理拖拽
        # 获取鼠标点击位置对应的列表项
        item = self.tree.identify_row(event.y)
        if item:
            # 检查是否是标题行，标题行不能拖拽
            item_tags = self.tree.item(item, "tags")
            if item_tags and ("PageHeaderLeft" in item_tags or "PageHeaderRight" in item_tags):
                self.drag_start_item = None
                self.drag_target_item = None
                return
            self.drag_start_item = item
            self.drag_start_y = event.y
            self.drag_target_item = None
            self.is_dragging = False

    def on_drag_motion(self, event):
        """拖拽过程中，检测是否真的在拖拽，并显示视觉反馈"""
        if self.drag_start_item is None:
            return
        
        # 检测鼠标是否移动了至少5像素
        if abs(event.y - self.drag_start_y) > 5:
            self.is_dragging = True
            
            # 高亮显示被拖动的行
            if self.tree.exists(self.drag_start_item):
                current_tags = list(self.tree.item(self.drag_start_item, "tags"))
                if "Dragging" not in current_tags:
                    current_tags.append("Dragging")
                    self.tree.item(self.drag_start_item, tags=tuple(current_tags))
            
            # 获取当前鼠标位置对应的列表项（目标位置）
            target_item = self.tree.identify_row(event.y)
            
            
            # 更新目标位置
            self.drag_target_item = target_item
            
            # 计算拖动方向（从上向下还是从下向上）
            children = list(self.tree.get_children())
            if self.drag_start_item in children and target_item in children:
                start_index = children.index(self.drag_start_item)
                target_index = children.index(target_item)
                is_dragging_down = target_index > start_index
            else:
                # 如果无法确定，根据鼠标Y坐标判断
                if self.tree.exists(self.drag_start_item):
                    start_bbox = self.tree.bbox(self.drag_start_item)
                    if start_bbox:
                        is_dragging_down = event.y > start_bbox[1] + start_bbox[3] / 2
                    else:
                        is_dragging_down = True
                else:
                    is_dragging_down = True
            
            # 显示指示线
            if target_item and target_item != self.drag_start_item:
                # 检查是否是标题行，标题行不能作为目标
                target_tags = self.tree.item(target_item, "tags")
                if target_tags and ("PageHeaderLeft" in target_tags or "PageHeaderRight" in target_tags):
                    # 如果是标题行，清除指示线
                    self.drag_target_item = None
                    self.drag_indicator_line.place_forget()
                    self.current_indicator_target = None
                    self.current_indicator_position = None
                else:
                    # 显示指示线
                    self.show_drag_indicator_line(target_item, is_dragging_down)
            else:
                # 没有有效目标，清除指示线
                self.drag_target_item = None
                self.drag_indicator_line.place_forget()
                self.current_indicator_target = None
                self.current_indicator_position = None

    def show_drag_indicator_line(self, target_item, is_dragging_down):
        """显示拖动指示线"""
        if not self.tree.exists(target_item):
            self.drag_indicator_line.place_forget()
            self.current_indicator_target = None
            self.current_indicator_position = None
            return
        
        # 先清除指示线，确保旧位置被清除
        self.drag_indicator_line.place_forget()
        
        # 获取目标行的位置和大小
        bbox = self.tree.bbox(target_item)
        if not bbox:
            self.current_indicator_target = None
            self.current_indicator_position = None
            return
        
        x, y, width, height = bbox
        
        # 获取Treeview在父容器中的位置
        tree_x = self.tree.winfo_x()
        tree_y = self.tree.winfo_y()
        
        # 计算指示线的位置
        # 如果从上向下拖动，线显示在行的下方
        # 如果从下向上拖动，线显示在行的上方
        if is_dragging_down:
            # 显示在行下方
            line_y = tree_y + y + height
        else:
            # 显示在行上方
            line_y = tree_y + y
        
        # 检查目标是否改变，如果目标项和位置都相同，则不需要更新
        if (self.current_indicator_target == target_item and 
            self.current_indicator_position == line_y):
            # 目标未改变，恢复显示（因为上面已经place_forget了）
            tree_width = self.tree.winfo_width()
            self.drag_indicator_line.place(x=tree_x, y=line_y, width=tree_width, height=3)
            self.drag_indicator_line.lift()
            return
        
        # 目标改变了，更新指示线
        self.current_indicator_target = target_item
        self.current_indicator_position = line_y
        
        # 获取Treeview的宽度
        tree_width = self.tree.winfo_width()
        
        # 显示指示线，并提升到最前面确保可见
        self.drag_indicator_line.place(x=tree_x, y=line_y, width=tree_width, height=3)
        self.drag_indicator_line.lift()
    
    def on_drag_end(self, event):
        """结束拖拽，移动项目并保存顺序"""
        # 清除拖动时的视觉反馈
        if self.drag_start_item and self.tree.exists(self.drag_start_item):
            start_tags = list(self.tree.item(self.drag_start_item, "tags"))
            if "Dragging" in start_tags:
                start_tags.remove("Dragging")
                self.tree.item(self.drag_start_item, tags=tuple(start_tags))
        
        # 清除指示线
        self.drag_indicator_line.place_forget()
        self.current_indicator_target = None
        self.current_indicator_position = None
        
        if self.drag_start_item is None:
            self.drag_target_item = None
            return
        
        # 如果没有真正拖拽（只是单击），不执行移动操作
        if not self.is_dragging:
            self.drag_start_item = None
            self.drag_start_y = None
            self.drag_target_item = None
            self.is_dragging = False
            return
        
        # 获取目标位置（优先使用drag_target_item，如果没有则使用鼠标位置）
        end_item = self.drag_target_item if self.drag_target_item else self.tree.identify_row(event.y)
        
        if not end_item or end_item == self.drag_start_item:
            self.drag_start_item = None
            self.drag_start_y = None
            self.drag_target_item = None
            self.is_dragging = False
            return
        
        # 检查起始项和目标项是否是标题行，标题行不能拖拽
        start_tags = self.tree.item(self.drag_start_item, "tags")
        end_tags = self.tree.item(end_item, "tags")
        if (start_tags and ("PageHeaderLeft" in start_tags or "PageHeaderRight" in start_tags)) or \
           (end_tags and ("PageHeaderLeft" in end_tags or "PageHeaderRight" in end_tags)):
            self.drag_start_item = None
            self.drag_start_y = None
            self.drag_target_item = None
            self.is_dragging = False
            return
        
        # 获取起始和目标索引
        children = list(self.tree.get_children())
        
        # 将Treeview索引转换为ids_data索引（排除标题行）
        def get_data_index(tree_index):
            """将Treeview中的索引转换为ids_data中的索引（排除标题行）"""
            data_index = 0
            for i in range(tree_index):
                item_id = children[i]
                item_tags = self.tree.item(item_id, "tags")
                # 如果不是标题行，则计入数据索引
                if item_tags and ("PageHeaderLeft" not in item_tags and "PageHeaderRight" not in item_tags):
                    data_index += 1
            return data_index
        
        start_tree_index = children.index(self.drag_start_item)
        end_tree_index = children.index(end_item)
        
        # 转换为数据索引
        start_index = get_data_index(start_tree_index)
        end_index = get_data_index(end_tree_index)
        
        # 清除之前的箭头指示器
        self.clear_drag_indicators()
        
        # 移动Treeview中的项目
        item_values = self.tree.item(self.drag_start_item)
        moved_item_id = item_values['tags'][0] if item_values['tags'] else None
        
        # 获取目标位置原来的item ID（用于显示箭头）
        target_original_id = None
        if end_item:
            target_item_values = self.tree.item(end_item)
            target_original_id = target_item_values['tags'][0] if target_item_values['tags'] else None
        
        # 保存复选框状态和值
        checkbox_data = None
        checkbox_text = ""
        if self.drag_start_item in self.checkbox_vars:
            checkbox_data = self.checkbox_vars.pop(self.drag_start_item)
            var, _ = checkbox_data
            checkbox_text = "☑" if var.get() else "☐"
        
        # 保存当前值
        current_values = list(item_values['values'])
        
        # 删除项目
        self.tree.delete(self.drag_start_item)
        
        # 重新获取children列表（因为删除了一个项目，索引会变化）
        children = list(self.tree.get_children())
        
        # 重新插入到目标位置
        # 注意：删除后，如果向下移动，end_tree_index需要调整（因为删除了start_tree_index的项目）
        if end_tree_index > start_tree_index:
            # 向下移动：删除start_tree_index的项目后，end_tree_index对应的项目位置变成了end_tree_index-1
            # 如果要插入到目标项目之后（"拖到底下"），应该插入到位置end_tree_index
            # 因为insert是在指定位置之前插入，所以如果要插入到end_tree_index位置之后，应该用end_tree_index+1
            # 但删除后，end_tree_index位置的项目现在在end_tree_index-1，所以插入到end_tree_index就是插入到它之后
            insert_index = end_tree_index
            if insert_index < 0:
                insert_index = 0
            if insert_index <= len(children):
                # 在指定位置插入（会插入到该位置之前，但由于我们用的是end_tree_index，正好是目标位置之后）
                new_item = self.tree.insert("", insert_index, text=item_values['text'], values=tuple(current_values), tags=item_values['tags'])
            else:
                # 插入到末尾
                new_item = self.tree.insert("", tk.END, text=item_values['text'], values=tuple(current_values), tags=item_values['tags'])
        else:
            # 向上移动：目标位置不变（因为删除的是后面的项目，不影响前面的索引）
            if end_tree_index <= len(children):
                new_item = self.tree.insert("", end_tree_index, text=item_values['text'], values=tuple(current_values), tags=item_values['tags'])
            else:
                new_item = self.tree.insert("", tk.END, text=item_values['text'], values=tuple(current_values), tags=item_values['tags'])
        
        # 恢复复选框状态
        if checkbox_data:
            self.checkbox_vars[new_item] = checkbox_data
            self.update_checkbox_display(new_item)
        
        # 同步更新ids_data和all_ids_data的顺序
        moved_item = self.ids_data.pop(start_index)
        self.ids_data.insert(end_index, moved_item)
        
        # 更新all_ids_data的顺序
        new_all_ids_order = [item['id'] for item in self.ids_data]
        self.all_ids_data = new_all_ids_order
        
        # 保存更新后的顺序到文件
        ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_ids.sav')
        all_ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_all_ids.sav')
        self.encode_and_save(self.ids_data, ids_path)
        self.encode_and_save(self.all_ids_data, all_ids_path)
        
        # 保存移动的item的ID（用于重新加载后恢复选择）
        moved_id = moved_item_id  
        
        # 记录移动方向（用于显示箭头指示器）
        is_moving_down = end_index > start_index
        
        # 计算填补被移动项原位置的项的ID（用于显示箭头）
        # 注意：这里需要使用Treeview索引，因为children是Treeview列表
        # 需要将数据索引转换为Treeview索引
        def get_tree_index(data_index):
            """将ids_data中的索引转换为Treeview中的索引（包含标题行）"""
            tree_index = 0
            data_count = 0
            for i, item_id in enumerate(children):
                item_tags = self.tree.item(item_id, "tags")
                # 如果不是标题行，则计入数据计数
                if item_tags and ("PageHeaderLeft" not in item_tags and "PageHeaderRight" not in item_tags):
                    if data_count == data_index:
                        return i
                    data_count += 1
            return len(children)  # 如果找不到，返回末尾
        
        # 计算填补被移动项原位置的项的ID（用于显示箭头）
        # 当向下移动时，start_index+1位置的项会向上移动到start_index位置（填补空位）
        # 当向上移动时，start_index-1位置的项会向下移动到start_index位置（填补空位）
        # 注意：这个项在移动后位于start_index位置（被移动项的原位置）
        affected_item_id = None
        # 使用Treeview索引来访问children列表
        start_tree_idx_for_children = get_tree_index(start_index)
        if is_moving_down and start_tree_idx_for_children + 1 < len(children):
            # 向下移动：start_tree_idx_for_children+1位置的项会向上移动到start_tree_idx_for_children位置
            affected_item = children[start_tree_idx_for_children + 1]
            affected_item_values = self.tree.item(affected_item)
            affected_item_id = affected_item_values['tags'][0] if affected_item_values['tags'] else None
        elif not is_moving_down and start_tree_idx_for_children > 0:
            # 向上移动：start_tree_idx_for_children-1位置的项会向下移动到start_tree_idx_for_children位置
            affected_item = children[start_tree_idx_for_children - 1]
            affected_item_values = self.tree.item(affected_item)
            affected_item_id = affected_item_values['tags'][0] if affected_item_values['tags'] else None
        
        # 重新加载列表以更新显示
        self.load_screenshots()
        
        # 恢复选择：根据ID找到新的item
        moved_item = None
        if moved_id:
            children = list(self.tree.get_children())
            for tree_item_id in children:
                item_tags = self.tree.item(tree_item_id, "tags")
                if item_tags and item_tags[0] == moved_id:
                    moved_item = tree_item_id
                    self.tree.selection_set(tree_item_id)
                    # 滚动到选中项
                    self.tree.see(tree_item_id)
                    break
        
        # 显示箭头指示器
        # 移动后，被移动的项位于end_index位置，填补原位置的项位于start_index位置
        children = list(self.tree.get_children())
        
        if moved_item:
            # 被移动的项：向下移动显示↓↓↓（绿色），向上移动显示↑↑↑（粉色）
            self.show_drag_indicator_on_item(moved_item, not is_moving_down)
        
        # 将数据索引转换为Treeview索引（重新加载后的列表）
        def get_tree_index_after_reload(data_index):
            """将ids_data中的索引转换为重新加载后Treeview中的索引（包含标题行）"""
            tree_index = 0
            data_count = 0
            for i, item_id in enumerate(children):
                item_tags = self.tree.item(item_id, "tags")
                # 如果不是标题行，则计入数据计数
                if item_tags and ("PageHeaderLeft" not in item_tags and "PageHeaderRight" not in item_tags):
                    if data_count == data_index:
                        return i
                    data_count += 1
            return len(children)  # 如果找不到，返回末尾
        
        start_tree_idx_after_reload = get_tree_index_after_reload(start_index)
        if start_tree_idx_after_reload < len(children):
            item_at_start_pos = children[start_tree_idx_after_reload]
            item_tags = self.tree.item(item_at_start_pos, "tags")
            # 确保不是被移动的项本身
            if item_tags and item_tags[0] != moved_id:
                self.show_drag_indicator_on_item(item_at_start_pos, is_moving_down)
        
        self.drag_start_item = None
        self.drag_start_y = None
        self.drag_target_item = None
        self.is_dragging = False
    
    def clear_drag_indicators(self):
        """清除所有箭头指示器"""
        for item_id, original_text, after_id in self.drag_indicators:
            try:
                # 取消定时器
                if after_id:
                    self.root.after_cancel(after_id)
                # 恢复原始文本
                if self.tree.exists(item_id):
                    current_values = list(self.tree.item(item_id, "values"))
                    if len(current_values) >= 2:
                        # 移除箭头前缀，恢复原始文本
                        info_text = current_values[1]
                        # 移除箭头前缀（↑↑↑或↓↓↓）
                        if info_text.startswith("↑↑↑"):
                            info_text = info_text[3:].lstrip()
                        elif info_text.startswith("↓↓↓"):
                            info_text = info_text[3:].lstrip()
                        current_values[1] = info_text
                        self.tree.item(item_id, values=tuple(current_values))
                        # 移除tag
                        current_tags = list(self.tree.item(item_id, "tags"))
                        if "DragIndicatorUp" in current_tags:
                            current_tags.remove("DragIndicatorUp")
                        if "DragIndicatorDown" in current_tags:
                            current_tags.remove("DragIndicatorDown")
                        self.tree.item(item_id, tags=tuple(current_tags))
            except:
                pass
        self.drag_indicators.clear()
    
    def show_drag_indicator_on_item(self, item_id, show_up_arrows):
        """在指定item的名字前显示箭头指示器"""
        if not self.tree.exists(item_id):
            return
        
        # 获取当前值
        current_values = list(self.tree.item(item_id, "values"))
        if len(current_values) < 2:
            return
        
        original_text = current_values[1]  # 保存原始文本
        
        # 确定箭头符号和颜色
        if show_up_arrows:
            # 显示↑↑↑（粉色 #D06CAA）
            arrow_prefix = "↑↑↑"
            style_tag = "DragIndicatorDown" 
        else:
            # 显示↓↓↓（绿色 #85A9A5）
            arrow_prefix = "↓↓↓"
            style_tag = "DragIndicatorUp" 
        
        # 在名字前添加箭头
        new_text = f"{arrow_prefix} {original_text}"
        current_values[1] = new_text
        
        # 更新item
        current_tags = list(self.tree.item(item_id, "tags"))
        if style_tag not in current_tags:
            current_tags.append(style_tag)
        self.tree.item(item_id, values=tuple(current_values), tags=tuple(current_tags))
        
        # 设置15秒后自动清除
        def remove_indicator():
            try:
                if self.tree.exists(item_id):
                    current_values = list(self.tree.item(item_id, "values"))
                    if len(current_values) >= 2:
                        info_text = current_values[1]
                        # 移除箭头前缀
                        if info_text.startswith("↑↑↑"):
                            info_text = info_text[3:].lstrip()
                        elif info_text.startswith("↓↓↓"):
                            info_text = info_text[3:].lstrip()
                        current_values[1] = info_text
                        self.tree.item(item_id, values=tuple(current_values))
                        # 移除tag
                        current_tags = list(self.tree.item(item_id, "tags"))
                        if "DragIndicatorUp" in current_tags:
                            current_tags.remove("DragIndicatorUp")
                        if "DragIndicatorDown" in current_tags:
                            current_tags.remove("DragIndicatorDown")
                        self.tree.item(item_id, tags=tuple(current_tags))
                # 从列表中移除
                self.drag_indicators = [(iid, orig, aid) for iid, orig, aid in self.drag_indicators if iid != item_id]
            except:
                pass
        
        after_id = self.root.after(15000, remove_indicator)  # 15秒后移除
        
        # 记录指示器信息
        self.drag_indicators.append((item_id, original_text, after_id))

    def show_status_indicator(self, id_str, is_new=True):
        """在指定ID的截图名称前显示状态指示器（新截图或替换截图）"""
        # 找到对应的item_id
        item_id = None
        for tree_item_id in self.tree.get_children():
            item_tags = self.tree.item(tree_item_id, "tags")
            if item_tags and item_tags[0] == id_str:
                item_id = tree_item_id
                break
        
        if not item_id or not self.tree.exists(item_id):
            return
        
        # 获取当前值
        current_values = list(self.tree.item(item_id, "values"))
        if len(current_values) < 2:
            return
        
        original_text = current_values[1]  # 保存原始文本
        
        # 确定标记符号和颜色tag
        if is_new:
            # 新截图：显示"⚝ "
            indicator_prefix = "⚝ "
            style_tag = "NewIndicator"
        else:
            # 替换截图：显示"✧ "
            indicator_prefix = "✧ "
            style_tag = "ReplaceIndicator"
        
        # 检查是否已经有标记（避免重复添加）
        info_text = current_values[1]
        if info_text.startswith("⚝ ") or info_text.startswith("✧ "):
            # 如果已经有标记，先移除
            if info_text.startswith("⚝ "):
                info_text = info_text[2:].lstrip()
            elif info_text.startswith("✧ "):
                info_text = info_text[2:].lstrip()
            original_text = info_text
        
        # 在名字前添加标记
        new_text = f"{indicator_prefix}{original_text}"
        current_values[1] = new_text
        
        # 更新item
        current_tags = list(self.tree.item(item_id, "tags"))
        if style_tag not in current_tags:
            current_tags.append(style_tag)
        self.tree.item(item_id, values=tuple(current_values), tags=tuple(current_tags))
        
        # 设置15秒后自动清除
        def remove_indicator():
            try:
                if self.tree.exists(item_id):
                    current_values = list(self.tree.item(item_id, "values"))
                    if len(current_values) >= 2:
                        info_text = current_values[1]
                        # 移除标记前缀
                        if info_text.startswith("⚝ "):
                            info_text = info_text[2:].lstrip()
                        elif info_text.startswith("✧ "):
                            info_text = info_text[2:].lstrip()
                        current_values[1] = info_text
                        self.tree.item(item_id, values=tuple(current_values))
                        # 移除tag
                        current_tags = list(self.tree.item(item_id, "tags"))
                        if "NewIndicator" in current_tags:
                            current_tags.remove("NewIndicator")
                        if "ReplaceIndicator" in current_tags:
                            current_tags.remove("ReplaceIndicator")
                        self.tree.item(item_id, tags=tuple(current_tags))
                # 从列表中移除
                self.status_indicators = [(iid, orig, aid, itype) for iid, orig, aid, itype in self.status_indicators if iid != item_id]
            except:
                pass
        
        after_id = self.root.after(15000, remove_indicator)  # 15秒后移除
        
        # 记录指示器信息
        self.status_indicators.append((item_id, original_text, after_id, "new" if is_new else "replace"))

    def show_preview(self, id_str):
        """显示指定ID的预览图片"""
        if not self.storage_dir or id_str not in self.sav_pairs:
            self.preview_label.config(image='', bg="lightgray")
            self.preview_photo = None
            return
        
        main_file = self.sav_pairs[id_str][0]
        if not main_file:
            self.preview_label.config(image='', bg="lightgray", text=self.t("file_missing_text"))
            self.preview_photo = None
            return
        
        main_sav = os.path.join(self.storage_dir, main_file)
        if not os.path.exists(main_sav):
            self.preview_label.config(image='', bg="lightgray", text=self.t("file_not_exist_text"))
            self.preview_photo = None
            return
        
        temp_png = None
        try:
            # 解码主 .sav 获取 PNG 数据
            with open(main_sav, 'r', encoding='utf-8') as f:
                encoded = f.read().strip()
            unquoted = urllib.parse.unquote(encoded)
            data_uri = json.loads(unquoted)
            b64_part = data_uri.split(';base64,', 1)[1]
            img_data = base64.b64decode(b64_part)
            
            # 保存到临时 PNG 文件
            temp_png = tempfile.NamedTemporaryFile(suffix='.png', delete=False).name
            with open(temp_png, 'wb') as f:
                f.write(img_data)
            
            # 加载图片
            img = Image.open(temp_png)
            try:
                # 拉伸到4:3比例(实际游戏内显示也会拉成这样)
                # 使用BILINEAR而不是LANCZOS，速度更快，预览质量足够
                preview_img = img.resize((160, 120), Image.Resampling.BILINEAR)
                photo = ImageTk.PhotoImage(preview_img)
                
                # 更新预览Label
                self.preview_label.config(image=photo, bg=Colors.WHITE, text="")
                self.preview_photo = photo 
            finally:
                # 确保图片对象被正确关闭
                img.close()
                preview_img.close()
        except Exception as e:
            # 出错时显示错误信息
            self.preview_label.config(image='', bg="lightgray", text=self.t("preview_failed"))
            self.preview_photo = None
        finally:
            # 清理临时文件
            if temp_png and os.path.exists(temp_png):
                try:
                    os.remove(temp_png)
                except:
                    pass

    def show_gallery_preview(self):
        """显示画廊预览窗口，按照特定方式排列图片"""
        if not self.storage_dir or not self.ids_data:
            messagebox.showerror(self.t("error"), self.t("select_dir_first"))
            return
        
        # 创建新窗口
        gallery_window = Toplevel(self.root)
        gallery_window.title(self.t("gallery_preview"))
        gallery_window.geometry("1000x700")
        
        # 设置窗口图标
        set_window_icon(gallery_window)
        
        # 创建滚动区域
        canvas = tk.Canvas(gallery_window, bg=Colors.WHITE)
        scrollbar = Scrollbar(gallery_window, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=Colors.WHITE)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # 获取所有图片ID（按照ids_data的顺序）
        image_ids = [item['id'] for item in self.ids_data]
        total_images = len(image_ids)
        
        # 计算需要的行数（每行4列，每列3张图片，所以每行12张图片）
        # 每3行显示12张图片（3行 × 4列）
        rows_per_group = 3
        cols_per_group = 4
        images_per_group = rows_per_group * cols_per_group  # 12
        
        # 计算总组数
        num_groups = (total_images + images_per_group - 1) // images_per_group
        
        # 存储所有图片引用，防止被垃圾回收
        gallery_window.image_refs = []
        # 存储占位符Label的映射 {id_str: (placeholder_label, col_frame)}
        gallery_window.placeholders = {}
        
        # 为每个组创建显示区域
        for group_idx in range(num_groups):
            # 创建组框架
            group_frame = tk.Frame(scrollable_frame, bg=Colors.WHITE)
            group_frame.pack(pady=20, padx=20, fill="both", expand=True)
            
            # 创建3行4列的网格
            for row in range(rows_per_group):
                row_frame = tk.Frame(group_frame, bg=Colors.WHITE)
                row_frame.pack(side="top", pady=5)
                
                for col in range(cols_per_group):
                    # 计算图片索引：对于第row行，第col列，索引 = row + col * 3
                    image_idx = group_idx * images_per_group + row + col * rows_per_group
                    
                    # 创建列框架（用于放置图片和分隔线）
                    col_frame = tk.Frame(row_frame, bg=Colors.WHITE)
                    col_frame.pack(side="left", padx=5)
                    
                    if image_idx < total_images:
                        id_str = image_ids[image_idx]
                        # 先创建占位符，然后异步加载
                        placeholder_container, placeholder_label = self.create_placeholder(col_frame)
                        gallery_window.placeholders[id_str] = (placeholder_container, placeholder_label, col_frame)
                    else:
                        # 空白占位，显示N/A，大小和图片一样（150x112）
                        # 创建一个固定大小的容器，模拟图片大小
                        placeholder_container = tk.Frame(col_frame, bg="lightgray", width=150, height=112)
                        placeholder_container.pack()
                        placeholder_container.pack_propagate(False)
                        
                        # 创建N/A标签，居中显示
                        placeholder_label = tk.Label(placeholder_container, text=self.t("not_available"), 
                                                    bg="lightgray", fg="gray", font=get_cjk_font(14, "bold"),
                                                    anchor="center", justify="center")
                        placeholder_label.place(relx=0.5, rely=0.5, anchor="center")
                        
                        # 在下方添加一个空的文本标签，模拟图片下方的ID显示区域
                        placeholder_id_label = tk.Label(col_frame, text="", bg=Colors.WHITE, font=get_cjk_font(8))
                        placeholder_id_label.pack()
                    
                    # 在第2列和第3列之间添加分隔线（col=1之后，即第2列之后）
                    if col == 1:  # 第2列（索引1）之后
                        separator = tk.Frame(row_frame, width=3, bg="gray", relief="sunken")
                        separator.pack(side="left", fill="y", padx=5)
            
            # 在每页下面显示页面编号
            page_label = tk.Label(group_frame, text=f"{self.t('page')} {group_idx + 1}", 
                                 bg=Colors.WHITE, font=get_cjk_font(12, "bold"), fg="gray")
            page_label.pack(pady=10)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 绑定鼠标滚轮（Windows和Linux）
        def on_mousewheel(event):
            # 检查 canvas 是否还存在
            try:
                if not canvas.winfo_exists():
                    return
            except tk.TclError:
                return
            
            try:
                if event.delta:
                    # Windows
                    canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                else:
                    # Linux
                    if event.num == 4:
                        canvas.yview_scroll(-1, "units")
                    elif event.num == 5:
                        canvas.yview_scroll(1, "units")
            except tk.TclError:
                # canvas 已被销毁，忽略错误
                pass
        
        # Windows
        canvas.bind_all("<MouseWheel>", on_mousewheel)
        # Linux
        canvas.bind_all("<Button-4>", on_mousewheel)
        canvas.bind_all("<Button-5>", on_mousewheel)
        
        # 窗口关闭时解绑全局事件
        def on_window_close():
            try:
                canvas.unbind_all("<MouseWheel>")
                canvas.unbind_all("<Button-4>")
                canvas.unbind_all("<Button-5>")
            except:
                pass
            gallery_window.destroy()
        
        gallery_window.protocol("WM_DELETE_WINDOW", on_window_close)
        
        # 快速获取画廊
        # 异步加载所有图片
        self.load_gallery_images_async(gallery_window, image_ids)
    
    def create_placeholder(self, parent_frame):
        """创建加载中的占位符"""
        placeholder_container = tk.Frame(parent_frame, bg="lightgray", width=150, height=112)
        placeholder_container.pack()
        placeholder_container.pack_propagate(False)
        
        placeholder_label = tk.Label(placeholder_container, text="Loading...", 
                                    bg="lightgray", fg="gray", font=get_cjk_font(10),
                                    anchor="center", justify="center")
        placeholder_label.place(relx=0.5, rely=0.5, anchor="center")
        
        placeholder_id_label = tk.Label(parent_frame, text="", bg=Colors.WHITE, font=get_cjk_font(8))
        placeholder_id_label.pack()
        
        # 返回容器和标签，方便后续销毁
        return placeholder_container, placeholder_label
    
    def load_gallery_images_async(self, gallery_window, image_ids):
        """异步加载所有图片"""
        def load_single_image(id_str):
            """在后台线程中加载单张图片，只处理图片解码，不创建PhotoImage（否则卡死）"""
            # 检查缓存（缓存中存储的是PIL Image对象）
            with self.cache_lock:
                if id_str in self.image_cache:
                    cached_img = self.image_cache[id_str]
                    # 如果缓存的是PhotoImage，需要重新创建（不应该发生，但为了安全）
                    if isinstance(cached_img, Image.Image):
                        return id_str, cached_img
            
            if id_str not in self.sav_pairs:
                return id_str, None
            
            # 优先使用缩略图文件（更小，加载更快）
            thumb_file = self.sav_pairs[id_str][1]
            main_file = self.sav_pairs[id_str][0]
            
            # 选择要加载的文件：优先缩略图，fallback 到主图
            sav_file = None
            if thumb_file:
                thumb_path = os.path.join(self.storage_dir, thumb_file)
                if os.path.exists(thumb_path):
                    sav_file = thumb_path
            
            if not sav_file and main_file:
                main_path = os.path.join(self.storage_dir, main_file)
                if os.path.exists(main_path):
                    sav_file = main_path
            
            if not sav_file:
                return id_str, None
            
            try:
                # 解码 .sav 获取 PNG 数据
                with open(sav_file, 'r', encoding='utf-8') as f:
                    encoded = f.read().strip()
                unquoted = urllib.parse.unquote(encoded)
                data_uri = json.loads(unquoted)
                b64_part = data_uri.split(';base64,', 1)[1]
                img_data = base64.b64decode(b64_part)
                
                # 直接从内存加载图片，避免临时文件
                img = Image.open(BytesIO(img_data))
                try:
                    # 调整大小以适应画廊预览
                    # 使用BILINEAR而不是LANCZOS，速度更快，预览质量足够
                    preview_img = img.resize((150, 112), Image.Resampling.BILINEAR)
                    
                    # 存入缓存（存储PIL Image对象，不是PhotoImage）
                    with self.cache_lock:
                        self.image_cache[id_str] = preview_img.copy()  # 复制一份，避免原图被关闭后缓存失效
                    
                    return id_str, preview_img
                finally:
                    # 确保原图被关闭
                    img.close()
            except Exception as e:
                return id_str, None
        
        def update_image(id_str, pil_image):
            """在主线程中更新UI，在这里创建PhotoImage"""
            if id_str not in gallery_window.placeholders:
                return
            
            placeholder_container, placeholder_label, col_frame = gallery_window.placeholders[id_str]
            
            if pil_image is None:
                # 加载失败，显示错误信息
                placeholder_label.config(text=self.t("preview_failed"), bg="lightgray", fg="red")
                return
            
            try:
                # 在主线程中创建PhotoImage（Tkinter不是线程安全的）
                photo = ImageTk.PhotoImage(pil_image)
                
                # 保存引用
                gallery_window.image_refs.append(photo)
                
                # 移除占位符容器（会自动销毁内部的所有组件）
                placeholder_container.destroy()
                
                # 创建图片Label
                img_label = tk.Label(col_frame, image=photo, bg=Colors.WHITE, text=id_str, 
                                    compound="top", font=get_cjk_font(8))
                img_label.pack()
            except Exception as e:
                # 如果创建PhotoImage失败，显示错误
                placeholder_label.config(text=self.t("preview_failed"), bg="lightgray", fg="red")
        
        # 使用线程池异步加载（非阻塞方式）
        def process_results():
            """在后台线程中处理结果，然后通过after在主线程中更新UI"""
            max_workers = min(8, len(image_ids))  # 最多8个线程
            executor = ThreadPoolExecutor(max_workers=max_workers)
            
            try:
                # 提交所有任务
                future_to_id = {executor.submit(load_single_image, id_str): id_str 
                                for id_str in image_ids}
                
                # 处理完成的任务
                for future in as_completed(future_to_id):
                    try:
                        id_str, pil_image = future.result()
                        # 在主线程中更新UI
                        gallery_window.after(0, update_image, id_str, pil_image)
                    except Exception as e:
                        # 处理单个任务失败的情况
                        pass
            finally:
                # 关闭线程池
                executor.shutdown(wait=False)
        
        # 在后台线程中启动处理
        thread = threading.Thread(target=process_results, daemon=True)
        thread.start()
    
    def load_and_decode(self, sav_path):
        with open(sav_path, 'r', encoding='utf-8') as f:
            encoded = f.read().strip()
        unquoted = urllib.parse.unquote(encoded)
        return json.loads(unquoted)

    def encode_and_save(self, data, sav_path):
        json_str = json.dumps(data)
        encoded = urllib.parse.quote(json_str)
        with open(sav_path, 'w', encoding='utf-8') as f:
            f.write(encoded)

    def replace_selected(self):
        # 获取选中的ID（通过Treeview选择或复选框）
        selected = self.tree.selection()
        if not selected:
            messagebox.showerror(self.t("error"), self.t("select_screenshot"))
            return
        
        item_id = selected[0]
        if item_id not in self.checkbox_vars:
            messagebox.showerror(self.t("error"), self.t("invalid_selection"))
            return
        
        _, id_str = self.checkbox_vars[item_id]

        if id_str not in self.sav_pairs or self.sav_pairs[id_str][0] is None or self.sav_pairs[id_str][1] is None:
            messagebox.showerror(self.t("error"), self.t("file_missing"))
            return

        new_png = filedialog.askopenfilename(title=self.t("select_new_image"))
        if not new_png:
            return

        # 检查文件扩展名
        valid_image_extensions = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.tiff', '.tif', '.ico'}
        file_ext = os.path.splitext(new_png)[1].lower()
        filename = os.path.basename(new_png)
        is_valid_image = file_ext in valid_image_extensions

        main_sav = os.path.join(self.storage_dir, self.sav_pairs[id_str][0])
        thumb_sav = os.path.join(self.storage_dir, self.sav_pairs[id_str][1])
        
        confirmed = False
        
        # 解码主 .sav 获取 PNG 数据
        with open(main_sav, 'r', encoding='utf-8') as f:
            encoded = f.read().strip()
        unquoted = urllib.parse.unquote(encoded)
        data_uri = json.loads(unquoted)
        b64_part = data_uri.split(';base64,', 1)[1]
        img_data = base64.b64decode(b64_part)

        # 保存到临时 PNG 文件
        temp_png = tempfile.NamedTemporaryFile(suffix='.png', delete=False).name
        with open(temp_png, 'wb') as f:
            f.write(img_data)

        # 确认替换窗口
        popup = Toplevel(self.root)
        popup.title(self.t("replace_warning"))
        
        # 设置窗口图标
        set_window_icon(popup)
        
        # 如果不是常规图片格式，在窗口顶端显示警告
        if not is_valid_image:
            warning_label = tk.Label(popup, text=self.t("file_extension_warning", filename=filename), 
                                    fg="#FF57FD", font=get_cjk_font(10), wraplength=600, justify="left")
            warning_label.pack(pady=5, padx=10, anchor="w")
        
        ttk.Label(popup, text=self.t("replace_confirm_text"), font=get_cjk_font(12)).pack(pady=10)
        
        # 图片对比区域
        image_frame = tk.Frame(popup)
        image_frame.pack(pady=10)
        
        # 原图片（左侧）
        orig_img = Image.open(temp_png)
        try:
            # 使用BILINEAR而不是LANCZOS，速度更快，预览质量足够
            orig_preview = orig_img.resize((400, 300), Image.Resampling.BILINEAR)  
            orig_photo = ImageTk.PhotoImage(orig_preview)
            orig_label = Label(image_frame, image=orig_photo)  # 显示图片的Label保持tk.Label
            orig_label.pack(side="left", padx=10)
            popup.orig_photo = orig_photo 
        finally:
            orig_img.close()
            orig_preview.close()
        
        ttk.Label(image_frame, text="→", font=get_cjk_font(24)).pack(side="left", padx=10)
        
        # 新图片（右侧）
        try:
            new_img = Image.open(new_png)
            try:
                # 使用BILINEAR而不是LANCZOS，速度更快，预览质量足够
                new_preview = new_img.resize((400, 300), Image.Resampling.BILINEAR) 
                new_photo = ImageTk.PhotoImage(new_preview)
                new_label = Label(image_frame, image=new_photo)  # 显示图片的Label保持tk.Label
                new_label.pack(side="left", padx=10)
                popup.new_photo = new_photo 
            finally:
                new_img.close()
                new_preview.close()
        except Exception as e:
            # 如果无法打开图片，显示错误信息
            error_label = Label(image_frame, text=self.t("preview_failed"), fg="red", font=get_cjk_font(12))
            error_label.pack(side="left", padx=10)
            popup.new_photo = None

        ttk.Label(popup, text=self.t("replace_confirm_question")).pack(pady=10)

        def yes():
            popup.destroy()
            nonlocal confirmed
            confirmed = True

        def no():
            popup.destroy()
            return  

        ttk.Button(popup, text=self.t("replace_yes"), command=yes).pack(side="left", padx=10)
        ttk.Button(popup, text=self.t("replace_no"), command=no).pack(side="right", padx=10)
        popup.grab_set()
        self.root.wait_window(popup)
        os.remove(temp_png)  # 无论如何清理
        if not confirmed:
            return
        self.replace_sav(main_sav, thumb_sav, new_png)
        messagebox.showinfo(self.t("success"), self.t("replace_success", id=id_str))
        self.load_screenshots()
        self.show_status_indicator(id_str, is_new=False)

    def replace_sav(self, main_sav, thumb_sav, new_png):
        temp_thumb = None
        try:
            # 提取原thumb尺寸
            with open(thumb_sav, 'r', encoding='utf-8') as f:
                encoded = f.read().strip()
            unquoted = urllib.parse.unquote(encoded)
            data_uri = json.loads(unquoted)
            b64_part = data_uri.split(';base64,', 1)[1]
            img_data = base64.b64decode(b64_part)
            temp_thumb = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False).name
            with open(temp_thumb, 'wb') as f:
                f.write(img_data)
            thumb_orig = Image.open(temp_thumb)
            try:
                thumb_size = thumb_orig.size
            finally:
                thumb_orig.close()  

            # 新主sav (PNG)
            with open(new_png, 'rb') as f:
                png_b64 = base64.b64encode(f.read()).decode('utf-8')
            new_main_uri = f"data:image/png;base64,{png_b64}"
            new_main_json = json.dumps(new_main_uri)
            new_main_encoded = urllib.parse.quote(new_main_json)
            with open(main_sav, 'w', encoding='utf-8') as f:
                f.write(new_main_encoded)

            # 新thumb JPEG
            main_img = Image.open(new_png)
            try:
                # 使用BILINEAR而不是LANCZOS，速度更快，缩略图质量足够
                new_thumb = main_img.resize(thumb_size, Image.Resampling.BILINEAR)
                new_thumb = new_thumb.convert('RGB')
                new_thumb.save(temp_thumb, 'JPEG', quality=90, optimize=True)
            finally:
                # 显式关闭图像对象，释放文件句柄
                main_img.close()
                new_thumb.close()
            with open(temp_thumb, 'rb') as f:
                jpeg_b64 = base64.b64encode(f.read()).decode('utf-8')
            new_thumb_uri = f"data:image/jpeg;base64,{jpeg_b64}"
            new_thumb_json = json.dumps(new_thumb_uri)
            new_thumb_encoded = urllib.parse.quote(new_thumb_json)
            with open(thumb_sav, 'w', encoding='utf-8') as f:
                f.write(new_thumb_encoded)
        finally:
            if temp_thumb and os.path.exists(temp_thumb):
                try:
                    os.remove(temp_thumb)
                except:
                    pass

    def add_new(self):
        # 检查是否已选择目录
        if not self.storage_dir:
            messagebox.showerror(self.t("error"), self.t("select_dir_hint"))
            return
        
        new_png = filedialog.askopenfilename(title=self.t("select_new_png"))
        if not new_png:
            return

        # 检查文件扩展名
        valid_image_extensions = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.tiff', '.tif', '.ico'}
        file_ext = os.path.splitext(new_png)[1].lower()
        filename = os.path.basename(new_png)
        is_valid_image = file_ext in valid_image_extensions

        # 检测图片分辨率是否为4:3
        is_4_3_ratio = False
        try:
            if is_valid_image:
                img = Image.open(new_png)
                try:
                    width, height = img.size
                finally:
                    img.close()
                
                # 检查是否是4:3比例（容错±30像素）
                # 如果宽度是w，高度应该是 w * 3 / 4
                expected_height = width * 3 / 4
                if abs(height - expected_height) <= 30:
                    is_4_3_ratio = True
        except Exception:
            # 如果检测不出尺寸，is_4_3_ratio保持为False
            pass

        # 弹出窗口输入 ID 和 date
        popup = Toplevel(self.root)
        popup.title(self.t("add_new_title"))
        
        # 设置窗口图标
        set_window_icon(popup)
        
        # 根据是否有警告消息调整窗口高度
        window_height = 200
        if not is_valid_image:
            window_height += 50
        if not is_4_3_ratio and is_valid_image:
            window_height += 50
        popup.geometry(f"400x{window_height}")

        # 如果不是常规图片格式，在窗口顶端显示警告
        if not is_valid_image:
            warning_label = tk.Label(popup, text=self.t("file_extension_warning", filename=filename), 
                                    fg="#FF57FD", font=get_cjk_font(10), wraplength=380, justify="left")
            warning_label.pack(pady=5, padx=10, anchor="w")
        
        # 如果图片分辨率不是4:3或检测不出，显示警告
        if not is_4_3_ratio and is_valid_image:
            aspect_warning_label = tk.Label(popup, text=self.t("aspect_ratio_warning"), 
                                           fg="#7CA294", font=get_cjk_font(10), wraplength=380, justify="left")
            aspect_warning_label.pack(pady=5, padx=10, anchor="w")

        ttk.Label(popup, text=self.t("id_label")).pack(pady=5)
        id_entry = ttk.Entry(popup, width=50)
        id_entry.pack()

        ttk.Label(popup, text=self.t("date_label")).pack(pady=5)
        date_entry = ttk.Entry(popup, width=50)
        date_entry.pack()

        def confirm():
            new_id = id_entry.get().strip() or ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
            new_date = date_entry.get().strip() or datetime.now().strftime('%Y/%m/%d %H:%M:%S')

            try:
                # 验证 date 格式
                datetime.strptime(new_date, '%Y/%m/%d %H:%M:%S')
            except ValueError:
                messagebox.showerror(self.t("error"), self.t("invalid_date_format"))
                return

            if new_id in self.sav_pairs:
                messagebox.showerror(self.t("error"), self.t("id_exists"))
                return

            # 更新ids
            self.ids_data.append({"id": new_id, "date": new_date})
            ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_ids.sav')
            self.encode_and_save(self.ids_data, ids_path)

            # 更新all_ids
            self.all_ids_data.append(new_id)
            all_ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_all_ids.sav')
            self.encode_and_save(self.all_ids_data, all_ids_path)

            # 生成新sav对
            main_sav_name = f'DevilConnection_photo_{new_id}.sav'
            thumb_sav_name = f'DevilConnection_photo_{new_id}_thumb.sav'
            main_sav = os.path.join(self.storage_dir, main_sav_name)
            thumb_sav = os.path.join(self.storage_dir, thumb_sav_name)
            thumb_size = (1280, 960)
            valid_thumb_found = False
            for pair in self.sav_pairs.values():
                if pair[1] is not None:
                    first_thumb = os.path.join(self.storage_dir, pair[1])
                    with open(first_thumb, 'r', encoding='utf-8') as f:
                        encoded = f.read().strip()
                    unquoted = urllib.parse.unquote(encoded)
                    data_uri = json.loads(unquoted)
                    b64_part = data_uri.split(';base64,', 1)[1]
                    img_data = base64.b64decode(b64_part)
                    temp_thumb_size = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False).name
                    with open(temp_thumb_size, 'wb') as f:
                        f.write(img_data)
                    thumb_orig = Image.open(temp_thumb_size)
                    try:
                        thumb_size = thumb_orig.size
                    finally:
                        thumb_orig.close() 
                    os.remove(temp_thumb_size)
                    valid_thumb_found = True
                    break

            # 生成文件
            temp_thumb = None
            try:
                # 新主sav (PNG)
                with open(new_png, 'rb') as f:
                    png_b64 = base64.b64encode(f.read()).decode('utf-8')
                new_main_uri = f"data:image/png;base64,{png_b64}"
                new_main_json = json.dumps(new_main_uri)
                new_main_encoded = urllib.parse.quote(new_main_json)
                with open(main_sav, 'w', encoding='utf-8') as f:
                    f.write(new_main_encoded)

                # 新thumb JPEG
                try:
                    main_img = Image.open(new_png)
                    try:
                        # 使用BILINEAR而不是LANCZOS，速度更快，缩略图质量足够
                        new_thumb = main_img.resize(thumb_size, Image.Resampling.BILINEAR)
                        new_thumb = new_thumb.convert('RGB')
                    finally:
                        main_img.close() 
                    temp_thumb = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False).name
                    new_thumb.save(temp_thumb, 'JPEG', quality=90, optimize=True)
                except Exception as e:
                    messagebox.showerror(self.t("error"), self.t("preview_failed") + f": {str(e)}")
                    return
                with open(temp_thumb, 'rb') as f:
                    jpeg_b64 = base64.b64encode(f.read()).decode('utf-8')
                new_thumb_uri = f"data:image/jpeg;base64,{jpeg_b64}"
                new_thumb_json = json.dumps(new_thumb_uri)
                new_thumb_encoded = urllib.parse.quote(new_thumb_json)
                with open(thumb_sav, 'w', encoding='utf-8') as f:
                    f.write(new_thumb_encoded)
            finally:
                if temp_thumb and os.path.exists(temp_thumb):
                    try:
                        os.remove(temp_thumb)
                    except:
                        pass

            popup.destroy()
            messagebox.showinfo(self.t("success"), self.t("add_success", id=new_id))
            # 取消所有选择
            for var, _ in self.checkbox_vars.values():
                var.set(False)
            for item_id in self.checkbox_vars.keys():
                self.update_checkbox_display(item_id)
            self.update_select_all_header()
            self.update_button_states()
            self.update_batch_export_button()
            self.load_screenshots()
            self.show_status_indicator(new_id, is_new=True)

        ttk.Button(popup, text=self.t("confirm"), command=confirm).pack(pady=20)
        
    def delete_selected(self):
        # 获取所有选中的ID（通过复选框）
        selected_ids = self.get_selected_ids()
        if not selected_ids:
            messagebox.showerror(self.t("error"), self.t("delete_select_error"))
            return
        
        # 确认删除对话框
        if len(selected_ids) == 1:
            confirm_msg = self.t("delete_confirm_single", id=selected_ids[0])
        else:
            ids_str = ', '.join(selected_ids[:5]) + ('...' if len(selected_ids) > 5 else '')
            confirm_msg = self.t("delete_confirm_multiple", count=len(selected_ids), ids=ids_str)
        
        popup = Toplevel(self.root)
        popup.title(self.t("delete_confirm"))
        
        # 设置窗口图标
        set_window_icon(popup)
        
        ttk.Label(popup, text=confirm_msg).pack(pady=10)

        confirmed = False

        def yes():
            nonlocal confirmed
            confirmed = True
            popup.destroy()

        def no():
            popup.destroy()

        ttk.Button(popup, text=self.t("delete_ok"), command=yes).pack(side="left", padx=10)
        ttk.Button(popup, text=self.t("delete_cancel"), command=no).pack(side="right", padx=10)

        popup.grab_set()
        self.root.wait_window(popup)

        if not confirmed:
            return

        # 删除所有选中的截图
        deleted_count = 0
        for id_str in selected_ids:
            # 删除文件（如果存在）
            pair = self.sav_pairs.get(id_str, [None, None])
            main_path = os.path.join(self.storage_dir, pair[0]) if pair[0] else None
            thumb_path = os.path.join(self.storage_dir, pair[1]) if pair[1] else None
            if main_path and os.path.exists(main_path):
                try:
                    os.remove(main_path)
                    deleted_count += 1
                except:
                    pass
            if thumb_path and os.path.exists(thumb_path):
                try:
                    os.remove(thumb_path)
                except:
                    pass

            # 从索引移除
            self.ids_data = [item for item in self.ids_data if item['id'] != id_str]
            self.all_ids_data = [item for item in self.all_ids_data if item != id_str]

            # 移除本地缓存（如果存在）
            if id_str in self.sav_pairs:
                del self.sav_pairs[id_str]

        # 保存更新
        ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_ids.sav')
        self.encode_and_save(self.ids_data, ids_path)
        all_ids_path = os.path.join(self.storage_dir, 'DevilConnection_photo_all_ids.sav')
        self.encode_and_save(self.all_ids_data, all_ids_path)

        if deleted_count > 0:
            messagebox.showinfo(self.t("success"), self.t("delete_success", count=deleted_count))
        else:
            messagebox.showwarning(self.t("warning"), self.t("delete_warning"))
        
        # 取消所有选择
        for var, _ in self.checkbox_vars.values():
            var.set(False)
        self.update_select_all_header()
        self.update_button_states()
        self.update_batch_export_button()
        self.load_screenshots()
    
    def export_image(self):
        """导出选中的截图"""
        selected = self.tree.selection()
        if not selected:
            messagebox.showerror(self.t("error"), self.t("select_screenshot"))
            return
        
        item_id = selected[0]
        if item_id not in self.checkbox_vars:
            messagebox.showerror(self.t("error"), self.t("invalid_selection"))
            return
        
        _, id_str = self.checkbox_vars[item_id]
        
        if not self.storage_dir or id_str not in self.sav_pairs:
            messagebox.showerror(self.t("error"), self.t("file_not_found"))
            return
        
        main_file = self.sav_pairs[id_str][0]
        if not main_file:
            messagebox.showerror(self.t("error"), self.t("file_missing_text"))
            return
        
        main_sav = os.path.join(self.storage_dir, main_file)
        if not os.path.exists(main_sav):
            messagebox.showerror(self.t("error"), self.t("file_not_exist"))
            return
        
        # 解码图片数据
        try:
            with open(main_sav, 'r', encoding='utf-8') as f:
                encoded = f.read().strip()
            unquoted = urllib.parse.unquote(encoded)
            data_uri = json.loads(unquoted)
            b64_part = data_uri.split(';base64,', 1)[1]
            img_data = base64.b64decode(b64_part)
            
            # 保存到临时PNG文件
            temp_png = tempfile.NamedTemporaryFile(suffix='.png', delete=False).name
            with open(temp_png, 'wb') as f:
                f.write(img_data)
            
            # 打开图片
            img = Image.open(temp_png)
            # 弹出格式选择对话框
            format_window = Toplevel(self.root)
            format_window.title(self.t("select_export_format"))
            format_window.geometry("300x150")
            
            # 设置窗口图标
            set_window_icon(format_window)
            
            selected_format = tk.StringVar(value="png")
            
            ttk.Label(format_window, text=self.t("select_image_format")).pack(pady=10)
            format_frame = tk.Frame(format_window)
            format_frame.pack(pady=10)
            
            ttk.Radiobutton(format_frame, text="PNG", variable=selected_format, value="png").pack(side="left", padx=10)
            ttk.Radiobutton(format_frame, text="JPEG", variable=selected_format, value="jpeg").pack(side="left", padx=10)
            ttk.Radiobutton(format_frame, text="WebP", variable=selected_format, value="webp").pack(side="left", padx=10)
            
            def confirm_export():
                nonlocal img, temp_png
                format_window.destroy()
                format = selected_format.get()
                
                # 获取原始文件名（不含.sav后缀）
                base_name = os.path.splitext(main_file)[0]
                
                # 根据格式设置文件扩展名和保存选项
                if format == "png":
                    filetypes = [("PNG files", "*.png"), ("All files", "*.*")]
                    default_ext = ".png"
                    default_filename = base_name + ".png"
                elif format == "jpeg":
                    filetypes = [("JPEG files", "*.jpg"), ("All files", "*.*")]
                    default_ext = ".jpg"
                    default_filename = base_name + ".jpg"
                else:  # webp
                    filetypes = [("WebP files", "*.webp"), ("All files", "*.*")]
                    default_ext = ".webp"
                    default_filename = base_name + ".webp"
                
                # 弹出保存对话框
                save_path = filedialog.asksaveasfilename(
                    title=self.t("save_image"),
                    defaultextension=default_ext,
                    filetypes=filetypes,
                    initialfile=default_filename
                )
                
                if not save_path:
                    img.close()
                    os.remove(temp_png)
                    return
                
                try:
                    # 根据格式保存图片
                    if format == "png":
                        img.save(save_path, "PNG")
                    elif format == "jpeg":
                        # JPEG需要RGB模式
                        if img.mode != "RGB":
                            img = img.convert("RGB")
                        img.save(save_path, "JPEG", quality=95)
                    else:  # webp
                        img.save(save_path, "WebP", quality=95)
                    
                    messagebox.showinfo(self.t("success"), self.t("export_success", path=save_path))
                except Exception as e:
                    messagebox.showerror(self.t("error"), self.t("save_failed", error=str(e)))
                finally:
                    img.close()
                    if os.path.exists(temp_png):
                        os.remove(temp_png)
            
            def on_close():
                """窗口关闭时的清理函数"""
                nonlocal img, temp_png
                try:
                    img.close()
                except:
                    pass
                try:
                    if os.path.exists(temp_png):
                        os.remove(temp_png)
                except:
                    pass
                format_window.destroy()
            
            ttk.Button(format_window, text=self.t("delete_ok"), command=confirm_export).pack(pady=10)
            format_window.protocol("WM_DELETE_WINDOW", on_close)
            format_window.grab_set()
            
        except Exception as e:
            messagebox.showerror(self.t("error"), self.t("export_failed") + f": {str(e)}")
    
    def batch_export_images(self):
        """批量导出选中的截图到ZIP文件"""
        selected_ids = self.get_selected_ids()
        if not selected_ids:
            messagebox.showerror(self.t("error"), self.t("batch_export_error"))
            return
        
        if not self.storage_dir:
            messagebox.showerror(self.t("error"), self.t("select_dir_hint"))
            return
        
        # 弹出格式选择对话框
        format_window = Toplevel(self.root)
        format_window.title(self.t("select_export_format"))
        format_window.geometry("300x150")
        
        # 设置窗口图标
        set_window_icon(format_window)
        
        selected_format = tk.StringVar(value="png")
        
        ttk.Label(format_window, text=self.t("select_image_format")).pack(pady=10)
        format_frame = tk.Frame(format_window)
        format_frame.pack(pady=10)
        
        ttk.Radiobutton(format_frame, text="PNG", variable=selected_format, value="png").pack(side="left", padx=10)
        ttk.Radiobutton(format_frame, text="JPEG", variable=selected_format, value="jpeg").pack(side="left", padx=10)
        ttk.Radiobutton(format_frame, text="WebP", variable=selected_format, value="webp").pack(side="left", padx=10)
        
        def confirm_batch_export():
            format_window.destroy()
            format = selected_format.get()
            
            # 根据格式设置文件扩展名
            if format == "png":
                default_ext = ".png"
                file_ext = "png"
            elif format == "jpeg":
                default_ext = ".jpg"
                file_ext = "jpg"
            else:  # webp
                default_ext = ".webp"
                file_ext = "webp"
            
            # 弹出保存对话框
            save_path = filedialog.asksaveasfilename(
                title=self.t("save_zip"),
                defaultextension=".zip",
                filetypes=[("ZIP files", "*.zip"), ("All files", "*.*")],
                initialfile="DevilConnectionSSPack.zip"
            )
            
            if not save_path:
                return
            
            try:
                # 创建临时目录存放图片
                temp_dir = tempfile.mkdtemp()
                exported_count = 0
                failed_count = 0
                
                # 导出每张图片
                for id_str in selected_ids:
                    if id_str not in self.sav_pairs:
                        failed_count += 1
                        continue
                    
                    main_file = self.sav_pairs[id_str][0]
                    if not main_file:
                        failed_count += 1
                        continue
                    
                    main_sav = os.path.join(self.storage_dir, main_file)
                    if not os.path.exists(main_sav):
                        failed_count += 1
                        continue
                    
                    try:
                        # 解码图片数据
                        with open(main_sav, 'r', encoding='utf-8') as f:
                            encoded = f.read().strip()
                        unquoted = urllib.parse.unquote(encoded)
                        data_uri = json.loads(unquoted)
                        b64_part = data_uri.split(';base64,', 1)[1]
                        img_data = base64.b64decode(b64_part)
                        
                        # 保存到临时PNG文件
                        temp_png = os.path.join(temp_dir, f"{id_str}.png")
                        with open(temp_png, 'wb') as f:
                            f.write(img_data)
                        
                        # 打开图片并转换格式
                        img = Image.open(temp_png)
                        try:
                            # 根据格式保存
                            output_filename = f"{id_str}.{file_ext}"
                            output_path = os.path.join(temp_dir, output_filename)
                            
                            if format == "png":
                                img.save(output_path, "PNG")
                            elif format == "jpeg":
                                if img.mode != "RGB":
                                    img = img.convert("RGB")
                                img.save(output_path, "JPEG", quality=95)
                            else:  # webp
                                img.save(output_path, "WebP", quality=95)
                        finally:
                            img.close()
                            # 删除临时PNG
                            if os.path.exists(temp_png):
                                try:
                                    os.remove(temp_png)
                                except:
                                    pass
                        exported_count += 1
                    except Exception as e:
                        failed_count += 1
                        continue
                
                # 创建ZIP文件
                if exported_count > 0:
                    with zipfile.ZipFile(save_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        for filename in os.listdir(temp_dir):
                            file_path = os.path.join(temp_dir, filename)
                            if os.path.isfile(file_path):
                                zipf.write(file_path, filename)
                    
                    # 清理临时目录
                    shutil.rmtree(temp_dir)
                    
                    success_msg = self.t("batch_export_success", count=exported_count)
                    if failed_count > 0:
                        success_msg += "\n" + self.t("batch_export_failed", count=failed_count)
                    messagebox.showinfo(self.t("success"), success_msg)
                else:
                    # 清理临时目录
                    shutil.rmtree(temp_dir)
                    messagebox.showerror(self.t("error"), self.t("batch_export_error_all"))
                    
            except Exception as e:
                messagebox.showerror(self.t("error"), self.t("batch_export_fail", error=str(e)))
        
        ttk.Button(format_window, text=self.t("delete_ok"), command=confirm_batch_export).pack(pady=10)
        format_window.grab_set()
        

if __name__ == "__main__":
    root = tk.Tk()
    app = SavTool(root)
    root.mainloop()