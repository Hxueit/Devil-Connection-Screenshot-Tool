"""
用于sf.sav存档文件有更改的时候右下角弹窗
"""
import tkinter as tk
import platform


class Toast:
    
    # 类变量：存储所有活跃的toast实例
    _active_toasts = []
    _toast_spacing = 10  # toast之间的间距（像素）
    
    def __init__(self, root, message, duration=10000, fade_in=200, fade_out=200, y_offset=None):
        """
        创建通知
        
        Args:
            root: 根窗口
            message: 通知消息
            duration: 显示持续时间（毫秒，不包括动画时间）
            fade_in: 淡入动画时间（毫秒）
            fade_out: 淡出动画时间（毫秒）
            y_offset: Y轴偏移量（从底部算起），如果为None则自动计算
        """
        self.root = root
        self.message = message
        self.duration = duration
        self.fade_in = fade_in
        self.fade_out = fade_out
        self.y_offset = y_offset
        
        # 创建通知窗口
        self.window = tk.Toplevel(root)
        self.window.title("")
        self.window.overrideredirect(True)  # 移除标题栏
        self.window.attributes("-topmost", True)  # 置顶，确保全屏模式下也能显示
        
        # 设置窗口样式（深色半透明背景）
        self.window.configure(bg="#1a1a1a")
        
        # 获取屏幕尺寸
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        
        # 设置窗口宽度（固定）
        window_width = 280
        
        # 设置初始透明度（Windows 支持）
        self.supports_alpha = False
        if platform.system() == "Windows":
            try:
                self.window.attributes("-alpha", 0.0)
                self.supports_alpha = True
            except:
                self.supports_alpha = False
        
        # 创建内容框架
        content_frame = tk.Frame(self.window, bg="#1a1a1a")
        content_frame.pack(fill="x", padx=10, pady=8)
        
        # 使用Text widget以支持彩色文本
        font_name = "Microsoft YaHei" if platform.system() == "Windows" else "Arial"
        message_text = tk.Text(
            content_frame,
            font=(font_name, 9),
            fg="#b0b0b0",  # 浅灰色，不显眼（默认颜色）
            bg="#1a1a1a",
            wrap="word",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            padx=0,
            pady=0,
            state="disabled",  # 禁用编辑
            width=window_width // 7  # 估算宽度（字符数）
        )
        message_text.pack(anchor="nw", fill="x")
        
        # 配置颜色标签
        message_text.tag_configure("green", foreground="#4ade80")  # 绿色
        message_text.tag_configure("red", foreground="#f87171")    # 红色
        message_text.tag_configure("default", foreground="#b0b0b0") # 默认灰色
        
        # 解析消息并应用颜色
        self._insert_colored_text(message_text, message)
        
        # 更新窗口以获取实际内容高度
        self.window.update_idletasks()
        
        # 计算实际需要的高度（使用bbox获取最后一行文本的位置）
        try:
            # 获取最后一行文本的边界框（使用"end-1c"获取最后一个字符的位置）
            bbox = message_text.bbox("end-1c")
            if bbox:
                # bbox返回 (x, y, width, height)
                # y是最后一行文本的顶部位置，height是该行的高度
                # 需要加上该行的高度才是实际内容高度
                last_line_height = bbox[3] if bbox[3] > 0 else 15
                content_height = bbox[1] + last_line_height
            else:
                # 如果bbox返回None（可能内容为空），使用行数估算
                end_index = message_text.index("end-1c")
                line_count = int(end_index.split(".")[0])
                # 估算每行高度（考虑字体大小9和行间距）
                line_height = 15
                content_height = max(line_count * line_height, 20)
        except:
            # 如果获取bbox失败，使用行数估算
            try:
                end_index = message_text.index("end-1c")
                line_count = int(end_index.split(".")[0])
                content_height = max(line_count * 15, 20)
            except:
                # 最后的备选方案：使用reqheight，但限制最大值
                content_height = message_text.winfo_reqheight()
                if content_height <= 0:
                    content_height = 50
        
        padding = 16  # 上下padding
        window_height = content_height + padding
        
        # 限制最大高度（不超过屏幕高度的80%）
        max_height = int(screen_height * 0.8)
        if window_height > max_height:
            window_height = max_height
        
        # 确保最小高度
        min_height = 50
        if window_height < min_height:
            window_height = min_height
        
        # 存储窗口高度，用于后续计算位置
        self.window_height = window_height
        
        # 计算Y位置
        if self.y_offset is None:
            # 如果没有指定偏移，计算应该放置的位置
            # 检查是否有其他活跃的toast
            active_toasts = [toast for toast in Toast._active_toasts if toast.window.winfo_exists()]
            if active_toasts:
                # 计算所有toast的总高度（包括间距）
                total_height = sum(toast.window_height + Toast._toast_spacing 
                                 for toast in active_toasts)
                # 新toast放在最上方（y_offset最大）
                y_offset = total_height
            else:
                # 没有其他toast，从底部开始
                y_offset = 0
            self.y_offset = y_offset
        
        # 计算右下角位置
        x = screen_width - window_width - 15  # 距离右边缘15像素
        y = screen_height - window_height - 15 - self.y_offset  # 距离下边缘15像素，加上偏移
        
        self.window.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        # 添加到活跃列表
        Toast._active_toasts.append(self)
        
        # 启动动画
        self._animate()
    
    def _insert_colored_text(self, text_widget, message):
        """插入带颜色的文本到Text widget"""
        text_widget.config(state="normal")  # 临时启用编辑
        text_widget.delete("1.0", "end")  # 清空内容
        
        lines = message.split("\n")
        for line_idx, line in enumerate(lines):
            if line_idx > 0:
                text_widget.insert("end", "\n")
            
            # 检查是否以+或-开头（可能后面有空格）
            if line.strip().startswith("+"):
                # + 开头：将+标记为绿色，其余为默认色
                # 找到第一个+的位置
                plus_pos = line.find("+")
                if plus_pos >= 0:
                    text_widget.insert("end", line[:plus_pos], "default")
                    text_widget.insert("end", "+", "green")
                    remaining = line[plus_pos + 1:]
                    if remaining:
                        text_widget.insert("end", remaining, "default")
                else:
                    text_widget.insert("end", line, "default")
            elif line.strip().startswith("-"):
                # - 开头：将-标记为红色，其余为默认色
                # 找到第一个-的位置
                minus_pos = line.find("-")
                if minus_pos >= 0:
                    text_widget.insert("end", line[:minus_pos], "default")
                    text_widget.insert("end", "-", "red")
                    remaining = line[minus_pos + 1:]
                    if remaining:
                        text_widget.insert("end", remaining, "default")
                else:
                    text_widget.insert("end", line, "default")
            elif ".append(" in line:
                # 包含.append(：将.append(标记为绿色
                parts = line.split(".append(")
                text_widget.insert("end", parts[0], "default")
                text_widget.insert("end", ".append(", "green")
                if len(parts) > 1:
                    text_widget.insert("end", parts[1], "default")
            elif ".remove(" in line:
                # 包含.remove(：将.remove(标记为红色
                parts = line.split(".remove(")
                text_widget.insert("end", parts[0], "default")
                text_widget.insert("end", ".remove(", "red")
                if len(parts) > 1:
                    text_widget.insert("end", parts[1], "default")
            else:
                # 其他情况：默认颜色
                text_widget.insert("end", line, "default")
        
        text_widget.config(state="disabled")  # 重新禁用编辑
    
    def _animate(self):
        """执行淡入-等待-淡出动画"""
        # 淡入动画
        self._fade_in(0.0, 0.85, self.fade_in, 0)
    
    def _fade_in(self, start_alpha, end_alpha, duration, step):
        """淡入动画"""
        if not self.window.winfo_exists():
            return
        
        steps = max(1, duration // 16)  # 约60fps
        alpha_step = (end_alpha - start_alpha) / steps
        
        if step < steps:
            current_alpha = start_alpha + alpha_step * step
            if self.supports_alpha:
                try:
                    self.window.attributes("-alpha", current_alpha)
                except:
                    pass
            self.window.after(16, lambda: self._fade_in(start_alpha, end_alpha, duration, step + 1))
        else:
            # 淡入完成，设置最终透明度
            if self.supports_alpha:
                try:
                    self.window.attributes("-alpha", end_alpha)
                except:
                    pass
            # 等待指定时间后开始淡出
            self.window.after(self.duration, self._start_fade_out)
    
    def _start_fade_out(self):
        """开始淡出动画"""
        if not self.window.winfo_exists():
            return
        
        current_alpha = 0.85
        if self.supports_alpha:
            try:
                current_alpha = self.window.attributes("-alpha")
            except:
                current_alpha = 0.85
        
        self._fade_out(current_alpha, 0.0, self.fade_out, 0)
    
    def _fade_out(self, start_alpha, end_alpha, duration, step):
        """淡出动画"""
        if not self.window.winfo_exists():
            return
        
        steps = max(1, duration // 16)  # 约60fps
        alpha_step = (end_alpha - start_alpha) / steps
        
        if step < steps:
            current_alpha = start_alpha + alpha_step * step
            if self.supports_alpha:
                try:
                    self.window.attributes("-alpha", current_alpha)
                except:
                    pass
            self.window.after(16, lambda: self._fade_out(start_alpha, end_alpha, duration, step + 1))
        else:
            # 淡出完成，关闭窗口
            if self.window.winfo_exists():
                self.window.destroy()
            # 从活跃列表中移除
            if self in Toast._active_toasts:
                Toast._active_toasts.remove(self)
            # 重新排列剩余的toast
            self._reposition_toasts()
    
    @staticmethod
    def _reposition_toasts():
        """重新排列所有活跃的toast（从底部开始，旧的在下，新的在上）"""
        if not Toast._active_toasts:
            return
        
        # 获取屏幕尺寸
        try:
            root = Toast._active_toasts[0].root
            screen_width = root.winfo_screenwidth()
            screen_height = root.winfo_screenheight()
        except:
            return
        
        # 过滤出仍然存在的toast（保持原有顺序，旧的在前）
        active_toasts = [toast for toast in Toast._active_toasts if toast.window.winfo_exists()]
        Toast._active_toasts = active_toasts
        
        if not active_toasts:
            return
        
        # 从底部开始重新排列（旧的在下，新的在上）
        y_offset = 0
        window_width = 280
        
        for toast in active_toasts:
            x = screen_width - window_width - 15
            y = screen_height - toast.window_height - 15 - y_offset
            try:
                if toast.window.winfo_exists():
                    toast.window.geometry(f"{window_width}x{toast.window_height}+{x}+{y}")
                    toast.y_offset = y_offset
                    y_offset += toast.window_height + Toast._toast_spacing
            except:
                # 如果窗口已销毁，跳过
                continue

