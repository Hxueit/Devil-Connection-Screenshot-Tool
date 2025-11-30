import tkinter as tk
from tkinter import ttk, Scrollbar, font as tkfont
import json
import urllib.parse
import os
import platform
import math
import time
from translations import TRANSLATIONS
from utils import set_window_icon
from styles import get_cjk_font, init_styles, Colors, ease_out_cubic, Debouncer
import re
import random
import string


class SaveAnalyzer:
    def __init__(self, parent, storage_dir, translations, current_language):
        self.parent = parent
        self.storage_dir = storage_dir
        self.translations = translations
        self.current_language = current_language
        
        self.window = parent
        
        # 样式已在主程序中通过 init_styles() 初始化
        
        # 性能优化：缓存宽度值，使用防抖机制避免频繁更新
        # 获取窗口宽度并计算2/3作为方框宽度
        self.window.update_idletasks()  # 确保窗口已渲染
        window_width = self.window.winfo_width()
        if window_width <= 1:
            # 如果窗口还未完全渲染，使用默认值，稍后会更新
            window_width = 800
        self._cached_width = int(window_width * 2 / 3)
        self._width_update_pending = False
        
        # 创建顶部控制栏
        control_frame = tk.Frame(self.window, bg=Colors.WHITE)
        control_frame.pack(fill="x", padx=10, pady=5)
        
        # 显示变量名复选框
        self.show_var_names_var = tk.BooleanVar(value=False)
        self.show_var_names_checkbox = ttk.Checkbutton(control_frame, 
                                                  text=self.t("show_var_names"),
                                                  variable=self.show_var_names_var,
                                                  command=self.toggle_var_names_display)
        self.show_var_names_checkbox.pack(side="left", padx=5)
        
        # 存储所有变量名widget的列表
        self.var_name_widgets = []
        
        # Widget 映射系统（用于增量更新）
        self._widget_map = {}  # 存储数据路径到 widget 的映射，格式：{"memory.name": value_widget, ...}
        self._section_map = {}  # 存储 section 名称到 section frame 的映射
        self._stats_widgets = {}  # 存储统计面板中的 widget 引用（canvas、label 等）
        self._is_initialized = False  # 标记是否已完成首次初始化
        self._dynamic_widgets = {}  # 存储动态内容（如缺失结局列表）的 widget 引用
        self._section_title_widgets = {}  # 存储 section 标题和按钮的引用，用于语言切换
        self._hint_labels = []  # 存储提示标签的引用，用于语言切换
        
        # 刷新按钮（右上角）
        self.refresh_button = ttk.Button(control_frame, text=self.t("refresh"), 
                                    command=self.refresh, name="refresh")
        self.refresh_button.pack(side="right", padx=5)
        
        # 创建主容器Frame，用于放置PanedWindow和滚动条
        main_container = tk.Frame(self.window, bg=Colors.WHITE)
        main_container.pack(fill="both", expand=True)
        
        # 创建PanedWindow分割左右区域（隐藏分割线）
        main_paned = tk.PanedWindow(main_container, orient="horizontal", sashwidth=0, bg=Colors.WHITE, sashrelief='flat')
        main_paned.pack(side="left", fill="both", expand=True)
        
        # 左侧2/3区域：可滚动的内容区域
        left_frame = tk.Frame(main_paned, bg=Colors.WHITE)
        main_paned.add(left_frame, width=800, minsize=400)
        
        # 创建滚动区域
        canvas = tk.Canvas(left_frame, bg=Colors.WHITE)
        scrollable_frame = tk.Frame(canvas, bg=Colors.WHITE)
        
        # 设置初始宽度，确保方框从一开始就有正确的宽度
        scrollable_frame.config(width=self._cached_width)
        
        # 性能优化：延迟更新scrollregion，使用防抖机制
        self._scroll_update_pending = False
        self._scroll_retry_count = 0  # 重试计数器，避免无限重试
        def update_scrollregion():
            try:
                # 检查canvas和scrollable_frame是否仍然有效
                if not hasattr(self, 'scrollable_canvas') or not self.scrollable_canvas:
                    self._scroll_update_pending = False
                    self._scroll_retry_count = 0
                    return
                if not hasattr(self, 'scrollable_frame') or not self.scrollable_frame:
                    self._scroll_update_pending = False
                    self._scroll_retry_count = 0
                    return
                
                # 检查canvas是否仍然存在
                try:
                    self.scrollable_canvas.winfo_exists()
                except:
                    self._scroll_update_pending = False
                    self._scroll_retry_count = 0
                    return
                
                # 获取bbox，检查是否有效
                bbox = self.scrollable_canvas.bbox("all")
                if bbox is None:
                    # 如果bbox为None，可能是widget还未完全渲染，延迟重试（最多重试3次）
                    self._scroll_update_pending = False
                    if self._scroll_retry_count < 3:
                        self._scroll_retry_count += 1
                        self.window.after(50, update_scrollregion)
                    else:
                        self._scroll_retry_count = 0
                    return
                
                # 检查bbox是否有效（宽度和高度应该大于0）
                if len(bbox) >= 4:
                    x1, y1, x2, y2 = bbox[:4]
                    if x2 > x1 and y2 > y1:
                        # 只有bbox有效时才更新scrollregion
                        self.scrollable_canvas.configure(scrollregion=bbox)
                        self._scroll_retry_count = 0  # 成功时重置计数器
                    else:
                        # bbox无效，延迟重试（最多重试3次）
                        self._scroll_update_pending = False
                        if self._scroll_retry_count < 3:
                            self._scroll_retry_count += 1
                            self.window.after(50, update_scrollregion)
                        else:
                            self._scroll_retry_count = 0
                        return
                else:
                    # bbox格式不正确，延迟重试（最多重试3次）
                    self._scroll_update_pending = False
                    if self._scroll_retry_count < 3:
                        self._scroll_retry_count += 1
                        self.window.after(50, update_scrollregion)
                    else:
                        self._scroll_retry_count = 0
                    return
            except Exception as e:
                # 记录错误但不抛出，避免影响其他功能
                self._scroll_retry_count = 0
            finally:
                self._scroll_update_pending = False
        
        def on_scrollable_configure(event=None):
            if not self._scroll_update_pending:
                self._scroll_update_pending = True
                self.window.after_idle(update_scrollregion)
        
        # 根据窗口宽度动态更新canvas宽度（固定为窗口宽度的2/3）
        def update_canvas_width(event=None):
            if self._width_update_pending:
                return
            self._width_update_pending = True
            def do_update():
                try:
                    # 检查canvas和scrollable_frame是否仍然有效
                    if not hasattr(self, 'scrollable_canvas') or not self.scrollable_canvas:
                        self._width_update_pending = False
                        return
                    if not hasattr(self, 'scrollable_frame') or not self.scrollable_frame:
                        self._width_update_pending = False
                        return
                    
                    # 检查canvas是否仍然存在
                    try:
                        self.scrollable_canvas.winfo_exists()
                    except:
                        self._width_update_pending = False
                        return
                    
                    # 获取窗口宽度并计算2/3
                    window_width = self.window.winfo_width()
                    if window_width > 1:
                        width = int(window_width * 2 / 3)
                        # 确保宽度至少为1，避免设置为0导致内容不可见
                        if width < 1:
                            width = 1
                        self._cached_width = width
                        canvas.config(width=width)
                        scrollable_frame.config(width=width)
                        
                        # 更新宽度后，延迟更新滚动区域，确保widget已经重新布局
                        self.window.after(10, lambda: on_scrollable_configure())
                except:
                    pass
                finally:
                    self._width_update_pending = False
            self.window.after_idle(do_update)
        
        scrollable_frame.bind("<Configure>", on_scrollable_configure)
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.pack(fill="both", expand=True)
        
        # 存储scrollable_frame和canvas的引用
        self.scrollable_frame = scrollable_frame
        self.scrollable_canvas = canvas
        
        # 加载并解析存档（延迟渲染以提高响应性）
        self.save_data = self.load_save_file()
        if self.save_data:
            self.window.after(10, lambda: self.display_save_info(scrollable_frame, self.save_data))
            # 更新统计面板（使用存储的容器引用）
            self.window.after(10, lambda: self.update_statistics_panel(self._stats_container, self.save_data) if hasattr(self, '_stats_container') else None)
        else:
            error_label = ttk.Label(scrollable_frame, text=self.t("save_file_not_found"), 
                                   font=get_cjk_font(12), foreground="red")
            error_label.pack(pady=20)
            self.save_data = None
        
        # 绑定主窗口的Configure事件，监听窗口大小变化
        def on_window_configure(event=None):
            # 只响应主窗口的大小变化
            if event is None or event.widget == self.window:
                update_canvas_width()
        
        self.window.bind("<Configure>", on_window_configure)
        # 延迟执行以确保窗口已完全渲染
        self.window.after(100, update_canvas_width)
        
        # 右侧1/3区域：显示统计面板（不可滚动）
        right_frame = tk.Frame(main_paned, bg=Colors.WHITE)
        main_paned.add(right_frame, width=400, minsize=200)
        self._right_frame = right_frame
        
        # 性能优化：使用防抖机制设置PanedWindow比例（固定2:1）
        self._paned_update_pending = False
        def set_paned_ratio(event=None):
            if self._paned_update_pending:
                return
            self._paned_update_pending = True
            def do_update():
                try:
                    if main_paned.winfo_width() > 1:
                        total_width = main_paned.winfo_width()
                        left_width = int(total_width * 0.67)
                        main_paned.paneconfig(left_frame, width=left_width)
                except:
                    pass
                self._paned_update_pending = False
            self.window.after_idle(do_update)
        
        # 禁用拖动分割线
        def disable_sash_drag(event):
            return "break"
        
        main_paned.bind("<Button-1>", disable_sash_drag)
        main_paned.bind("<B1-Motion>", disable_sash_drag)
        main_paned.bind("<ButtonRelease-1>", disable_sash_drag)
        
        main_paned.bind("<Configure>", set_paned_ratio)
        set_paned_ratio()
        
        # 创建统计面板（先创建，稍后更新数据）
        self.create_statistics_panel(right_frame)
        
        # 创建查看存档文件按钮（放在右侧面板底部）
        button_frame = tk.Frame(right_frame, bg=Colors.WHITE)
        button_frame.pack(side="bottom", fill="x", pady=(0, 10))
        self.view_file_button = ttk.Button(button_frame, text=self.t("view_save_file"), 
                                           command=self.show_save_file_viewer)
        self.view_file_button.pack(pady=5)
        
        # 创建滚动条，放在主容器最右侧
        scrollbar = Scrollbar(main_container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        
        # 绑定鼠标滚轮（绑定到整个可滚动区域）
        def on_mousewheel(event):
            try:
                if event.delta:
                    canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                else:
                    if event.num == 4:
                        canvas.yview_scroll(-1, "units")
                    elif event.num == 5:
                        canvas.yview_scroll(1, "units")
            except:
                pass
        
        # 递归绑定滚轮事件到widget及其所有子组件
        def bind_mousewheel_recursive(widget):
            """递归绑定滚轮事件到widget及其所有子组件"""
            try:
                widget.bind("<MouseWheel>", on_mousewheel)
                widget.bind("<Button-4>", on_mousewheel)
                widget.bind("<Button-5>", on_mousewheel)
                # 递归绑定所有子组件
                for child in widget.winfo_children():
                    bind_mousewheel_recursive(child)
            except:
                pass
        
        # 绑定到canvas、left_frame和scrollable_frame
        bind_mousewheel_recursive(canvas)
        bind_mousewheel_recursive(left_frame)
        bind_mousewheel_recursive(scrollable_frame)
        
        # 保存函数引用，以便在添加新组件后重新绑定
        self._bind_mousewheel_recursive = bind_mousewheel_recursive
        self._scrollable_frame = scrollable_frame
        self._left_frame = left_frame
    
    def toggle_var_names_display(self):
        """切换变量名显示状态"""
        show = self.show_var_names_var.get()
        for widget_info in self.var_name_widgets:
            widget = widget_info['widget']
            parent = widget_info['parent']
            label_widget = widget_info['label_widget']
            
            if show:
                # 在标签前面显示变量名
                widget.pack(side="left", padx=2, before=label_widget)
            else:
                widget.pack_forget()
    
    def refresh(self):
        """刷新存档分析页面：重新加载存档并更新显示（支持增量更新）"""
        # 更新按钮文本（语言切换时）
        if hasattr(self, 'show_var_names_checkbox'):
            self.show_var_names_checkbox.config(text=self.t("show_var_names"))
        if hasattr(self, 'refresh_button'):
            self.refresh_button.config(text=self.t("refresh"))
        if hasattr(self, 'view_file_button'):
            self.view_file_button.config(text=self.t("view_save_file"))
        
        # 更新所有 section 标题和按钮文本（语言切换时）
        for key, widget_info in list(self._section_title_widgets.items()):
            title_label = widget_info.get('title_label')
            button = widget_info.get('button')
            title_key = widget_info.get('title_key')
            
            # 更新标题文本
            if title_label and title_label.winfo_exists() and title_key:
                try:
                    title_label.config(text=self.t(title_key))
                except:
                    pass  # 如果翻译键不存在，忽略错误
            
            # 更新按钮文本
            if button and button.winfo_exists() and widget_info.get('button_text_key'):
                try:
                    button.config(text=self.t(widget_info['button_text_key']))
                except:
                    pass  # 如果翻译键不存在，忽略错误
        
        # 更新统计面板中的标签文本（语言切换时）
        if hasattr(self, '_stats_widgets'):
            mp_label_title = self._stats_widgets.get('mp_label_title')
            if mp_label_title and mp_label_title.winfo_exists():
                try:
                    mp_label_title.config(text=self.t("total_mp"))
                except:
                    pass
        
        # 更新所有提示标签文本（语言切换时）
        if hasattr(self, '_hint_labels'):
            for hint_info in self._hint_labels:
                label = hint_info.get('label')
                text_key = hint_info.get('text_key')
                if label and label.winfo_exists() and text_key:
                    try:
                        label.config(text=self.t(text_key))
                    except:
                        pass
        
        # 重新加载存档
        self.save_data = self.load_save_file()
        
        if self.save_data:
            # 使用增量更新（display_save_info 内部会判断是否已初始化）
            self.display_save_info(self.scrollable_frame, self.save_data)
            # 更新统计面板（使用存储的容器引用）
            if hasattr(self, '_stats_container') and self._stats_container:
                self.update_statistics_panel(self._stats_container, self.save_data)
        else:
            # 如果存档文件不存在或加载失败
            if self._is_initialized:
                # 已初始化：不销毁现有内容，只显示错误提示（可选）
                # 这里可以选择不显示错误，或者显示一个临时错误提示
                pass
            else:
                # 首次加载失败：清除内容并显示错误信息
                for widget in self.scrollable_frame.winfo_children():
                    widget.destroy()
                error_label = ttk.Label(self.scrollable_frame, text=self.t("save_file_not_found"), 
                                       font=get_cjk_font(12), foreground="red")
                error_label.pack(pady=20)
            self.save_data = None
    
    def t(self, key, **kwargs):
        """翻译函数"""
        text = self.translations[self.current_language].get(key, key)
        if kwargs:
            return text.format(**kwargs)
        return text
    
    def load_save_file(self):
        """加载并解码存档文件"""
        sf_path = os.path.join(self.storage_dir, 'DevilConnection_sf.sav')
        if not os.path.exists(sf_path):
            return None
        
        try:
            with open(sf_path, 'r', encoding='utf-8') as f:
                encoded = f.read().strip()
            unquoted = urllib.parse.unquote(encoded)
            return json.loads(unquoted)
        except Exception as e:
            return None
    
    def create_statistics_panel(self, parent):
        """创建统计面板（贴纸环形图、MP大字、判定小字）"""
        # 使用原生 tkinter 创建主容器
        stats_container = tk.Frame(parent, bg=Colors.WHITE)
        stats_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 存储容器引用以便更新
        self._stats_container = stats_container
        
        # 存储乱码更新定时器的ID（用于取消定时器）
        self._gibberish_update_job = None
        # 存储原始文本内容（用于乱码效果）
        self._original_texts = {}
        # 存储需要显示乱码的widget引用
        self._gibberish_widgets = []
        
        # 显示占位文本（稍后会被 update_statistics_panel 替换）
        placeholder = tk.Label(
            stats_container,
            text=self.t("no_save_data"),
            font=get_cjk_font(12),
            bg=Colors.WHITE
        )
        placeholder.pack(pady=50)
    
    def _draw_progress_ring(self, canvas, center_x, center_y, radius, line_width, 
                           current_percent, progress_color, tag="progress"):
        """绘制进度圆环（支持动画）
        
        Args:
            canvas: tkinter Canvas对象
            center_x, center_y: 圆心坐标
            radius: 半径
            line_width: 线宽
            current_percent: 当前百分比（0-100）
            progress_color: 进度颜色
            tag: 用于标记进度元素的tag，方便清除
        """
        # 清除旧的进度元素
        canvas.delete(tag)
        
        # 计算进度（四舍五入到1%精度）
        rounded_percent = round(current_percent)
        if rounded_percent >= 100:
            num_segments = 99  # 99个1%段，留出1%的空隙（约3.6度）
        else:
            num_segments = rounded_percent  # 每1%一段
        
        # 绘制进度（用多条直线段绘制，避免圆形笔触端点）
        if num_segments > 0:
            # 每1%对应的角度
            angle_per_segment = 360 / 100  # 3.6度
            
            # 多层绘制改善抗锯齿
            # 背景圆环：create_oval(center_x - radius - offset, center_y - radius - offset, 
            #                      center_x + radius + offset, center_y + radius + offset, ...)
            # 椭圆边界框半径 = radius + offset（椭圆中心在center_x, center_y）
            # 进度圆环：create_line的中心线半径应该匹配背景圆环的椭圆边界半径
            # 确保使用完全相同的计算公式：radius + offset
            for offset, width in [(0, line_width), (0.5, line_width - 1), (1, max(1, line_width - 2))]:
                # 使用与背景圆环完全相同的半径计算：radius + offset
                # 这确保进度圆环的中心线与背景圆环的椭圆边界对齐
                offset_radius = radius + offset
                
                # 确保坐标计算完全正确，使用标准的极坐标转换
                # x = center_x + radius * cos(angle)
                # y = center_y - radius * sin(angle)  (注意Y轴向下，所以用减号)
                
                # 绘制每一段（每1%一段）
                for i in range(num_segments):
                    # 计算当前段的起始角度（从顶部90度开始，顺时针）
                    start_angle = 90 - (i * angle_per_segment)
                    end_angle = 90 - ((i + 1) * angle_per_segment)
                    
                    # 转换为弧度
                    start_angle_rad = math.radians(start_angle)
                    end_angle_rad = math.radians(end_angle)
                    
                    # 计算起点和终点坐标
                    start_x = center_x + offset_radius * math.cos(start_angle_rad)
                    start_y = center_y - offset_radius * math.sin(start_angle_rad)
                    end_x = center_x + offset_radius * math.cos(end_angle_rad)
                    end_y = center_y - offset_radius * math.sin(end_angle_rad)
                    
                    # 绘制直线段，添加tag
                    canvas.create_line(
                        start_x, start_y,
                        end_x, end_y,
                        fill=progress_color,
                        width=int(width),
                        capstyle=tk.ROUND,
                        tags=tag
                    )
    
    def update_statistics_panel(self, parent, save_data):
        """更新统计面板内容（支持增量更新）"""
        # 取消之前的乱码更新定时器（如果存在）
        if hasattr(self, '_gibberish_update_job') and self._gibberish_update_job is not None:
            try:
                self.window.after_cancel(self._gibberish_update_job)
            except:
                pass
            self._gibberish_update_job = None
        
        # 初始化乱码相关变量（如果不存在）
        if not hasattr(self, '_gibberish_widgets'):
            self._gibberish_widgets = []
        if not hasattr(self, '_original_texts'):
            self._original_texts = {}
        
        # 如果已初始化，进行增量更新
        if 'sticker_canvas' in self._stats_widgets:
            self._update_statistics_panel_incremental(parent, save_data)
            return
        
        # 首次加载：清除旧内容并创建新widget
        for widget in parent.winfo_children():
            widget.destroy()
        
        # 检查狂信徒线条件
        kill = save_data.get("kill", None)
        killed = save_data.get("killed", None)
        kill_start = save_data.get("killStart", 0)
        
        is_zealot_route = (
            (kill is not None and kill == 1) or
            (killed is not None and killed == 1) or
            (kill_start is not None and kill_start > 0)
        )
        
        # 计算统计数据
        stickers = set(save_data.get("sticker", []))
        total_stickers = 132
        collected_stickers = len(stickers)
        stickers_percent = (collected_stickers / total_stickers * 100) if total_stickers > 0 else 0
        
        whole_total_mp = save_data.get("wholeTotalMP", 0)
        judge_counts = save_data.get("judgeCounts", {})
        perfect = judge_counts.get("perfect", 0)
        good = judge_counts.get("good", 0)
        bad = judge_counts.get("bad", 0)
        
        # 1. 贴纸统计环形图（使用 Canvas 绘制，改善抗锯齿）
        sticker_frame = tk.Frame(parent, bg=Colors.WHITE)
        sticker_frame.pack(pady=(0, 20))
        
        # 创建 Canvas 用于绘制环形图
        canvas_size = 180
        sticker_canvas = tk.Canvas(
            sticker_frame,
            width=canvas_size,
            height=canvas_size,
            bg=Colors.WHITE,
            highlightthickness=0
        )
        sticker_canvas.pack()
        
        # 绘制环形进度图
        center_x, center_y = canvas_size // 2, canvas_size // 2
        radius = 70
        line_width = 20  # 增加线宽，改善抗锯齿
        
        # 背景圆环（灰色，多层绘制改善抗锯齿）
        sticker_canvas.delete("background_ring")  # 清除旧的背景圆环（如果存在）
        for offset, width in [(0, line_width + 2), (0.5, line_width + 1), (1, line_width)]:
            sticker_canvas.create_oval(
                center_x - radius - offset, center_y - radius - offset,
                center_x + radius + offset, center_y + radius + offset,
                outline="#e0e0e0",
                width=int(width),
                tags="background_ring"
            )
        
        # 进度圆环（根据完成度设置颜色，使用更明显的对比）
        # 如果满足狂信徒线条件，强制使用#BF0204颜色
        if is_zealot_route:
            progress_color = "#BF0204"  # 狂信徒线专用颜色
        elif stickers_percent == 100:
            progress_color = "#2E7D32"  # 深绿色，更明显
        elif stickers_percent >= 90:
            progress_color = "#4CAF50"  # 标准绿色
        elif stickers_percent >= 75:
            progress_color = "#FF9800"  # 橙色
        elif stickers_percent >= 50:
            progress_color = "#FFC107"  # 黄色
        else:
            progress_color = "#F44336"  # 红色
        
        # 中心文字：标题（贴纸统计）
        sticker_canvas.create_text(
            center_x, center_y - 20,
            text=self.t('stickers_statistics'),
            font=get_cjk_font(12, "bold"),
            fill="#333333",
            tags="title_text"
        )
        
        # 中心文字：百分比（初始为0%，动画时会更新）
        percent_text_id = sticker_canvas.create_text(
            center_x, center_y + 2,
            text="0.0%",
            font=get_cjk_font(20, "bold"),
            fill="#333333",
            tags="percent_text"
        )
        
        # 动画参数
        target_percent = stickers_percent
        animation_duration = 1.5  # 动画持续时间（秒）
        animation_start_time = time.time()
        
        # 取消之前的动画（如果存在）
        if hasattr(sticker_canvas, '_animation_job'):
            try:
                self.window.after_cancel(sticker_canvas._animation_job)
            except:
                pass
        
        # 在闭包外部保存变量，确保值正确传递
        anim_center_x = center_x
        anim_center_y = center_y
        anim_radius = radius
        anim_line_width = line_width
        anim_progress_color = progress_color
        
        def animate_progress():
            """动画循环函数"""
            try:
                # 检查canvas是否还存在
                if not sticker_canvas.winfo_exists():
                    return
            except tk.TclError:
                return
            
            # 计算动画进度（0.0 到 1.0）
            elapsed = time.time() - animation_start_time
            progress = min(elapsed / animation_duration, 1.0)
            
            # 应用缓动函数
            eased_progress = ease_out_cubic(progress)
            
            # 计算当前百分比
            current_percent = target_percent * eased_progress
            
            # 绘制进度圆环（使用保存的变量）
            self._draw_progress_ring(
                sticker_canvas, anim_center_x, anim_center_y, anim_radius, anim_line_width,
                current_percent, anim_progress_color, tag="progress"
            )
            
            # 更新百分比文字
            sticker_canvas.itemconfig(
                percent_text_id,
                text=f"{current_percent:.1f}%"
            )
            
            # 如果动画未完成，继续下一帧
            if progress < 1.0:
                sticker_canvas._animation_job = self.window.after(16, animate_progress)  # 约60fps
            else:
                # 动画完成，确保最终值精确
                self._draw_progress_ring(
                    sticker_canvas, anim_center_x, anim_center_y, anim_radius, anim_line_width,
                    target_percent, anim_progress_color, tag="progress"
                )
                sticker_canvas.itemconfig(
                    percent_text_id,
                    text=f"{target_percent:.1f}%"
                )
                sticker_canvas._animation_job = None
        
        # 启动动画
        animate_progress()
        
        # 中心文字：数量（X/132）
        sticker_canvas.create_text(
            center_x, center_y + 22,
            text=f"{collected_stickers}/{total_stickers}",
            font=get_cjk_font(11),
            fill="#666666",
            tags="count_text"
        )
        
        # 2. 总MP收集量（大字显示）
        mp_frame = tk.Frame(parent, bg=Colors.WHITE)
        mp_frame.pack(pady=(0, 15))
        
        mp_label_title = tk.Label(
            mp_frame,
            text=self.t("total_mp"),
            font=get_cjk_font(12),
            fg="#666666",
            bg=Colors.WHITE
        )
        mp_label_title.pack()
        
        mp_label_value = tk.Label(
            mp_frame,
            text=f"{whole_total_mp:,}",
            font=get_cjk_font(32, "bold"),
            fg="#2196F3",
            bg=Colors.WHITE
        )
        mp_label_value.pack()
        
        # 3. 判定统计（一行显示）
        judge_frame = tk.Frame(parent, bg=Colors.WHITE)
        judge_frame.pack(pady=(10, 0))
        
        # 创建一行文本，包含三个判定（使用不同颜色）
        judge_canvas = tk.Canvas(
            judge_frame,
            height=25,
            bg=Colors.WHITE,
            highlightthickness=0
        )
        judge_canvas.pack()
        
        # 构建完整文本
        perfect_text = f"{perfect:,}"
        good_text = f"{good:,}"
        bad_text = f"{bad:,}"
        full_text = f"{perfect_text} - {good_text} - {bad_text}"
        
        # 计算文本宽度以便居中
        temp_font = get_cjk_font(10)
        if isinstance(temp_font, tuple):
            font_obj = tkfont.Font(family=temp_font[0], size=temp_font[1])
        else:
            font_obj = tkfont.Font(font=temp_font)
        
        text_width = font_obj.measure(full_text)
        canvas_width = max(250, text_width + 20)  # 至少250宽度
        judge_canvas.config(width=canvas_width)
        
        # 居中绘制文本（分别绘制不同颜色的部分）
        center_x = canvas_width // 2
        current_x = center_x - text_width // 2
        
        # Perfect（#CC6DAE）
        perfect_width = font_obj.measure(perfect_text)
        judge_canvas.create_text(
            current_x + perfect_width // 2, 12,
            text=perfect_text,
            font=get_cjk_font(10),
            fill="#CC6DAE",
            anchor="center"
        )
        current_x += perfect_width + font_obj.measure(" - ")
        
        # Good（#F5CE88）
        good_width = font_obj.measure(good_text)
        judge_canvas.create_text(
            current_x + good_width // 2, 12,
            text=good_text,
            font=get_cjk_font(10),
            fill="#F5CE88",
            anchor="center"
        )
        current_x += good_width + font_obj.measure(" - ")
        
        # Bad（#6DB7AB）
        bad_width = font_obj.measure(bad_text)
        judge_canvas.create_text(
            current_x + bad_width // 2, 12,
            text=bad_text,
            font=get_cjk_font(10),
            fill="#6DB7AB",
            anchor="center"
        )
        
        # 绘制分隔符
        sep_width = font_obj.measure(" - ")
        sep1_x = center_x - text_width // 2 + perfect_width
        sep2_x = sep1_x + sep_width + good_width
        judge_canvas.create_text(sep1_x + sep_width // 2, 12, text=" - ", font=get_cjk_font(10), fill="#666666", anchor="center")
        judge_canvas.create_text(sep2_x + sep_width // 2, 12, text=" - ", font=get_cjk_font(10), fill="#666666", anchor="center")
        
        # 4. 读取并显示 NEO.sav 内容（如果存在）
        neo_label = None
        neo_original_text = None
        neo_sav_path = os.path.join(self.storage_dir, 'NEO.sav')
        if os.path.exists(neo_sav_path):
            try:
                with open(neo_sav_path, 'r', encoding='utf-8') as f:
                    encoded_content = f.read().strip()
                
                # URL解码
                decoded_content = urllib.parse.unquote(encoded_content)
                
                # 根据内容决定显示方式和颜色
                neo_frame = tk.Frame(parent, bg=Colors.WHITE)
                neo_frame.pack(pady=(20, 0))
                
                # 检查是否是特殊内容
                if decoded_content == '"キミたちに永遠の祝福を"':
                    # 使用翻译键 good_neo，颜色 #FFEB9E
                    neo_text = self.t("good_neo")
                    text_color = "#FFEB9E"
                elif decoded_content == '"オマ工に永遠の制裁を"':
                    # 使用翻译键 bad_neo，颜色鲜红
                    neo_text = self.t("bad_neo")
                    text_color = "#FF0000"  # 鲜红色
                else:
                    # 其他情况正常黑字展示
                    neo_text = decoded_content
                    text_color = "#000000"  # 黑色
                
                neo_label = tk.Label(
                    neo_frame,
                    text=neo_text,
                    font=get_cjk_font(14),
                    fg=text_color,
                    bg=Colors.WHITE,
                    wraplength=200  # 限制宽度以便换行
                )
                neo_label.pack()
                neo_original_text = neo_text  # 保存原始文本用于乱码效果
                
                # 如果满足狂信徒线条件，将NEO标签颜色改为深红色
                if is_zealot_route:
                    dark_red_color = "#8b0000"
                    neo_label.config(fg=dark_red_color)
                
            except Exception as e:
                # 如果读取失败，忽略错误
                pass
        
        # 如果满足狂信徒线条件，启动乱码效果
        if is_zealot_route:
            # 保存需要显示乱码的widget和原始文本
            self._gibberish_widgets = []
            self._original_texts = {}
            
            # 狂信徒线使用深红色文字
            dark_red_color = "#8b0000"
            
            # 保存Canvas文字（需要保存Canvas对象、文字ID、位置和样式信息）
            # 获取所有文字ID（按创建顺序）
            all_text_ids = [item for item in sticker_canvas.find_all() if sticker_canvas.type(item) == 'text']
            if len(all_text_ids) >= 3:
                # 饼状图中心文字 - 标题
                self._gibberish_widgets.append({
                    'type': 'canvas_text',
                    'canvas': sticker_canvas,
                    'text_id': all_text_ids[-3],
                    'x': center_x,
                    'y': center_y - 20,
                    'font': get_cjk_font(12, "bold"),
                    'fill': dark_red_color,
                    'anchor': 'center',
                    'tag': 'title_text'
                })
                self._original_texts[len(self._gibberish_widgets) - 1] = self.t('stickers_statistics')
                
                # 饼状图中心文字 - 百分比
                self._gibberish_widgets.append({
                    'type': 'canvas_text',
                    'canvas': sticker_canvas,
                    'text_id': all_text_ids[-2],
                    'x': center_x,
                    'y': center_y + 2,
                    'font': get_cjk_font(20, "bold"),
                    'fill': dark_red_color,
                    'anchor': 'center',
                    'tag': 'percent_text'
                })
                self._original_texts[len(self._gibberish_widgets) - 1] = f"{stickers_percent:.1f}%"
                
                # 饼状图中心文字 - 数量
                self._gibberish_widgets.append({
                    'type': 'canvas_text',
                    'canvas': sticker_canvas,
                    'text_id': all_text_ids[-1],
                    'x': center_x,
                    'y': center_y + 22,
                    'font': get_cjk_font(11),
                    'fill': dark_red_color,
                    'anchor': 'center',
                    'tag': 'count_text'
                })
                self._original_texts[len(self._gibberish_widgets) - 1] = f"{collected_stickers}/{total_stickers}"
            
            # 保存Label文字
            self._gibberish_widgets.append({
                'type': 'tk_label',
                'widget': mp_label_title
            })
            self._original_texts[len(self._gibberish_widgets) - 1] = self.t("total_mp")
            
            self._gibberish_widgets.append({
                'type': 'tk_label',
                'widget': mp_label_value
            })
            self._original_texts[len(self._gibberish_widgets) - 1] = f"{whole_total_mp:,}"
            
            # 保存判定统计Canvas文字（需要保存每个文字的位置信息）
            # 由于判定统计是分别绘制的，我们需要保存整个Canvas和重新绘制的信息
            self._gibberish_widgets.append({
                'type': 'judge_canvas',
                'canvas': judge_canvas,
                'perfect': perfect,
                'good': good,
                'bad': bad,
                'canvas_width': canvas_width,
                'font_obj': font_obj,
                'center_x': center_x,
                'text_width': text_width
            })
            self._original_texts[len(self._gibberish_widgets) - 1] = full_text
            
            # 如果NEO标签存在，也加入到乱码效果中
            if neo_label is not None and neo_original_text is not None:
                self._gibberish_widgets.append({
                    'type': 'tk_label',
                    'widget': neo_label
                })
                self._original_texts[len(self._gibberish_widgets) - 1] = neo_original_text
            
            # 启动乱码更新定时器
            self._update_gibberish_texts()
        
        # 存储widget引用以便后续增量更新
        self._stats_widgets['sticker_canvas'] = sticker_canvas
        self._stats_widgets['sticker_frame'] = sticker_frame
        self._stats_widgets['mp_label_title'] = mp_label_title
        self._stats_widgets['mp_label_value'] = mp_label_value
        self._stats_widgets['judge_canvas'] = judge_canvas
        self._stats_widgets['judge_frame'] = judge_frame
        if neo_label is not None:
            self._stats_widgets['neo_label'] = neo_label
            self._stats_widgets['neo_frame'] = neo_frame
        self._stats_widgets['percent_text_id'] = percent_text_id
        self._stats_widgets['canvas_size'] = canvas_size
        self._stats_widgets['center_x'] = center_x
        self._stats_widgets['center_y'] = center_y
        self._stats_widgets['radius'] = radius
        self._stats_widgets['line_width'] = line_width
    
    def _update_statistics_panel_incremental(self, parent, save_data):
        """增量更新统计面板内容"""
        # 检查狂信徒线条件
        kill = save_data.get("kill", None)
        killed = save_data.get("killed", None)
        kill_start = save_data.get("killStart", 0)
        
        is_zealot_route = (
            (kill is not None and kill == 1) or
            (killed is not None and killed == 1) or
            (kill_start is not None and kill_start > 0)
        )
        
        # 计算统计数据
        stickers = set(save_data.get("sticker", []))
        total_stickers = 132
        collected_stickers = len(stickers)
        stickers_percent = (collected_stickers / total_stickers * 100) if total_stickers > 0 else 0
        
        whole_total_mp = save_data.get("wholeTotalMP", 0)
        judge_counts = save_data.get("judgeCounts", {})
        perfect = judge_counts.get("perfect", 0)
        good = judge_counts.get("good", 0)
        bad = judge_counts.get("bad", 0)
        
        # 获取存储的widget引用
        sticker_canvas = self._stats_widgets.get('sticker_canvas')
        mp_label_value = self._stats_widgets.get('mp_label_value')
        judge_canvas = self._stats_widgets.get('judge_canvas')
        percent_text_id = self._stats_widgets.get('percent_text_id')
        radius = self._stats_widgets.get('radius', 70)
        line_width = self._stats_widgets.get('line_width', 20)
        
        if not sticker_canvas or not sticker_canvas.winfo_exists():
            # 如果widget已被销毁，重新创建
            self._stats_widgets.clear()
            self.update_statistics_panel(parent, save_data)
            return
        
        # 从canvas的实际尺寸重新计算center_x和center_y（确保位置正确）
        canvas_width = sticker_canvas.winfo_width()
        canvas_height = sticker_canvas.winfo_height()
        if canvas_width <= 1 or canvas_height <= 1:
            # 如果canvas还未完全渲染，使用存储的值
            canvas_width = self._stats_widgets.get('canvas_size', 180)
            canvas_height = canvas_width
        center_x = canvas_width // 2
        center_y = canvas_height // 2
        
        # 确定进度颜色
        if is_zealot_route:
            progress_color = "#BF0204"
        elif stickers_percent == 100:
            progress_color = "#2E7D32"
        elif stickers_percent >= 90:
            progress_color = "#4CAF50"
        elif stickers_percent >= 75:
            progress_color = "#FF9800"
        elif stickers_percent >= 50:
            progress_color = "#FFC107"
        else:
            progress_color = "#F44336"
        
        # 更新贴纸环形图
        # 清除旧的进度圆环和所有文字
        sticker_canvas.delete("progress")
        sticker_canvas.delete("title_text")  # 删除"贴纸统计"标题
        sticker_canvas.delete("percent_text")  # 删除百分比文字
        sticker_canvas.delete("count_text")  # 删除"X/132"数量文字
        
        # 检查并重新绘制背景圆环（如果不存在或位置不正确）
        background_exists = len(sticker_canvas.find_withtag("background_ring")) > 0
        if not background_exists:
            # 重新绘制背景圆环（确保位置正确）
            for offset, width in [(0, line_width + 2), (0.5, line_width + 1), (1, line_width)]:
                sticker_canvas.create_oval(
                    center_x - radius - offset, center_y - radius - offset,
                    center_x + radius + offset, center_y + radius + offset,
                    outline="#e0e0e0",
                    width=int(width),
                    tags="background_ring"
                )
        
        # 重新创建标题文字（贴纸统计）
        sticker_canvas.create_text(
            center_x, center_y - 20,
            text=self.t('stickers_statistics'),
            font=get_cjk_font(12, "bold"),
            fill="#333333",
            tags="title_text"
        )
        
        # 重新创建百分比文字
        percent_text_id = sticker_canvas.create_text(
            center_x, center_y + 2,
            text="0.0%",
            font=get_cjk_font(20, "bold"),
            fill="#333333",
            tags="percent_text"
        )
        self._stats_widgets['percent_text_id'] = percent_text_id
        
        # 动画参数
        target_percent = stickers_percent
        animation_duration = 1.5
        animation_start_time = time.time()
        
        # 取消之前的动画
        if hasattr(sticker_canvas, '_animation_job'):
            try:
                self.window.after_cancel(sticker_canvas._animation_job)
            except:
                pass
        
        anim_center_x = center_x
        anim_center_y = center_y
        anim_radius = radius
        anim_line_width = line_width
        anim_progress_color = progress_color
        
        def animate_progress():
            try:
                if not sticker_canvas.winfo_exists():
                    return
            except tk.TclError:
                return
            
            elapsed = time.time() - animation_start_time
            progress = min(elapsed / animation_duration, 1.0)
            eased_progress = ease_out_cubic(progress)
            current_percent = target_percent * eased_progress
            
            self._draw_progress_ring(
                sticker_canvas, anim_center_x, anim_center_y, anim_radius, anim_line_width,
                current_percent, anim_progress_color, tag="progress"
            )
            
            sticker_canvas.itemconfig(
                percent_text_id,
                text=f"{current_percent:.1f}%"
            )
            
            if progress < 1.0:
                sticker_canvas._animation_job = self.window.after(16, animate_progress)
            else:
                self._draw_progress_ring(
                    sticker_canvas, anim_center_x, anim_center_y, anim_radius, anim_line_width,
                    target_percent, anim_progress_color, tag="progress"
                )
                sticker_canvas.itemconfig(
                    percent_text_id,
                    text=f"{target_percent:.1f}%"
                )
                sticker_canvas._animation_job = None
        
        animate_progress()
        
        # 更新数量文字（X/132）
        # 删除旧的文字
        sticker_canvas.delete("count_text")
        sticker_canvas.create_text(
            center_x, center_y + 22,
            text=f"{collected_stickers}/{total_stickers}",
            font=get_cjk_font(11),
            fill="#666666",
            tags="count_text"
        )
        
        # 更新MP标签
        if mp_label_value and mp_label_value.winfo_exists():
            mp_label_value.config(text=f"{whole_total_mp:,}")
        
        # 更新判定统计Canvas
        if judge_canvas and judge_canvas.winfo_exists():
            judge_canvas.delete("all")
            
            perfect_text = f"{perfect:,}"
            good_text = f"{good:,}"
            bad_text = f"{bad:,}"
            full_text = f"{perfect_text} - {good_text} - {bad_text}"
            
            temp_font = get_cjk_font(10)
            if isinstance(temp_font, tuple):
                font_obj = tkfont.Font(family=temp_font[0], size=temp_font[1])
            else:
                font_obj = tkfont.Font(font=temp_font)
            
            text_width = font_obj.measure(full_text)
            canvas_width = max(250, text_width + 20)
            judge_canvas.config(width=canvas_width)
            
            center_x_judge = canvas_width // 2
            current_x = center_x_judge - text_width // 2
            
            perfect_width = font_obj.measure(perfect_text)
            judge_canvas.create_text(
                current_x + perfect_width // 2, 12,
                text=perfect_text,
                font=get_cjk_font(10),
                fill="#CC6DAE",
                anchor="center"
            )
            current_x += perfect_width + font_obj.measure(" - ")
            
            good_width = font_obj.measure(good_text)
            judge_canvas.create_text(
                current_x + good_width // 2, 12,
                text=good_text,
                font=get_cjk_font(10),
                fill="#F5CE88",
                anchor="center"
            )
            current_x += good_width + font_obj.measure(" - ")
            
            bad_width = font_obj.measure(bad_text)
            judge_canvas.create_text(
                current_x + bad_width // 2, 12,
                text=bad_text,
                font=get_cjk_font(10),
                fill="#6DB7AB",
                anchor="center"
            )
            
            sep_width = font_obj.measure(" - ")
            sep1_x = center_x_judge - text_width // 2 + perfect_width
            sep2_x = sep1_x + sep_width + good_width
            judge_canvas.create_text(sep1_x + sep_width // 2, 12, text=" - ", font=get_cjk_font(10), fill="#666666", anchor="center")
            judge_canvas.create_text(sep2_x + sep_width // 2, 12, text=" - ", font=get_cjk_font(10), fill="#666666", anchor="center")
        
        # 更新NEO标签（如果存在）
        neo_sav_path = os.path.join(self.storage_dir, 'NEO.sav')
        neo_label = self._stats_widgets.get('neo_label')
        neo_text = None
        if os.path.exists(neo_sav_path):
            try:
                with open(neo_sav_path, 'r', encoding='utf-8') as f:
                    encoded_content = f.read().strip()
                
                decoded_content = urllib.parse.unquote(encoded_content)
                
                if decoded_content == '"キミたちに永遠の祝福を"':
                    neo_text = self.t("good_neo")
                    text_color = "#FFEB9E"
                elif decoded_content == '"オマ工に永遠の制裁を"':
                    neo_text = self.t("bad_neo")
                    text_color = "#FF0000"
                else:
                    neo_text = decoded_content
                    text_color = "#000000"
                
                if neo_label and neo_label.winfo_exists():
                    neo_label.config(text=neo_text, fg=text_color)
            except:
                pass
        
        # 如果满足狂信徒线条件，启动乱码效果（复用原有逻辑）
        if is_zealot_route:
            # 重新初始化乱码相关变量
            self._gibberish_widgets = []
            self._original_texts = {}
        else:
            # 不满足狂信徒线条件时，停止乱码效果并清除相关变量
            if hasattr(self, '_gibberish_update_job') and self._gibberish_update_job is not None:
                try:
                    self.window.after_cancel(self._gibberish_update_job)
                except:
                    pass
                self._gibberish_update_job = None
            
            # 清理乱码效果创建的canvas文字（在清除变量之前）
            if hasattr(self, '_gibberish_widgets') and self._gibberish_widgets:
                for widget_info in self._gibberish_widgets:
                    try:
                        if widget_info['type'] == 'canvas_text':
                            canvas = widget_info.get('canvas')
                            text_id = widget_info.get('text_id')
                            if canvas and text_id:
                                canvas.delete(text_id)
                    except:
                        pass
            
            self._gibberish_widgets = []
            self._original_texts = {}
        
        if is_zealot_route:
            # 狂信徒线使用深红色文字
            dark_red_color = "#8b0000"
            
            # 保存Canvas文字
            all_text_ids = [item for item in sticker_canvas.find_all() if sticker_canvas.type(item) == 'text']
            if len(all_text_ids) >= 3:
                self._gibberish_widgets.append({
                    'type': 'canvas_text',
                    'canvas': sticker_canvas,
                    'text_id': all_text_ids[-3],
                    'x': center_x,
                    'y': center_y - 20,
                    'font': get_cjk_font(12, "bold"),
                    'fill': dark_red_color,
                    'anchor': 'center',
                    'tag': 'title_text'
                })
                self._original_texts[len(self._gibberish_widgets) - 1] = self.t('stickers_statistics')
                
                self._gibberish_widgets.append({
                    'type': 'canvas_text',
                    'canvas': sticker_canvas,
                    'text_id': all_text_ids[-2],
                    'x': center_x,
                    'y': center_y + 2,
                    'font': get_cjk_font(20, "bold"),
                    'fill': dark_red_color,
                    'anchor': 'center',
                    'tag': 'percent_text'
                })
                self._original_texts[len(self._gibberish_widgets) - 1] = f"{stickers_percent:.1f}%"
                
                self._gibberish_widgets.append({
                    'type': 'canvas_text',
                    'canvas': sticker_canvas,
                    'text_id': all_text_ids[-1],
                    'x': center_x,
                    'y': center_y + 22,
                    'font': get_cjk_font(11),
                    'fill': dark_red_color,
                    'anchor': 'center',
                    'tag': 'count_text'
                })
                self._original_texts[len(self._gibberish_widgets) - 1] = f"{collected_stickers}/{total_stickers}"
            
            # 保存Label文字
            mp_label_title = self._stats_widgets.get('mp_label_title')
            if mp_label_title:
                self._gibberish_widgets.append({
                    'type': 'tk_label',
                    'widget': mp_label_title
                })
                self._original_texts[len(self._gibberish_widgets) - 1] = self.t("total_mp")
            
            if mp_label_value:
                self._gibberish_widgets.append({
                    'type': 'tk_label',
                    'widget': mp_label_value
                })
                self._original_texts[len(self._gibberish_widgets) - 1] = f"{whole_total_mp:,}"
            
            # 保存判定统计Canvas
            if judge_canvas:
                temp_font = get_cjk_font(10)
                if isinstance(temp_font, tuple):
                    font_obj = tkfont.Font(family=temp_font[0], size=temp_font[1])
                else:
                    font_obj = tkfont.Font(font=temp_font)
                
                full_text = f"{perfect:,} - {good:,} - {bad:,}"
                text_width = font_obj.measure(full_text)
                canvas_width = max(250, text_width + 20)
                
                self._gibberish_widgets.append({
                    'type': 'judge_canvas',
                    'canvas': judge_canvas,
                    'perfect': perfect,
                    'good': good,
                    'bad': bad,
                    'canvas_width': canvas_width,
                    'font_obj': font_obj,
                    'center_x': canvas_width // 2,
                    'text_width': text_width
                })
                self._original_texts[len(self._gibberish_widgets) - 1] = full_text
            
            # 如果NEO标签存在
            if neo_label and neo_label.winfo_exists() and neo_text:
                self._gibberish_widgets.append({
                    'type': 'tk_label',
                    'widget': neo_label
                })
                self._original_texts[len(self._gibberish_widgets) - 1] = neo_text
            
            # 启动乱码更新定时器
            self._update_gibberish_texts()
    
    def _generate_gibberish_text(self, original_text):
        """生成乱码文本，将20-50%的字符替换为随机乱码"""
        if not original_text:
            return original_text
        
        # 随机选择替换比例（20-50%）
        replace_ratio = random.uniform(0.2, 0.5)
        num_replace = max(1, int(len(original_text) * replace_ratio))
        
        # 随机选择要替换的位置
        positions_to_replace = random.sample(range(len(original_text)), min(num_replace, len(original_text)))
        
        # 生成乱码文本
        result = list(original_text)
        printable_chars = string.printable  # 包含所有可打印字符
        
        for pos in positions_to_replace:
            # 替换为随机可打印字符
            result[pos] = random.choice(printable_chars)
        
        return ''.join(result)
    
    def _update_gibberish_texts(self):
        """更新所有文字为乱码效果"""
        if not hasattr(self, '_gibberish_widgets') or not self._gibberish_widgets:
            return
        
        for idx, widget_info in enumerate(self._gibberish_widgets):
            if idx not in self._original_texts:
                continue
            
            original_text = self._original_texts[idx]
            gibberish_text = self._generate_gibberish_text(original_text)
            
            try:
                if widget_info['type'] == 'canvas_text':
                    # 更新Canvas文字：删除旧文字，创建新文字
                    canvas = widget_info['canvas']
                    try:
                        canvas.delete(widget_info['text_id'])
                    except:
                        pass
                    # 使用保存的tag（以便清理时能被正确删除）
                    text_tag = widget_info.get('tag', 'gibberish_text')
                    
                    # 创建新文字（带tags）
                    new_text_id = canvas.create_text(
                        widget_info['x'],
                        widget_info['y'],
                        text=gibberish_text,
                        font=widget_info['font'],
                        fill=widget_info['fill'],
                        anchor=widget_info['anchor'],
                        tags=text_tag
                    )
                    widget_info['text_id'] = new_text_id
                
                elif widget_info['type'] == 'tk_label':
                    # 更新Label文字，在狂信徒线条件下使用深红色
                    dark_red_color = "#8b0000"
                    widget_info['widget'].config(text=gibberish_text, fg=dark_red_color)
                
                elif widget_info['type'] == 'judge_canvas':
                    # 重新绘制判定统计Canvas
                    canvas = widget_info['canvas']
                    canvas.delete("all")  # 清除所有内容
                    
                    # 生成乱码文本
                    perfect_text = self._generate_gibberish_text(f"{widget_info['perfect']:,}")
                    good_text = self._generate_gibberish_text(f"{widget_info['good']:,}")
                    bad_text = self._generate_gibberish_text(f"{widget_info['bad']:,}")
                    full_text = f"{perfect_text} - {good_text} - {bad_text}"
                    
                    # 重新计算位置
                    font_obj = widget_info['font_obj']
                    text_width = font_obj.measure(full_text)
                    center_x = widget_info['canvas_width'] // 2
                    current_x = center_x - text_width // 2
                    
                    # 狂信徒线使用深红色文字
                    dark_red_color = "#8b0000"
                    
                    # 重新绘制文本
                    perfect_width = font_obj.measure(perfect_text)
                    canvas.create_text(
                        current_x + perfect_width // 2, 12,
                        text=perfect_text,
                        font=get_cjk_font(10),
                        fill=dark_red_color,
                        anchor="center"
                    )
                    current_x += perfect_width + font_obj.measure(" - ")
                    
                    good_width = font_obj.measure(good_text)
                    canvas.create_text(
                        current_x + good_width // 2, 12,
                        text=good_text,
                        font=get_cjk_font(10),
                        fill=dark_red_color,
                        anchor="center"
                    )
                    current_x += good_width + font_obj.measure(" - ")
                    
                    bad_width = font_obj.measure(bad_text)
                    canvas.create_text(
                        current_x + bad_width // 2, 12,
                        text=bad_text,
                        font=get_cjk_font(10),
                        fill=dark_red_color,
                        anchor="center"
                    )
                    
                    # 重新绘制分隔符
                    sep_width = font_obj.measure(" - ")
                    sep1_x = center_x - text_width // 2 + perfect_width
                    sep2_x = sep1_x + sep_width + good_width
                    canvas.create_text(sep1_x + sep_width // 2, 12, text=" - ", font=get_cjk_font(10), fill=dark_red_color, anchor="center")
                    canvas.create_text(sep2_x + sep_width // 2, 12, text=" - ", font=get_cjk_font(10), fill=dark_red_color, anchor="center")
            except Exception as e:
                # 如果widget已被销毁，忽略错误
                pass
        
        # 150ms后再次更新
        self._gibberish_update_job = self.window.after(150, self._update_gibberish_texts)
    
    def create_section(self, parent, title, bg_color=None, text_color=None, title_key=None):
        """创建带标题的分区
        
        Args:
            parent: 父容器
            title: 标题文本（已翻译）
            bg_color: 背景颜色（可选，默认为白色）
            text_color: 文字颜色（可选，默认为黑色）
            title_key: 标题的翻译键（可选，用于语言切换时更新）
        
        Returns:
            content_frame - 用于添加内容的frame
        """
        if bg_color is None:
            bg_color = Colors.WHITE
        if text_color is None:
            text_color = "#000000"
        
        section_frame = tk.Frame(parent, bg=bg_color, relief="ridge", borderwidth=2)
        section_frame.pack(fill="x", padx=10, pady=5)
        
        # 使用缓存的宽度计算标题换行长度
        def get_title_wraplength():
            return int(self._cached_width * 0.9)
        
        title_label = ttk.Label(section_frame, text=title, font=get_cjk_font(12, "bold"), 
                               wraplength=get_title_wraplength(), justify="left",
                               foreground=text_color)
        title_label.pack(anchor="w", padx=5, pady=5)
        
        content_frame = tk.Frame(section_frame, bg=bg_color)
        content_frame.pack(fill="x", padx=10, pady=5)
        
        # 存储section_frame引用以便后续访问
        content_frame._section_frame = section_frame
        
        # 保存标题的引用，用于语言切换
        # 使用 title_key 作为 key（如果提供），否则使用 title
        key = title_key if title_key else title
        self._section_title_widgets[key] = {
            'title_label': title_label,
            'button': None,
            'button_text_key': None,
            'title_key': title_key
        }
        
        return content_frame
    
    def create_section_with_button(self, parent, title, button_text, button_command=None, title_key=None):
        """创建带标题和按钮的分区
        
        Args:
            parent: 父容器
            title: 标题文本（已翻译）
            button_text: 按钮文本（已翻译）
            button_command: 按钮命令
            title_key: 标题的翻译键（可选，用于语言切换时更新）
        """
        section_frame = tk.Frame(parent, bg=Colors.WHITE, relief="ridge", borderwidth=2)
        section_frame.pack(fill="x", padx=10, pady=5)
        
        # 标题和按钮在同一行
        header_frame = tk.Frame(section_frame, bg=Colors.WHITE)
        header_frame.pack(fill="x", padx=5, pady=5)
        
        # 使用缓存的宽度计算标题换行长度
        def get_title_wraplength():
            return int(self._cached_width * 0.6)
        
        title_label = ttk.Label(header_frame, text=title, font=get_cjk_font(12, "bold"), 
                               wraplength=get_title_wraplength(), justify="left")
        title_label.pack(side="left", padx=5)
        
        button = None
        if button_text:
            button = ttk.Button(header_frame, text=button_text, command=button_command if button_command else lambda: None)
            button.pack(side="right", padx=5)
        
        content_frame = tk.Frame(section_frame, bg=Colors.WHITE)
        content_frame.pack(fill="x", padx=10, pady=5)
        
        # 保存标题和按钮的引用，用于语言切换
        # 使用 title_key 作为 key（如果提供），否则使用 title
        key = title_key if title_key else title
        self._section_title_widgets[key] = {
            'title_label': title_label,
            'button': button,
            'button_text_key': 'view_requirements' if button_text else None,
            'title_key': title_key
        }
        
        return content_frame
    
    def add_info_line(self, parent, label, value, var_name=None, widget_key=None, text_color=None):
        """添加信息行
        
        Args:
            parent: 父容器
            label: 标签文本
            value: 值
            var_name: 变量名（可选）
            widget_key: widget 标识键，用于增量更新（可选）
            text_color: 文字颜色（可选，如果未提供则从父容器背景色推断）
        
        Returns:
            value_widget: 值 widget 的引用
        """
        # 如果提供了 widget_key 且 widget 已存在，进行增量更新
        if widget_key and widget_key in self._widget_map:
            widget_info = self._widget_map[widget_key]
            value_widget = widget_info.get('value_widget')
            label_widget = widget_info.get('label_widget')
            
            if value_widget and value_widget.winfo_exists():
                # 更新值文本
                value_widget.config(text=str(value))
                # 更新标签文本（语言切换时可能需要）
                if label_widget:
                    label_widget.config(text=label + ":")
                return value_widget
        
        # 如果没有指定文字颜色，使用默认颜色
        # 注意：狂信徒区域现在使用白色背景和深红色文字，已通过text_color参数显式传递
        
        # 创建新的 widget
        parent_bg = parent.cget("bg") if hasattr(parent, "cget") else Colors.WHITE
        line_frame = tk.Frame(parent, bg=parent_bg)
        line_frame.pack(fill="x", padx=5, pady=2)
        
        label_widget = ttk.Label(line_frame, text=label + ":", font=get_cjk_font(10), 
                                wraplength=200, foreground=text_color if text_color else None)
        label_widget.pack(side="left", padx=5)
        
        # 如果有变量名，在冒号前面显示灰色的变量名
        var_name_widget = None
        if var_name:
            var_name_widget = ttk.Label(line_frame, text=f"[{var_name}]", 
                                       font=get_cjk_font(9), 
                                       foreground="gray",
                                       wraplength=150)
            # 默认隐藏，只有勾选复选框时才显示
            if self.show_var_names_var.get():
                var_name_widget.pack(side="left", padx=2, before=label_widget)
            # 存储widget信息以便后续切换显示
            self.var_name_widgets.append({
                'widget': var_name_widget,
                'parent': line_frame,
                'label_widget': label_widget
            })
        
        wraplength = int(self._cached_width * 0.7)
        
        value_widget = ttk.Label(line_frame, text=str(value), font=get_cjk_font(10), 
                                wraplength=wraplength, justify="left",
                                foreground=text_color if text_color else None)
        value_widget.pack(side="left", padx=5, fill="x", expand=True)
        
        # 如果提供了 widget_key，存储到映射中
        if widget_key:
            self._widget_map[widget_key] = {
                'value_widget': value_widget,
                'label_widget': label_widget,
                'line_frame': line_frame,
                'var_name_widget': var_name_widget
            }
        
        return value_widget
    
    def add_list_info(self, parent, label, items):
        """添加列表信息，显示完整列表"""
        line_frame = tk.Frame(parent, bg=Colors.WHITE)
        line_frame.pack(fill="x", padx=5, pady=2)
        
        label_widget = ttk.Label(line_frame, text=label + ":", font=get_cjk_font(10), wraplength=200)
        label_widget.pack(side="left", padx=5)
        
        wraplength = int(self._cached_width * 0.7)
        
        if len(items) == 0:
            value_widget = ttk.Label(line_frame, text=self.t("none"), font=get_cjk_font(10), 
                                     foreground="gray", wraplength=wraplength, justify="left")
            value_widget.pack(side="left", padx=5, fill="x", expand=True)
        else:
            value_text = ", ".join(str(item) for item in items)
            value_widget = ttk.Label(line_frame, text=value_text, font=get_cjk_font(10), 
                                    wraplength=wraplength, justify="left")
            value_widget.pack(side="left", padx=5, fill="x", expand=True)
    
    def add_list_info_horizontal(self, parent, label, items):
        """添加列表信息，横向一行展示（为之后修改功能留接口）"""
        line_frame = tk.Frame(parent, bg=Colors.WHITE)
        line_frame.pack(fill="x", padx=5, pady=2)
        
        label_widget = ttk.Label(line_frame, text=label + ":", font=get_cjk_font(10))
        label_widget.pack(side="left", padx=5)
        
        # 创建可滚动的横向显示区域
        canvas_frame = tk.Frame(line_frame, bg=Colors.WHITE)
        canvas_frame.pack(side="left", fill="x", expand=True, padx=5)
        
        # 使用Canvas实现横向滚动
        canvas = tk.Canvas(canvas_frame, height=25, bg=Colors.WHITE, highlightthickness=0)
        scrollbar_h = Scrollbar(canvas_frame, orient="horizontal", command=canvas.xview)
        scrollable_frame = tk.Frame(canvas, bg=Colors.WHITE)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(xscrollcommand=scrollbar_h.set)
        
        if len(items) == 0:
            value_widget = ttk.Label(scrollable_frame, text=self.t("none"), font=get_cjk_font(10), 
                                     foreground="gray")
            value_widget.pack(side="left", padx=2)
        else:
            value_text = ", ".join(str(item) for item in items)
            value_widget = ttk.Label(scrollable_frame, text=value_text, font=get_cjk_font(10))
            value_widget.pack(side="left", padx=2)
        
        canvas.pack(side="left", fill="x", expand=True)
        if len(items) > 10:  # 只有内容较多时才显示滚动条
            scrollbar_h.pack(side="bottom", fill="x")
        
        # 存储items以便之后修改功能使用
        scrollable_frame.items_data = items
        scrollable_frame.label_key = label
        
        return scrollable_frame
    
    def add_info_line_with_tooltip(self, parent, label, value, tooltip_text, var_name=None, widget_key=None, text_color=None):
        """添加带可点击问号的信息行
        
        Args:
            parent: 父容器
            label: 标签文本
            value: 值
            tooltip_text: 提示文本
            var_name: 变量名（可选）
            widget_key: widget 标识键，用于增量更新（可选）
            text_color: 文字颜色（可选，如果未提供则从父容器背景色推断）
        
        Returns:
            value_widget: 值 widget 的引用
        """
        # 如果提供了 widget_key 且 widget 已存在，进行增量更新
        if widget_key and widget_key in self._widget_map:
            widget_info = self._widget_map[widget_key]
            value_widget = widget_info.get('value_widget')
            label_widget = widget_info.get('label_widget')
            tooltip_text_widget = widget_info.get('tooltip_text_widget')
            
            if value_widget and value_widget.winfo_exists():
                # 更新值文本
                value_widget.config(text=str(value))
                # 更新标签文本（语言切换时可能需要）
                if label_widget:
                    label_widget.config(text=label + ":")
                # 更新提示文本
                if tooltip_text_widget:
                    tooltip_text_widget.config(text=tooltip_text)
                return value_widget
        
        # 如果没有指定文字颜色，使用默认颜色
        # 注意：狂信徒区域现在使用白色背景和深红色文字，已通过text_color参数显式传递
        
        # 创建一个容器来包含主行和提示信息
        parent_bg = parent.cget("bg") if hasattr(parent, "cget") else Colors.WHITE
        container = tk.Frame(parent, bg=parent_bg)
        container.pack(fill="x", padx=5, pady=2)
        
        line_frame = tk.Frame(container, bg=parent_bg)
        line_frame.pack(fill="x")
        
        label_widget = ttk.Label(line_frame, text=label + ":", font=get_cjk_font(10), 
                             wraplength=200, foreground=text_color if text_color else None)
        label_widget.pack(side="left", padx=5)
        
        # 如果有变量名，在冒号前面显示灰色的变量名
        var_name_widget = None
        if var_name:
            var_name_widget = ttk.Label(line_frame, text=f"[{var_name}]", 
                                       font=get_cjk_font(9), 
                                       foreground="gray",
                                       wraplength=150)
            # 默认隐藏，只有勾选复选框时才显示
            if self.show_var_names_var.get():
                var_name_widget.pack(side="left", padx=2, before=label_widget)
            # 存储widget信息以便后续切换显示
            self.var_name_widgets.append({
                'widget': var_name_widget,
                'parent': line_frame,
                'label_widget': label_widget
            })
        
        # 性能优化：使用缓存的宽度
        wraplength = int(self._cached_width * 0.7)
        
        value_widget = ttk.Label(line_frame, text=str(value), font=get_cjk_font(10), 
                                wraplength=wraplength, justify="left",
                                foreground=text_color if text_color else None)
        value_widget.pack(side="left", padx=5, fill="x", expand=True)
        
        # 创建可点击的信息符号
        tooltip_label = ttk.Label(line_frame, text="ℹ", font=get_cjk_font(10, "bold"), 
                                  foreground=text_color if text_color else "blue", cursor="hand2")
        tooltip_label.pack(side="left", padx=2)
        
        # 提示信息标签（初始隐藏）
        tooltip_frame = tk.Frame(container, bg=parent_bg)
        tooltip_wraplength = int(self._cached_width * 0.85)
        
        tooltip_text_widget = ttk.Label(tooltip_frame, text=tooltip_text, 
                                       font=get_cjk_font(9), 
                                       foreground="gray",
                                       wraplength=tooltip_wraplength,
                                       justify="left")
        tooltip_text_widget.pack(anchor="w", padx=15, pady=2)
        
        # 切换显示/隐藏提示信息
        def toggle_tooltip(event=None):
            if tooltip_frame.winfo_viewable():
                tooltip_frame.pack_forget()
            else:
                tooltip_frame.pack(fill="x", padx=5, pady=2)
        
        tooltip_label.bind("<Button-1>", toggle_tooltip)
        
        # 如果提供了 widget_key，存储到映射中
        if widget_key:
            self._widget_map[widget_key] = {
                'value_widget': value_widget,
                'label_widget': label_widget,
                'container': container,
                'line_frame': line_frame,
                'var_name_widget': var_name_widget,
                'tooltip_text_widget': tooltip_text_widget
            }
        
        return value_widget
    
    def display_save_info(self, parent, save_data):
        """显示存档信息（支持增量更新）"""
        parent.update_idletasks()
        # 确保scrollable_frame的宽度已正确设置为窗口宽度的2/3
        try:
            window_width = self.window.winfo_width()
            if window_width > 1:
                width = int(window_width * 2 / 3)
                self._cached_width = width
                parent.config(width=width)
        except:
            pass
        
        # 如果已初始化，进行增量更新
        if self._is_initialized:
            self._update_save_info_incremental(save_data)
            return
        
        # 首次加载：完整创建流程
        # 获取memory数据（在多个地方使用）
        memory = save_data.get("memory", {})
        
        # 检查狂信徒线条件
        kill = save_data.get("kill", None)
        killed = save_data.get("killed", None)
        kill_start = save_data.get("killStart", 0)
        
        is_zealot_route = (
            (kill is not None and kill == 1) or
            (killed is not None and killed == 1) or
            (kill_start is not None and kill_start > 0)
        )
        
        # 如果满足狂信徒线条件，先创建狂信徒section（移到最顶端）
        if is_zealot_route:
            # 使用白色背景和深红色文字
            dark_red_text = "#8b0000"  # 深红色文字
            zealot_section = self.create_section(parent, self.t("zealot_related"), 
                                                bg_color=Colors.WHITE, text_color=dark_red_text,
                                                title_key="zealot_related")
            self._section_map["zealot_related"] = zealot_section
            
            neo = save_data.get("NEO", 0)
            self.add_info_line_with_tooltip(zealot_section, self.t("neo_value"), neo, 
                                           self.t("neo_value_tooltip"), "NEO", "NEO", text_color=dark_red_text)
            
            # 是否遭受拉米亚的诅咒
            lamia_noroi = save_data.get("Lamia_noroi", 0)
            self.add_info_line(zealot_section, self.t("lamia_curse"), lamia_noroi, "Lamia_noroi", "Lamia_noroi", text_color=dark_red_text)
            
            # 创伤值
            trauma = save_data.get("trauma", 0)
            self.add_info_line(zealot_section, self.t("trauma_value"), trauma, "trauma", "trauma", text_color=dark_red_text)
            
            # killWarning - 狂信徒警告
            kill_warning = save_data.get("killWarning", 0)
            self.add_info_line(zealot_section, self.t("kill_warning"), kill_warning, "killWarning", "killWarning", text_color=dark_red_text)
            
            # killed - 是否正在进行狂信徒线
            killed = save_data.get("killed", None)
            if killed is None:
                killed_display = self.t("variable_not_exist")
            else:
                killed_display = killed
            self.add_info_line_with_tooltip(zealot_section, self.t("killed"), killed_display,
                                           self.t("killed_tooltip"), "killed", "killed", text_color=dark_red_text)
            
            # kill - 狂信徒线完成数
            kill = save_data.get("kill", 0)
            self.add_info_line_with_tooltip(zealot_section, self.t("kill_count"), kill,
                                           self.t("kill_count_tooltip"), "kill", "kill", text_color=dark_red_text)
            
            # killStart - 在狂信徒线中选择新开一局游戏的次数
            kill_start = save_data.get("killStart", 0)
            self.add_info_line_with_tooltip(zealot_section, self.t("kill_start"), kill_start,
                                           self.t("kill_start_tooltip"), "killStart", "killStart", text_color=dark_red_text)
        
        # 1. 结局统计 + "查看达成条件"按钮
        endings = set(save_data.get("endings", []))
        collected_endings = set(save_data.get("collectedEndings", []))
        missing_endings = sorted(endings - collected_endings, key=lambda x: int(x) if x.isdigit() else 999)
        
        endings_section = self.create_section_with_button(
            parent, 
            self.t("endings_statistics"), 
            self.t("view_requirements"),
            button_command=lambda: self.show_endings_requirements(save_data, endings, collected_endings, missing_endings),
            title_key="endings_statistics"
        )
        self._section_map["endings_statistics"] = endings_section
        
        endings_count = len(endings)
        collected_endings_count = len(collected_endings)
        
        self.add_info_line(endings_section, self.t("total_endings"), endings_count, "endings", "endings.count")
        self.add_info_line(endings_section, self.t("collected_endings"), collected_endings_count, "collectedEndings", "collectedEndings.count")
        missing_endings_key = "missing_endings"
        if missing_endings:
            missing_endings_text = f"{len(missing_endings)}: {', '.join(missing_endings)}"
        else:
            missing_endings_text = self.t("none")
        self.add_info_line(endings_section, self.t("missing_endings"), missing_endings_text, None, missing_endings_key)
        self._dynamic_widgets[missing_endings_key] = {
            'section': endings_section,
            'label': self.t("missing_endings"),
            'data_key': 'missing_endings'
        }
        
        # 3. 贴纸统计 + "查看达成条件"按钮
        stickers_section = self.create_section_with_button(
            parent, 
            self.t("stickers_statistics"), 
            self.t("view_requirements"),
            button_command=lambda: None,
            title_key="stickers_statistics"
        )
        self._section_map["stickers_statistics"] = stickers_section
        
        stickers = set(save_data.get("sticker", []))
        # 总共132个贴纸，编号1-133，没有82
        all_sticker_ids = set(range(1, 82)) | set(range(83, 134))  # 1-81, 83-133
        stickers_count = len(stickers)
        total_stickers = 132
        missing_stickers = sorted(all_sticker_ids - stickers)
        
        self.add_info_line(stickers_section, self.t("total_stickers"), total_stickers, None, "stickers.total")
        self.add_info_line(stickers_section, self.t("collected_stickers"), stickers_count, "sticker", "sticker.count")
        self.add_info_line(stickers_section, self.t("missing_stickers_count"), len(missing_stickers), None, "missing_stickers.count")
        missing_stickers_key = "missing_stickers"
        if missing_stickers:
            missing_stickers_text = ", ".join(str(s) for s in missing_stickers)
        else:
            missing_stickers_text = self.t("none")
        self.add_info_line(stickers_section, self.t("missing_stickers"), missing_stickers_text, None, missing_stickers_key)
        self._dynamic_widgets[missing_stickers_key] = {
            'section': stickers_section,
            'label': self.t("missing_stickers"),
            'data_key': 'missing_stickers'
        }
        
        # 4. 角色统计
        characters_section = self.create_section(
            parent, 
            self.t("characters_statistics"),
            title_key="characters_statistics"
        )
        self._section_map["characters_statistics"] = characters_section
        
        # 过滤掉空字符串和空白字符
        characters = set(c for c in save_data.get("characters", []) if c and c.strip())
        collected_characters = set(c for c in save_data.get("collectedCharacters", []) if c and c.strip())
        characters_count = max(0, len(characters))
        collected_characters_count = max(0, len(collected_characters))
        missing_characters = sorted(characters - collected_characters)
        
        self.add_info_line(characters_section, self.t("total_characters"), characters_count, "characters", "characters.count")
        self.add_info_line(characters_section, self.t("collected_characters"), collected_characters_count, "collectedCharacters", "collectedCharacters.count")
        missing_characters_key = "missing_characters"
        if missing_characters:
            self.add_list_info(characters_section, self.t("missing_characters"), missing_characters)
            # 存储列表信息的 widget 引用（需要特殊处理）
            self._dynamic_widgets[missing_characters_key] = {
                'section': characters_section,
                'label': self.t("missing_characters"),
                'data_key': 'missing_characters',
                'is_list': True
            }
        else:
            self.add_info_line(characters_section, self.t("missing_characters"), self.t("none"), None, missing_characters_key)
            self._dynamic_widgets[missing_characters_key] = {
                'section': characters_section,
                'label': self.t("missing_characters"),
                'data_key': 'missing_characters',
                'is_list': False
            }
        
        # 5. 额外内容统计
        omakes_section = self.create_section(
            parent, 
            self.t("omakes_statistics"),
            title_key="omakes_statistics"
        )
        self._section_map["omakes_statistics"] = omakes_section
        
        omakes = set(save_data.get("omakes", []))
        omakes_count = len(omakes)
        collected_omakes = omakes & collected_endings  # 已收集的额外内容
        collected_omakes_count = len(collected_omakes)
        missing_omakes = sorted(omakes - collected_endings, key=lambda x: int(x) if x.isdigit() else 999)
        
        # omakes是已观看的额外内容数量
        self.add_info_line(omakes_section, self.t("total_omakes"), omakes_count, "omakes", "omakes.count")
        self.add_info_line(omakes_section, self.t("collected_omakes"), collected_omakes_count, None, "collected_omakes.count")
        missing_omakes_key = "missing_omakes"
        if missing_omakes:
            missing_omakes_text = f"{len(missing_omakes)}: {', '.join(missing_omakes)}"
        else:
            missing_omakes_text = self.t("none")
        self.add_info_line(omakes_section, self.t("missing_omakes"), missing_omakes_text, None, missing_omakes_key)
        self._dynamic_widgets[missing_omakes_key] = {
            'section': omakes_section,
            'label': self.t("missing_omakes"),
            'data_key': 'missing_omakes'
        }
        
        # 画廊数量和NG场景数移到额外内容统计
        gallery = save_data.get("gallery", [])
        gallery_count = len(gallery)
        self.add_info_line(omakes_section, self.t("gallery_count"), gallery_count, "gallery", "gallery.count")
        
        ng_scene = save_data.get("ngScene", [])
        ng_scene_count = len(ng_scene)
        self.add_info_line(omakes_section, self.t("ng_scene_count"), ng_scene_count, "ngScene", "ngScene.count")
        
        # 6. 游戏统计
        stats_section = self.create_section(parent, self.t("game_statistics"), title_key="game_statistics")
        self._section_map["game_statistics"] = stats_section
        
        whole_total_mp = save_data.get("wholeTotalMP", 0)
        self.add_info_line(stats_section, self.t("total_mp"), whole_total_mp, "wholeTotalMP", "wholeTotalMP")
        
        judge_counts = save_data.get("judgeCounts", {})
        perfect = judge_counts.get("perfect", 0)
        good = judge_counts.get("good", 0)
        bad = judge_counts.get("bad", 0)
        self.add_info_line(stats_section, self.t("judge_perfect"), perfect, "judgeCounts.perfect", "judgeCounts.perfect")
        self.add_info_line(stats_section, self.t("judge_good"), good, "judgeCounts.good", "judgeCounts.good")
        self.add_info_line(stats_section, self.t("judge_bad"), bad, "judgeCounts.bad", "judgeCounts.bad")
        
        epilogue = save_data.get("epilogue", 0)
        self.add_info_line(stats_section, self.t("epilogue_count"), epilogue, "epilogue", "epilogue")
        
        loop_count = save_data.get("loopCount", 0)
        self.add_info_line(stats_section, self.t("loop_count"), loop_count, "loopCount", "loopCount")
        
        # 周回记录：记录到达真结局时的周回数
        loop_record = save_data.get("loopRecord", 0)
        self.add_info_line_with_tooltip(stats_section, self.t("loop_record"), loop_record,
                                       self.t("loop_record_tooltip"), "loopRecord", "loopRecord")
        
        # 如果不满足狂信徒线条件，在这里创建狂信徒相关section（正常位置）
        if not is_zealot_route:
            # 6.5. 狂信徒相关
            zealot_section = self.create_section(parent, self.t("zealot_related"), title_key="zealot_related")
            self._section_map["zealot_related"] = zealot_section
            
            neo = save_data.get("NEO", 0)
            self.add_info_line_with_tooltip(zealot_section, self.t("neo_value"), neo, 
                                           self.t("neo_value_tooltip"), "NEO", "NEO")
            
            # 是否遭受拉米亚的诅咒
            lamia_noroi = save_data.get("Lamia_noroi", 0)
            self.add_info_line(zealot_section, self.t("lamia_curse"), lamia_noroi, "Lamia_noroi", "Lamia_noroi")
            
            # 创伤值
            trauma = save_data.get("trauma", 0)
            self.add_info_line(zealot_section, self.t("trauma_value"), trauma, "trauma", "trauma")
            
            # killWarning - 狂信徒警告
            kill_warning = save_data.get("killWarning", 0)
            self.add_info_line(zealot_section, self.t("kill_warning"), kill_warning, "killWarning", "killWarning")
            
            # killed - 是否正在进行狂信徒线
            killed = save_data.get("killed", None)
            if killed is None:
                killed_display = self.t("variable_not_exist")
            else:
                killed_display = killed
            self.add_info_line_with_tooltip(zealot_section, self.t("killed"), killed_display,
                                           self.t("killed_tooltip"), "killed", "killed")
            
            # kill - 狂信徒线完成数
            kill = save_data.get("kill", 0)
            self.add_info_line_with_tooltip(zealot_section, self.t("kill_count"), kill,
                                           self.t("kill_count_tooltip"), "kill", "kill")
            
            # killStart - 在狂信徒线中选择新开一局游戏的次数
            kill_start = save_data.get("killStart", 0)
            self.add_info_line_with_tooltip(zealot_section, self.t("kill_start"), kill_start,
                                           self.t("kill_start_tooltip"), "killStart", "killStart")
        
        # 7. 角色信息
        character_section = self.create_section(parent, self.t("character_info"), title_key="character_info")
        self._section_map["character_info"] = character_section
        
        character_name = memory.get("name", self.t("not_set"))
        self.add_info_line(character_section, self.t("character_name"), character_name, "memory.name", "memory.name")
        
        seibetu = memory.get("seibetu", 0)
        if seibetu == 1:
            gender_text = self.t("gender_male")
        elif seibetu == 2:
            gender_text = self.t("gender_female")
        else:
            gender_text = self.t("not_set")
        self.add_info_line(character_section, self.t("character_gender"), gender_text, "memory.seibetu", "memory.seibetu")
        
        hutanari = memory.get("hutanari", 0)
        self.add_info_line(character_section, self.t("hutanari"), hutanari, "memory.hutanari", "memory.hutanari")
        
        # 8. 其他信息
        other_section = self.create_section(parent, self.t("other_info"), title_key="other_info")
        self._section_map["other_info"] = other_section
        
        # 存档列表编号和相册页码（相册页码从0开始，显示时+1）
        save_list_no = save_data.get("saveListNo", 0)
        album_page_no = save_data.get("albumPageNo", 0) + 1
        self.add_info_line(other_section, self.t("save_list_no"), save_list_no, "saveListNo", "saveListNo")
        self.add_info_line(other_section, self.t("album_page_no"), album_page_no, "albumPageNo", "albumPageNo")
        
        desu = save_data.get("desu", 0)
        self.add_info_line(other_section, self.t("desu"), desu, "desu", "desu")
        
        hade = save_data.get("hade", 0)
        self.add_info_line(other_section, self.t("hade"), hade, "hade", "hade")
        
        camera_enable = memory.get("cameraEnable", 0)
        self.add_info_line(other_section, self.t("camera_enable"), camera_enable, "memory.cameraEnable", "memory.cameraEnable")
        
        yubiwa = memory.get("yubiwa", 0)
        self.add_info_line(other_section, self.t("yubiwa"), yubiwa, "memory.yubiwa", "memory.yubiwa")
        
        autosave = save_data.get("system", {}).get("autosave", False)
        self.add_info_line(other_section, self.t("autosave_enabled"), autosave, "system.autosave", "system.autosave")
        
        fullscreen = save_data.get("fullscreen", False)
        self.add_info_line(other_section, self.t("fullscreen"), fullscreen, "fullscreen", "fullscreen")
        
        # 添加提示文字
        hint_label = ttk.Label(other_section, text=self.t("other_info_hint"), 
                              font=get_cjk_font(9), 
                              foreground="gray",
                              wraplength=int(self._cached_width * 0.85),
                              justify="left")
        hint_label.pack(anchor="w", padx=5, pady=(5, 0))
        
        # 保存提示标签的引用，用于语言切换
        self._hint_labels.append({
            'label': hint_label,
            'text_key': 'other_info_hint'
        })
        
        # 所有组件创建完成后，更新滚动区域并绑定滚轮事件
        def finalize_scrolling():
            try:
                # 检查必要的属性是否存在
                if not hasattr(self, 'scrollable_canvas') or not self.scrollable_canvas:
                    return
                if not hasattr(self, 'scrollable_frame') or not self.scrollable_frame:
                    return
                
                # 检查canvas是否仍然存在
                try:
                    self.scrollable_canvas.winfo_exists()
                except:
                    return
                
                # 获取bbox并检查是否有效
                bbox = self.scrollable_canvas.bbox("all")
                if bbox is None:
                    # 如果bbox为None，延迟重试
                    self.window.after(50, finalize_scrolling)
                    return
                
                # 检查bbox是否有效
                if len(bbox) >= 4:
                    x1, y1, x2, y2 = bbox[:4]
                    if x2 > x1 and y2 > y1:
                        # 只有bbox有效时才更新scrollregion
                        self.scrollable_canvas.configure(scrollregion=bbox)
                    else:
                        # bbox无效，延迟重试
                        self.window.after(50, finalize_scrolling)
                        return
                else:
                    # bbox格式不正确，延迟重试
                    self.window.after(50, finalize_scrolling)
                    return
                
                # 为新添加的所有组件绑定滚轮事件（重新绑定整个scrollable_frame及其子组件）
                if hasattr(self, '_bind_mousewheel_recursive') and hasattr(self, '_scrollable_frame'):
                    try:
                        self._bind_mousewheel_recursive(self._scrollable_frame)
                    except:
                        pass
                # 同时重新绑定left_frame，确保整个区域都能滚动
                if hasattr(self, '_bind_mousewheel_recursive') and hasattr(self, '_left_frame'):
                    try:
                        self._bind_mousewheel_recursive(self._left_frame)
                    except:
                        pass
            except Exception:
                # 出错时延迟重试
                self.window.after(50, finalize_scrolling)
        
        self.window.after_idle(finalize_scrolling)
        
        # 标记为已初始化
        self._is_initialized = True
    
    def _update_save_info_incremental(self, save_data):
        """增量更新存档信息（不销毁重建widget）"""
        memory = save_data.get("memory", {})
        
        # 更新角色信息
        character_name = memory.get("name", self.t("not_set"))
        self.add_info_line(None, self.t("character_name"), character_name, "memory.name", "memory.name")
        
        seibetu = memory.get("seibetu", 0)
        if seibetu == 1:
            gender_text = self.t("gender_male")
        elif seibetu == 2:
            gender_text = self.t("gender_female")
        else:
            gender_text = self.t("not_set")
        self.add_info_line(None, self.t("character_gender"), gender_text, "memory.seibetu", "memory.seibetu")
        
        hutanari = memory.get("hutanari", 0)
        self.add_info_line(None, self.t("hutanari"), hutanari, "memory.hutanari", "memory.hutanari")
        
        # 更新结局统计
        endings = set(save_data.get("endings", []))
        collected_endings = set(save_data.get("collectedEndings", []))
        missing_endings = sorted(endings - collected_endings, key=lambda x: int(x) if x.isdigit() else 999)
        
        endings_count = len(endings)
        collected_endings_count = len(collected_endings)
        self.add_info_line(None, self.t("total_endings"), endings_count, "endings", "endings.count")
        self.add_info_line(None, self.t("collected_endings"), collected_endings_count, "collectedEndings", "collectedEndings.count")
        
        # 更新缺失结局（动态内容）
        if missing_endings:
            missing_endings_text = f"{len(missing_endings)}: {', '.join(missing_endings)}"
        else:
            missing_endings_text = self.t("none")
        self.add_info_line(None, self.t("missing_endings"), missing_endings_text, None, "missing_endings")
        
        # 更新贴纸统计
        stickers = set(save_data.get("sticker", []))
        all_sticker_ids = set(range(1, 82)) | set(range(83, 134))
        stickers_count = len(stickers)
        total_stickers = 132
        missing_stickers = sorted(all_sticker_ids - stickers)
        
        self.add_info_line(None, self.t("total_stickers"), total_stickers, None, "stickers.total")
        self.add_info_line(None, self.t("collected_stickers"), stickers_count, "sticker", "sticker.count")
        self.add_info_line(None, self.t("missing_stickers_count"), len(missing_stickers), None, "missing_stickers.count")
        
        if missing_stickers:
            missing_stickers_text = ", ".join(str(s) for s in missing_stickers)
        else:
            missing_stickers_text = self.t("none")
        self.add_info_line(None, self.t("missing_stickers"), missing_stickers_text, None, "missing_stickers")
        
        # 更新角色统计
        characters = set(c for c in save_data.get("characters", []) if c and c.strip())
        collected_characters = set(c for c in save_data.get("collectedCharacters", []) if c and c.strip())
        characters_count = max(0, len(characters))
        collected_characters_count = max(0, len(collected_characters))
        missing_characters = sorted(characters - collected_characters)
        
        self.add_info_line(None, self.t("total_characters"), characters_count, "characters", "characters.count")
        self.add_info_line(None, self.t("collected_characters"), collected_characters_count, "collectedCharacters", "collectedCharacters.count")
        
        # 更新缺失角色（动态内容，需要特殊处理列表）
        if "missing_characters" in self._dynamic_widgets:
            widget_info = self._dynamic_widgets["missing_characters"]
            section = widget_info.get('section')
            if section and section.winfo_exists():
                # 如果之前是列表，需要删除旧的widget
                if widget_info.get('is_list'):
                    # 找到并删除旧的列表widget
                    for child in section.winfo_children():
                        try:
                            if hasattr(child, 'items_data'):
                                child.destroy()
                        except:
                            pass
                
                if missing_characters:
                    self.add_list_info(section, self.t("missing_characters"), missing_characters)
                    widget_info['is_list'] = True
                else:
                    self.add_info_line(section, self.t("missing_characters"), self.t("none"), None, "missing_characters")
                    widget_info['is_list'] = False
        
        # 更新额外内容统计
        omakes = set(save_data.get("omakes", []))
        omakes_count = len(omakes)
        collected_omakes = omakes & collected_endings
        collected_omakes_count = len(collected_omakes)
        missing_omakes = sorted(omakes - collected_endings, key=lambda x: int(x) if x.isdigit() else 999)
        
        self.add_info_line(None, self.t("total_omakes"), omakes_count, "omakes", "omakes.count")
        self.add_info_line(None, self.t("collected_omakes"), collected_omakes_count, None, "collected_omakes.count")
        
        if missing_omakes:
            missing_omakes_text = f"{len(missing_omakes)}: {', '.join(missing_omakes)}"
        else:
            missing_omakes_text = self.t("none")
        self.add_info_line(None, self.t("missing_omakes"), missing_omakes_text, None, "missing_omakes")
        
        gallery = save_data.get("gallery", [])
        gallery_count = len(gallery)
        self.add_info_line(None, self.t("gallery_count"), gallery_count, "gallery", "gallery.count")
        
        ng_scene = save_data.get("ngScene", [])
        ng_scene_count = len(ng_scene)
        self.add_info_line(None, self.t("ng_scene_count"), ng_scene_count, "ngScene", "ngScene.count")
        
        # 更新游戏统计
        whole_total_mp = save_data.get("wholeTotalMP", 0)
        self.add_info_line(None, self.t("total_mp"), whole_total_mp, "wholeTotalMP", "wholeTotalMP")
        
        judge_counts = save_data.get("judgeCounts", {})
        perfect = judge_counts.get("perfect", 0)
        good = judge_counts.get("good", 0)
        bad = judge_counts.get("bad", 0)
        self.add_info_line(None, self.t("judge_perfect"), perfect, "judgeCounts.perfect", "judgeCounts.perfect")
        self.add_info_line(None, self.t("judge_good"), good, "judgeCounts.good", "judgeCounts.good")
        self.add_info_line(None, self.t("judge_bad"), bad, "judgeCounts.bad", "judgeCounts.bad")
        
        epilogue = save_data.get("epilogue", 0)
        self.add_info_line(None, self.t("epilogue_count"), epilogue, "epilogue", "epilogue")
        
        loop_count = save_data.get("loopCount", 0)
        self.add_info_line(None, self.t("loop_count"), loop_count, "loopCount", "loopCount")
        
        loop_record = save_data.get("loopRecord", 0)
        self.add_info_line_with_tooltip(None, self.t("loop_record"), loop_record,
                                       self.t("loop_record_tooltip"), "loopRecord", "loopRecord")
        
        # 更新狂信徒相关
        neo = save_data.get("NEO", 0)
        self.add_info_line_with_tooltip(None, self.t("neo_value"), neo, 
                                       self.t("neo_value_tooltip"), "NEO", "NEO")
        
        lamia_noroi = save_data.get("Lamia_noroi", 0)
        self.add_info_line(None, self.t("lamia_curse"), lamia_noroi, "Lamia_noroi", "Lamia_noroi")
        
        trauma = save_data.get("trauma", 0)
        self.add_info_line(None, self.t("trauma_value"), trauma, "trauma", "trauma")
        
        kill_warning = save_data.get("killWarning", 0)
        self.add_info_line(None, self.t("kill_warning"), kill_warning, "killWarning", "killWarning")
        
        killed = save_data.get("killed", None)
        if killed is None:
            killed_display = self.t("variable_not_exist")
        else:
            killed_display = killed
        self.add_info_line_with_tooltip(None, self.t("killed"), killed_display,
                                       self.t("killed_tooltip"), "killed", "killed")
        
        kill = save_data.get("kill", 0)
        self.add_info_line_with_tooltip(None, self.t("kill_count"), kill,
                                       self.t("kill_count_tooltip"), "kill", "kill")
        
        kill_start = save_data.get("killStart", 0)
        self.add_info_line_with_tooltip(None, self.t("kill_start"), kill_start,
                                       self.t("kill_start_tooltip"), "killStart", "killStart")
        
        # 更新其他信息
        save_list_no = save_data.get("saveListNo", 0)
        album_page_no = save_data.get("albumPageNo", 0) + 1
        self.add_info_line(None, self.t("save_list_no"), save_list_no, "saveListNo", "saveListNo")
        self.add_info_line(None, self.t("album_page_no"), album_page_no, "albumPageNo", "albumPageNo")
        
        desu = save_data.get("desu", 0)
        self.add_info_line(None, self.t("desu"), desu, "desu", "desu")
        
        hade = save_data.get("hade", 0)
        self.add_info_line(None, self.t("hade"), hade, "hade", "hade")
        
        camera_enable = memory.get("cameraEnable", 0)
        self.add_info_line(None, self.t("camera_enable"), camera_enable, "memory.cameraEnable", "memory.cameraEnable")
        
        yubiwa = memory.get("yubiwa", 0)
        self.add_info_line(None, self.t("yubiwa"), yubiwa, "memory.yubiwa", "memory.yubiwa")
        
        autosave = save_data.get("system", {}).get("autosave", False)
        self.add_info_line(None, self.t("autosave_enabled"), autosave, "system.autosave", "system.autosave")
        
        fullscreen = save_data.get("fullscreen", False)
        self.add_info_line(None, self.t("fullscreen"), fullscreen, "fullscreen", "fullscreen")
    
    def apply_json_syntax_highlight(self, text_widget, content):
        """应用JSON语法高亮"""
        # 定义高亮规则（按优先级，先匹配更具体的）
        patterns = [
            (r'"[^"]*"', 'string'),  # 字符串（包含转义字符）
            (r'\b(true|false|null)\b', 'keyword'),  # 关键字
            (r'\b\d+\.?\d*\b', 'number'),  # 数字
            (r'[{}[\]]', 'bracket'),  # 括号
            (r'[:,]', 'punctuation'),  # 标点
        ]
        
        # 清除现有tags
        for tag in ['string', 'keyword', 'number', 'bracket', 'punctuation']:
            text_widget.tag_remove(tag, "1.0", "end")
        
        # 获取等宽字体
        try:
            if platform.system() == "Windows":
                mono_font = ("Consolas", 10)
            elif platform.system() == "Darwin":
                mono_font = ("Monaco", 10)
            else:
                mono_font = ("DejaVu Sans Mono", 10)
        except:
            mono_font = ("Courier", 10)
        
        # 配置tag样式
        text_widget.tag_config('string', foreground='#008000', font=mono_font)  # 绿色
        text_widget.tag_config('keyword', foreground='#0000FF', font=mono_font)  # 蓝色
        text_widget.tag_config('number', foreground='#FF0000', font=mono_font)  # 红色
        text_widget.tag_config('bracket', foreground='#000000', font=(mono_font[0], mono_font[1], "bold"))  # 黑色加粗
        text_widget.tag_config('punctuation', foreground='#666666', font=mono_font)  # 灰色
        
        # 应用高亮（按行处理，避免跨行匹配问题）
        lines = content.split('\n')
        for line_num, line in enumerate(lines):
            for pattern, tag_name in patterns:
                for match in re.finditer(pattern, line):
                    start_line = line_num + 1
                    start_col = match.start()
                    end_line = line_num + 1
                    end_col = match.end()
                    start = f"{start_line}.{start_col}"
                    end = f"{end_line}.{end_col}"
                    text_widget.tag_add(tag_name, start, end)
    
    def show_save_file_viewer(self):
        """显示存档文件查看器窗口"""
        if not self.save_data:
            return
        
        # 获取根窗口（从parent向上查找）
        root_window = self.window
        while not isinstance(root_window, tk.Tk) and hasattr(root_window, 'master'):
            root_window = root_window.master
        
        # 创建新窗口
        viewer_window = tk.Toplevel(root_window)
        viewer_window.title(self.t("save_file_viewer_title"))
        viewer_window.geometry("900x700")
        set_window_icon(viewer_window)
        
        
        # 创建主框架
        main_frame = tk.Frame(viewer_window)
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # 添加提示文字
        hint_frame = tk.Frame(main_frame, bg=Colors.WHITE)
        hint_frame.pack(fill="x", pady=(0, 10))
        hint_label = ttk.Label(hint_frame, text=self.t("viewer_hint_text"), 
                               font=get_cjk_font(9), 
                               foreground="gray",
                               wraplength=850,
                               justify="left")
        hint_label.pack(anchor="w", padx=5)
        
        # 创建工具栏
        toolbar = tk.Frame(main_frame)
        toolbar.pack(fill="x", pady=(0, 5))
        
        # 初始化搜索相关变量（需要在update_display之前定义）
        search_matches = []  # 所有匹配位置
        current_search_pos = [0]  # 当前搜索位置
        search_results_label = None  # 稍后创建
        
        # 取消折叠/横置复选框变量
        disable_collapse_var = tk.BooleanVar(value=False)
        
        # 开启修改复选框变量
        enable_edit_var = tk.BooleanVar(value=False)
        
        # 保存按钮（稍后创建，初始禁用）
        save_button = None
        
        # 自定义JSON格式化函数
        def format_json_custom(obj, indent=0):
            """自定义JSON格式化，列表字段在一行内显示"""
            list_fields = ["endings", "collectedEndings", "omakes", "characters", "collectedCharacters", "sticker", "gallery", "ngScene"]
            indent_str = "  " * indent
            
            if isinstance(obj, dict):
                items = []
                for key, value in obj.items():
                    if key in list_fields and isinstance(value, list):
                        # 列表字段横向展示
                        value_str = json.dumps(value, ensure_ascii=False)
                        items.append(f'"{key}": {value_str}')
                    elif isinstance(value, (dict, list)):
                        # 嵌套对象正常格式化
                        value_str = format_json_custom(value, indent + 1)
                        items.append(f'"{key}": {value_str}')
                    else:
                        value_str = json.dumps(value, ensure_ascii=False)
                        items.append(f'"{key}": {value_str}')
                
                if indent == 0:
                    return "{\n" + indent_str + "  " + (",\n" + indent_str + "  ").join(items) + "\n" + indent_str + "}"
                else:
                    return "{\n" + indent_str + "  " + (",\n" + indent_str + "  ").join(items) + "\n" + indent_str + "}"
            elif isinstance(obj, list):
                # 普通列表正常格式化
                items = [format_json_custom(item, indent + 1) if isinstance(item, (dict, list)) else json.dumps(item, ensure_ascii=False) for item in obj]
                return "[\n" + indent_str + "  " + (",\n" + indent_str + "  ").join(items) + "\n" + indent_str + "]"
            else:
                return json.dumps(obj, ensure_ascii=False)
        
        # 初始化显示数据
        collapsed_fields = {}
        fields_to_collapse = ["record", "_tap_effect", "initialVars"]
        for field in fields_to_collapse:
            if field in self.save_data:
                collapsed_fields[field] = self.save_data[field]
            elif isinstance(self.save_data, dict):
                for key, value in self.save_data.items():
                    if isinstance(value, dict) and field in value:
                        collapsed_fields[f"{key}.{field}"] = value[field]
                        break
        
        display_data = json.loads(json.dumps(self.save_data))
        for field_key, field_value in collapsed_fields.items():
            if "." in field_key:
                key_parts = field_key.split(".")
                temp = display_data
                for part in key_parts[:-1]:
                    temp = temp[part]
                temp[key_parts[-1]] = self.t("collapsed_field_text")
            else:
                display_data[field_key] = self.t("collapsed_field_text")
        
        formatted_json = format_json_custom(display_data)
        
        # 创建Text widget和滚动条
        text_frame = tk.Frame(main_frame)
        text_frame.pack(fill="both", expand=True)
        
        # 获取等宽字体
        try:
            if platform.system() == "Windows":
                mono_font = ("Consolas", 10)
            elif platform.system() == "Darwin":
                mono_font = ("Monaco", 10)
            else:
                mono_font = ("DejaVu Sans Mono", 10)
        except:
            mono_font = ("Courier", 10)
        
        # 创建行号栏
        line_numbers = tk.Text(text_frame, 
                              font=mono_font,
                              bg="#e8e8e8",
                              fg="#666666",
                              width=4,
                              padx=5,
                              pady=2,
                              state="disabled",
                              wrap="none",
                              highlightthickness=0,
                              borderwidth=0)
        line_numbers.pack(side="left", fill="y")
        
        # 创建文本编辑区域容器
        text_container = tk.Frame(text_frame)
        text_container.pack(side="left", fill="both", expand=True)
        
        # 垂直滚动条
        v_scrollbar = Scrollbar(text_container, orient="vertical")
        v_scrollbar.pack(side="right", fill="y")
        
        # 水平滚动条
        h_scrollbar = Scrollbar(text_container, orient="horizontal")
        h_scrollbar.pack(side="bottom", fill="x")
        
        text_widget = tk.Text(text_container, 
                             font=mono_font,
                             bg="#f5f5f5",
                             fg="#333333",
                             yscrollcommand=lambda *args: (v_scrollbar.set(*args), update_line_numbers()),
                             xscrollcommand=h_scrollbar.set,
                             wrap="none",
                             tabs=("2c", "4c", "6c", "8c", "10c", "12c", "14c", "16c"))
        text_widget.pack(side="left", fill="both", expand=True)
        v_scrollbar.config(command=lambda *args: (text_widget.yview(*args), update_line_numbers()))
        h_scrollbar.config(command=text_widget.xview)
        
        # 存储原始内容（用于检测修改）
        original_content = formatted_json
        
        def update_line_numbers():
            """更新行号显示"""
            line_numbers.config(state="normal")
            line_numbers.delete("1.0", "end")
            
            # 获取文本总行数
            content = text_widget.get("1.0", "end-1c")
            if content:
                line_count = content.count('\n') + 1
            else:
                line_count = 1
            
            # 添加行号
            for i in range(1, line_count + 1):
                line_numbers.insert("end", f"{i}\n")
            
            line_numbers.config(state="disabled")
            
            # 同步滚动
            line_numbers.yview_moveto(text_widget.yview()[0])
        
        # 绑定文本变化事件以更新行号
        def on_text_change(*args):
            update_line_numbers()
            # 检测修改并添加高亮
            if enable_edit_var.get():
                detect_and_highlight_changes()
        
        text_widget.bind("<<Modified>>", on_text_change)
        text_widget.bind("<KeyRelease>", lambda e: update_line_numbers())
        text_widget.bind("<Button-1>", lambda e: update_line_numbers())
        
        # 存储修改高亮tag
        text_widget.tag_config("user_edit", background="#fff9c4")  # 非常淡的黄色
        
        def detect_and_highlight_changes():
            """检测并高亮用户修改"""
            if not enable_edit_var.get():
                return
            
            # 清除之前的高亮
            text_widget.tag_remove("user_edit", "1.0", "end")
            
            # 获取当前内容
            current_content = text_widget.get("1.0", "end-1c")
            
            # 比较原始内容和当前内容，找出差异
            if current_content != original_content:
                # 简单的逐行比较
                original_lines = original_content.split('\n')
                current_lines = current_content.split('\n')
                
                max_lines = max(len(original_lines), len(current_lines))
                for i in range(max_lines):
                    original_line = original_lines[i] if i < len(original_lines) else ""
                    current_line = current_lines[i] if i < len(current_lines) else ""
                    
                    if original_line != current_line:
                        # 高亮整行
                        line_start = f"{i+1}.0"
                        line_end = f"{i+1}.end"
                        try:
                            text_widget.tag_add("user_edit", line_start, line_end)
                        except:
                            pass
        
        # 插入JSON内容
        text_widget.insert("1.0", formatted_json)
        
        # 存储原始内容（用于检测修改）
        original_content = formatted_json
        
        # 应用语法高亮
        self.apply_json_syntax_highlight(text_widget, formatted_json)
        
        # 更新行号
        update_line_numbers()
        
        # 禁用编辑
        text_widget.config(state="disabled")
        
        # 存储折叠文本的位置范围（用于编辑限制）
        collapsed_text_ranges = []
        
        def update_collapsed_ranges():
            """更新折叠文本的位置范围"""
            collapsed_text_ranges.clear()
            if not disable_collapse_var.get():
                collapsed_text = self.t("collapsed_field_text")
                content = text_widget.get("1.0", "end-1c")
                start_pos = "1.0"
                while True:
                    pos = text_widget.search(collapsed_text, start_pos, "end", exact=True)
                    if not pos:
                        break
                    end_pos = f"{pos}+{len(collapsed_text)}c"
                    collapsed_text_ranges.append((pos, end_pos))
                    start_pos = end_pos
        
        def is_in_collapsed_range(pos):
            """检查位置是否在折叠文本范围内"""
            if disable_collapse_var.get():
                return False  # 取消折叠后，所有区域都可编辑
            for start, end in collapsed_text_ranges:
                if text_widget.compare(start, "<=", pos) and text_widget.compare(pos, "<", end):
                    return True
            return False
        
        def on_text_edit(event=None):
            """文本编辑事件处理"""
            if not enable_edit_var.get():
                return "break"
            
            # 检查是否在折叠区域内
            cursor_pos = text_widget.index("insert")
            if is_in_collapsed_range(cursor_pos):
                from tkinter import messagebox
                messagebox.showwarning(
                    self.t("cannot_edit_collapsed"),
                    self.t("cannot_edit_collapsed_detail"),
                    parent=viewer_window
                )
                return "break"
            
            return None
        
        def on_text_change(event=None):
            """文本改变事件处理（用于检测粘贴等操作）"""
            if not enable_edit_var.get():
                return
            
            # 检查当前光标位置是否在折叠区域内
            try:
                cursor_pos = text_widget.index("insert")
                if is_in_collapsed_range(cursor_pos):
                    # 如果光标在折叠区域内，阻止编辑
                    from tkinter import messagebox
                    messagebox.showwarning(
                        self.t("cannot_edit_collapsed"),
                        self.t("cannot_edit_collapsed_detail"),
                        parent=viewer_window
                    )
                    # 尝试撤销最后一次操作
                    try:
                        text_widget.edit_undo()
                    except:
                        pass
            except:
                pass
        
        # 绑定文本编辑事件
        text_widget.bind("<KeyPress>", on_text_edit)
        text_widget.bind("<Button-1>", lambda e: update_collapsed_ranges())
        text_widget.bind("<<Modified>>", on_text_change)
        
        # 启用撤销功能
        text_widget.config(undo=True)
        
        # 定义update_display函数
        def update_display(check_changes=False):
            """更新显示内容"""
            nonlocal original_content
            
            # 如果切换折叠/横置状态，检查是否有未保存的修改
            if check_changes and enable_edit_var.get():
                current_content = text_widget.get("1.0", "end-1c")
                if current_content != original_content:
                    # 有未保存的修改，弹出确认提示
                    from tkinter import messagebox
                    result = messagebox.askyesno(
                        self.t("refresh_confirm_title"),
                        self.t("unsaved_changes_warning"),
                        parent=viewer_window
                    )
                    if not result:
                        # 用户取消操作，恢复复选框状态
                        disable_collapse_var.set(not disable_collapse_var.get())
                        return
            
            # 保存当前滚动位置（在删除内容之前）
            scroll_position = text_widget.yview()[0]  # 获取垂直滚动位置（0.0到1.0之间的值）
            
            text_widget.config(state="normal")
            
            # 清除搜索高亮
            text_widget.tag_delete("search_highlight")
            search_matches.clear()
            current_search_pos[0] = 0
            if search_results_label:
                search_results_label.config(text="")
            
            if disable_collapse_var.get():
                # 取消折叠/横置：显示完整解码后的文件
                full_json = json.dumps(self.save_data, ensure_ascii=False, indent=2)
                text_widget.delete("1.0", "end")
                text_widget.insert("1.0", full_json)
                self.apply_json_syntax_highlight(text_widget, full_json)
                original_content = full_json
                collapsed_text_ranges.clear()  # 取消折叠后，没有折叠区域
            else:
                # 应用折叠和横置
                # 处理需要折叠的字段：record, _tap_effect, initialVars
                collapsed_fields = {}  # 记录哪些字段被折叠
                fields_to_collapse = ["record", "_tap_effect", "initialVars"]
                
                # 检查需要折叠的字段
                for field in fields_to_collapse:
                    if field in self.save_data:
                        collapsed_fields[field] = self.save_data[field]
                    elif isinstance(self.save_data, dict):
                        # 检查嵌套的字段
                        for key, value in self.save_data.items():
                            if isinstance(value, dict) and field in value:
                                collapsed_fields[f"{key}.{field}"] = value[field]
                                break
                
                # 创建处理后的数据用于显示
                display_data = json.loads(json.dumps(self.save_data))  # 深拷贝
                
                # 折叠字段
                for field_key, field_value in collapsed_fields.items():
                    if "." in field_key:
                        key_parts = field_key.split(".")
                        temp = display_data
                        for part in key_parts[:-1]:
                            temp = temp[part]
                        temp[key_parts[-1]] = self.t("collapsed_field_text")
                    else:
                        display_data[field_key] = self.t("collapsed_field_text")
                
                # 自定义JSON格式化：列表字段横向展示
                formatted_json = format_json_custom(display_data)
                text_widget.delete("1.0", "end")
                text_widget.insert("1.0", formatted_json)
                self.apply_json_syntax_highlight(text_widget, formatted_json)
                original_content = formatted_json
                
                # 更新折叠文本范围
                update_collapsed_ranges()
            
            # 更新行号
            update_line_numbers()
            
            # 根据编辑模式设置编辑状态
            if enable_edit_var.get():
                text_widget.config(state="normal")
                if save_button:
                    save_button.config(state="normal")
                # 检测并高亮修改
                detect_and_highlight_changes()
            else:
                text_widget.config(state="disabled")
                if save_button:
                    save_button.config(state="disabled")
                # 清除修改高亮
                text_widget.tag_remove("user_edit", "1.0", "end")
            
            # 恢复滚动位置（在所有更新完成后）
            # 使用 after_idle 确保在UI更新完成后再恢复滚动位置
            def restore_scroll():
                text_widget.yview_moveto(scroll_position)
            viewer_window.after_idle(restore_scroll)
        
        # 添加取消折叠/横置复选框
        def toggle_collapse():
            """切换折叠/横置状态"""
            # update_display会检查未保存的修改
            update_display(check_changes=True)
        
        disable_collapse_checkbox = ttk.Checkbutton(toolbar, 
                                                     text=self.t("disable_collapse_horizontal"),
                                                     variable=disable_collapse_var,
                                                     command=toggle_collapse)
        disable_collapse_checkbox.pack(side="left", padx=5)
        
        # 添加查找功能
        search_frame = tk.Frame(toolbar)
        search_frame.pack(side="left", padx=5)
        
        search_entry = ttk.Entry(search_frame, width=20)
        search_entry.pack(side="left", padx=2)
        
        search_results_label = ttk.Label(search_frame, text="")
        search_results_label.pack(side="left", padx=2)
        
        # 添加复制按钮
        def copy_to_clipboard():
            viewer_window.clipboard_clear()
            # 复制完整数据
            full_json = json.dumps(self.save_data, ensure_ascii=False, indent=2)
            viewer_window.clipboard_append(full_json)
        
        copy_button = ttk.Button(toolbar, text=self.t("copy_to_clipboard"), command=copy_to_clipboard)
        copy_button.pack(side="left", padx=5)
        
        # 添加右侧区域（用于放置开启修改复选框和保存按钮）
        toolbar_right = tk.Frame(toolbar)
        toolbar_right.pack(side="right", padx=5)
        
        # 添加刷新按钮
        def check_unsaved_changes():
            """检查是否有未保存的修改，如果有则弹出确认提示"""
            if enable_edit_var.get():
                current_content = text_widget.get("1.0", "end-1c")
                if current_content != original_content:
                    # 有未保存的修改，弹出确认提示
                    from tkinter import messagebox
                    result = messagebox.askyesno(
                        self.t("refresh_confirm_title"),
                        self.t("unsaved_changes_warning"),
                        parent=viewer_window  # 确保从viewer_window弹出
                    )
                    return result
            return True  # 没有修改或未开启编辑模式，允许继续
        
        # 绑定窗口关闭事件
        def on_window_close():
            """窗口关闭事件处理"""
            # 检查是否有未保存的修改
            if not check_unsaved_changes():
                # 用户取消关闭，阻止窗口关闭
                return
            viewer_window.destroy()
            # 窗口关闭后，刷新存档分析页面
            self.refresh()
        
        viewer_window.protocol("WM_DELETE_WINDOW", on_window_close)
        
        def refresh_save_file():
            """刷新存档文件"""
            # 检查是否有未保存的修改
            if not check_unsaved_changes():
                return
            
            # 重新加载存档文件
            self.save_data = self.load_save_file()
            if not self.save_data:
                from tkinter import messagebox
                messagebox.showerror(
                    self.t("error"),
                    self.t("save_file_not_found"),
                    parent=viewer_window
                )
                return
            
            # 更新显示
            update_display()
        
        refresh_button = ttk.Button(toolbar_right, text=self.t("refresh"), command=refresh_save_file)
        refresh_button.pack(side="right", padx=5)
        
        # 添加开启修改复选框（最右侧）
        enable_edit_checkbox = ttk.Checkbutton(toolbar_right, 
                                               text=self.t("enable_edit"),
                                               variable=enable_edit_var,
                                               command=lambda: toggle_edit_mode())
        enable_edit_checkbox.pack(side="right", padx=5)
        
        # 添加保存按钮
        def save_save_file():
            """保存存档文件"""
            try:
                # 获取文本内容
                text_widget.config(state="normal")
                content = text_widget.get("1.0", "end-1c")
                
                # 验证JSON格式
                try:
                    edited_data = json.loads(content)
                except json.JSONDecodeError as e:
                    text_widget.config(state="normal" if enable_edit_var.get() else "disabled")
                    from tkinter import messagebox
                    messagebox.showerror(
                        self.t("json_format_error"),
                        self.t("json_format_error_detail").format(error=str(e)),
                        parent=viewer_window
                    )
                    return
                
                # 将显示格式转回原始格式
                # 如果取消折叠/横置，数据已经是完整格式，直接使用
                # 如果折叠/横置，需要恢复折叠字段的原始值
                if not disable_collapse_var.get():
                    # 恢复折叠字段的原始值
                    collapsed_text = self.t("collapsed_field_text")
                    fields_to_collapse = ["record", "_tap_effect", "initialVars"]
                    
                    # 检查并恢复折叠字段
                    for field in fields_to_collapse:
                        if field in edited_data:
                            if isinstance(edited_data[field], str) and edited_data[field] == collapsed_text:
                                # 这是折叠字段，恢复原始值
                                if field in self.save_data:
                                    edited_data[field] = self.save_data[field]
                        else:
                            # 检查嵌套字段
                            for key, value in self.save_data.items():
                                if isinstance(value, dict) and field in value:
                                    # 检查edited_data中是否有这个嵌套字段
                                    if key in edited_data and isinstance(edited_data[key], dict):
                                        if field in edited_data[key]:
                                            if isinstance(edited_data[key][field], str) and edited_data[key][field] == collapsed_text:
                                                # 这是折叠字段，恢复原始值
                                                edited_data[key][field] = value[field]
                                    elif key in edited_data and isinstance(edited_data[key], str) and edited_data[key] == collapsed_text:
                                        # 整个嵌套对象被折叠了，恢复整个对象
                                        edited_data[key] = value
                                    break
                
                # 确认保存
                from tkinter import messagebox
                result = messagebox.askyesno(
                    self.t("save_confirm_title"),
                    self.t("save_confirm_text"),
                    parent=viewer_window
                )
                
                if not result:
                    text_widget.config(state="normal" if enable_edit_var.get() else "disabled")
                    return
                
                # 保存到文件
                sf_path = os.path.join(self.storage_dir, 'DevilConnection_sf.sav')
                json_str = json.dumps(edited_data, ensure_ascii=False)
                encoded = urllib.parse.quote(json_str)
                
                with open(sf_path, 'w', encoding='utf-8') as f:
                    f.write(encoded)
                
                # 更新self.save_data
                self.save_data = edited_data
                
                # 更新原始内容
                nonlocal original_content
                original_content = content
                
                # 显示成功消息
                messagebox.showinfo(
                    self.t("success"), 
                    self.t("save_success"),
                    parent=viewer_window
                )
                
                # 刷新显示
                update_display()
                
            except Exception as e:
                from tkinter import messagebox
                messagebox.showerror(
                    self.t("save_failed"),
                    str(e),
                    parent=viewer_window
                )
                text_widget.config(state="normal" if enable_edit_var.get() else "disabled")
        
        save_button = ttk.Button(toolbar_right, text=self.t("save_file"), 
                                command=save_save_file, state="disabled")
        save_button.pack(side="right", padx=5)
        
        def toggle_edit_mode():
            """切换编辑模式"""
            # 如果取消勾选"开启修改"，检查是否有未保存的修改
            if not enable_edit_var.get():
                if not check_unsaved_changes():
                    # 用户取消操作，恢复勾选状态
                    enable_edit_var.set(True)
                    return
            
            # 每次切换都刷新sav文件
            self.save_data = self.load_save_file()
            if not self.save_data:
                enable_edit_var.set(False)
                from tkinter import messagebox
                messagebox.showerror(
                    self.t("error"),
                    self.t("save_file_not_found"),
                    parent=viewer_window
                )
                return
            
            if enable_edit_var.get():
                # 开启编辑模式：刷新显示并允许编辑
                update_display()
                # 更新原始内容为当前显示的内容
                nonlocal original_content
                original_content = text_widget.get("1.0", "end-1c")
            else:
                # 关闭编辑模式：禁用编辑
                text_widget.config(state="disabled")
                if save_button:
                    save_button.config(state="disabled")
                # 清除修改高亮
                text_widget.tag_remove("user_edit", "1.0", "end")
        
        def find_text(direction="next"):
            """查找文本"""
            search_term = search_entry.get()
            if not search_term:
                search_results_label.config(text="")
                return
            
            # 启用编辑以进行搜索
            was_disabled = text_widget.cget("state") == "disabled"
            if was_disabled:
                text_widget.config(state="normal")
            content = text_widget.get("1.0", "end-1c")
            
            # 清除之前的搜索高亮
            text_widget.tag_delete("search_highlight")
            text_widget.tag_config("search_highlight", background="yellow")
            
            # 查找所有匹配
            search_matches.clear()
            start_pos = "1.0"
            while True:
                pos = text_widget.search(search_term, start_pos, "end", nocase=True)
                if not pos:
                    break
                end_pos = f"{pos}+{len(search_term)}c"
                search_matches.append((pos, end_pos))
                text_widget.tag_add("search_highlight", pos, end_pos)
                start_pos = end_pos
            
            # 导航到匹配位置
            if search_matches:
                if direction == "next":
                    current_search_pos[0] = (current_search_pos[0] + 1) % len(search_matches)
                else:
                    current_search_pos[0] = (current_search_pos[0] - 1) % len(search_matches)
                
                pos, end_pos = search_matches[current_search_pos[0]]
                text_widget.see(pos)
                text_widget.mark_set("insert", pos)
                text_widget.see(pos)
                
                search_results_label.config(text=f"{current_search_pos[0] + 1}/{len(search_matches)}")
            else:
                search_results_label.config(text="未找到")
            
            if was_disabled:
                text_widget.config(state="disabled")
        
        def find_next():
            find_text("next")
        
        def find_prev():
            find_text("prev")
        
        find_next_button = ttk.Button(search_frame, text="↓", command=find_next, width=3)
        find_next_button.pack(side="left", padx=2)
        
        find_prev_button = ttk.Button(search_frame, text="↑", command=find_prev, width=3)
        find_prev_button.pack(side="left", padx=2)
        
        # 绑定Ctrl+F
        def on_ctrl_f(event):
            search_entry.focus()
            search_entry.select_range(0, "end")
            return "break"
        
        viewer_window.bind("<Control-f>", on_ctrl_f)
        viewer_window.bind("<Control-F>", on_ctrl_f)
        
        # 绑定回车键查找下一个，Shift+Enter查找上一个
        def on_search_enter(event):
            if event.state & 0x1:  # Shift键
                find_prev()
            else:
                find_next()
            return "break"
        
        search_entry.bind("<Return>", on_search_enter)
    
    def show_endings_requirements(self, save_data, endings, collected_endings, missing_endings):
        """显示结局达成条件窗口"""
        # 获取根窗口
        root_window = self.window
        while not isinstance(root_window, tk.Tk) and hasattr(root_window, 'master'):
            root_window = root_window.master
        
        # 创建新窗口
        requirements_window = tk.Toplevel(root_window)
        requirements_window.title(self.t("endings_statistics") + " - " + self.t("view_requirements"))
        requirements_window.geometry("800x600")
        set_window_icon(requirements_window)
        
        # 创建主框架
        main_frame = tk.Frame(requirements_window, bg=Colors.WHITE)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 创建滚动区域
        canvas = tk.Canvas(main_frame, bg=Colors.WHITE)
        scrollable_frame = tk.Frame(canvas, bg=Colors.WHITE)
        
        scrollbar = Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        
        def update_scrollregion(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
        
        scrollable_frame.bind("<Configure>", update_scrollregion)
        
        # 获取所有结局ID（1-45）
        all_ending_ids = [str(i) for i in range(1, 46)]
        
        # 将 missing_endings 转换为集合以便快速查找
        missing_endings_set = set(missing_endings)
        collected_endings_set = set(collected_endings)
        
        # 分离已达成和未达成的结局
        collected_list = []
        missing_list = []
        
        for ending_id in all_ending_ids:
            ending_key = f"END{ending_id}_unlock_cond"
            condition_text = self.t(ending_key)
            
            # 判断是否为未达成的结局
            # 如果结局不在 collected_endings 中，则视为未达成
            if ending_id not in collected_endings_set:
                # 未达成的结局
                missing_list.append((ending_id, condition_text))
            else:
                # 已达成的结局
                collected_list.append((ending_id, condition_text))
        
        # 先显示未达成的结局（突出显示），然后显示已达成的结局
        display_order = missing_list + collected_list
        
        # 创建标题
        title_label = ttk.Label(scrollable_frame, 
                               text=self.t("endings_statistics") + " - " + self.t("view_requirements"),
                               font=get_cjk_font(14, "bold"))
        title_label.pack(anchor="w", pady=(0, 10))
        
        # 如果有未达成的结局，添加提示
        if missing_list:
            hint_label = ttk.Label(scrollable_frame,
                                 text=f"⚠ {self.t('missing_endings')}: {len(missing_list)}",
                                 font=get_cjk_font(11, "bold"),
                                 foreground="red")
            hint_label.pack(anchor="w", pady=(0, 10))
        
        # 显示所有结局
        for ending_id, condition_text in display_order:
            # 创建每个结局的框架
            ending_frame = tk.Frame(scrollable_frame, bg=Colors.WHITE, relief="ridge", borderwidth=1)
            ending_frame.pack(fill="x", pady=5, padx=5)
            
            # 判断是否为未达成的结局
            is_missing = ending_id not in collected_endings_set
            
            # 设置背景色和字体样式
            if is_missing:
                # 未达成的结局：使用浅红色背景，加粗字体
                ending_frame.config(bg="#ffe6e6")
                title_bg = "#ffe6e6"
                title_fg = "red"
                title_font = get_cjk_font(11, "bold")
            else:
                # 已达成的结局：使用浅绿色背景，普通字体
                ending_frame.config(bg="#e6ffe6")
                title_bg = "#e6ffe6"
                title_fg = "green"
                title_font = get_cjk_font(11, "normal")
            
            # 结局标题
            title_frame = tk.Frame(ending_frame, bg=title_bg)
            title_frame.pack(fill="x", padx=5, pady=5)
            
            ending_title = ttk.Label(title_frame, 
                                    text=f"END{ending_id}",
                                    font=title_font,
                                    foreground=title_fg,
                                    background=title_bg)
            ending_title.pack(side="left", padx=5)
            
            # 状态标签
            if is_missing:
                status_label = ttk.Label(title_frame,
                                       text="❌ " + self.t("missing_endings"),
                                       font=get_cjk_font(10, "bold"),
                                       foreground="red",
                                       background=title_bg)
            else:
                status_label = ttk.Label(title_frame,
                                       text="✓ " + self.t("collected_endings"),
                                       font=get_cjk_font(10, "normal"),
                                       foreground="green",
                                       background=title_bg)
            status_label.pack(side="right", padx=5)
            
            # 达成条件文本
            condition_frame = tk.Frame(ending_frame, bg=title_bg)
            condition_frame.pack(fill="x", padx=10, pady=(0, 5))
            
            wraplength = 700
            condition_label = ttk.Label(condition_frame,
                                        text=condition_text,
                                        font=get_cjk_font(10),
                                        wraplength=wraplength,
                                        justify="left",
                                        background=title_bg)
            condition_label.pack(anchor="w", padx=5)
        
        # 布局滚动条和画布
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 绑定鼠标滚轮
        def on_mousewheel(event):
            try:
                if event.delta:
                    canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                else:
                    if event.num == 4:
                        canvas.yview_scroll(-1, "units")
                    elif event.num == 5:
                        canvas.yview_scroll(1, "units")
            except:
                pass
        
        canvas.bind("<MouseWheel>", on_mousewheel)
        canvas.bind("<Button-4>", on_mousewheel)
        canvas.bind("<Button-5>", on_mousewheel)
        
        # 更新滚动区域
        requirements_window.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))

