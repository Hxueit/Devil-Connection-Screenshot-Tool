"""
窗口模块
包含画廊预览窗口和结局条件窗口
"""
import dearpygui.dearpygui as dpg
from typing import List, Dict, Optional, Set
from dpg_helpers import get_i18n, load_image_from_sav, numpy_to_texture_id, resize_image, load_image_async
import os
import numpy as np


class GalleryWindow:
    """
    画廊预览窗口
    按照3行4列的方式排列图片，每页12张
    """
    def __init__(self, storage_dir: str, ids_data: List[Dict], sav_pairs: Dict):
        """
        Args:
            storage_dir: 存储目录
            ids_data: 图片ID数据列表
            sav_pairs: sav文件对字典 {id: (main_sav, thumb_sav)}
        """
        self.storage_dir = storage_dir
        self.ids_data = ids_data
        self.sav_pairs = sav_pairs
        self.i18n = get_i18n()
        
        # 布局参数
        self.rows_per_group = 3
        self.cols_per_group = 4
        self.images_per_group = self.rows_per_group * self.cols_per_group  # 12
        
        # 图片尺寸
        self.image_width = 150
        self.image_height = 112
        
        # 存储图片纹理ID {id_str: texture_id}
        self.texture_cache: Dict[str, int] = {}
        
        # 占位符映射 {id_str: placeholder_id}
        self.placeholders: Dict[str, int] = {}
        
        # 创建窗口
        self.create_window()
    
    def create_window(self):
        """创建画廊窗口"""
        # 获取所有图片ID（按照ids_data的顺序）
        image_ids = [item['id'] for item in self.ids_data]
        total_images = len(image_ids)
        
        # 计算总组数
        num_groups = (total_images + self.images_per_group - 1) // self.images_per_group
        
        # 创建窗口
        with dpg.window(
            label=self.i18n.t("gallery_preview", default="画廊预览"),
            width=1000,
            height=700,
            tag="gallery_window",
            no_close=False,
            parent=0  # 明确指定为顶级窗口，确保独立显示
        ):
            # 创建可滚动区域
            with dpg.child_window(
                tag="gallery_scroll_area",
                width=-1,
                height=-1
            ):
                # 为每个组创建显示区域
                for group_idx in range(num_groups):
                    # 创建组框架
                    with dpg.group(tag=f"group_{group_idx}", horizontal=False):
                        # 创建3行4列的网格
                        for row in range(self.rows_per_group):
                            with dpg.group(tag=f"group_{group_idx}_row_{row}", horizontal=True):
                                for col in range(self.cols_per_group):
                                    # 计算图片索引：对于第row行，第col列
                                    # 索引 = group_idx * 12 + row * 4 + col
                                    image_idx = group_idx * self.images_per_group + row * self.cols_per_group + col
                                    
                                    if image_idx < total_images:
                                        id_str = image_ids[image_idx]
                                        # 创建占位符
                                        self._create_placeholder(id_str, f"group_{group_idx}_row_{row}")
                                    else:
                                        # 空白占位，显示N/A
                                        self._create_empty_placeholder(f"group_{group_idx}_row_{row}")
                        
                        # 在每页下面显示页面编号
                        dpg.add_text(
                            f"{self.i18n.t('page', default='页面')} {group_idx + 1}",
                            tag=f"page_label_{group_idx}",
                            color=[200, 200, 200, 255]  # 浅灰色文字（深色主题）
                        )
        
        # 异步加载所有图片
        self._load_images_async(image_ids)
    
    def _create_placeholder(self, id_str: str, parent_tag: str):
        """创建加载中的占位符"""
        placeholder_group_id = dpg.add_group(parent=parent_tag, tag=f"placeholder_{id_str}")
        # 占位符容器
        placeholder_id = dpg.add_text(
            "Loading...",
            parent=placeholder_group_id,
            tag=f"placeholder_text_{id_str}",
            color=[200, 200, 200, 255]  # 浅灰色文字（深色主题）
        )
        self.placeholders[id_str] = placeholder_id
        
        # ID标签
        dpg.add_text(
            id_str,
            parent=placeholder_group_id,
            tag=f"placeholder_id_{id_str}",
            color=[200, 200, 200, 255]  # 浅灰色文字（深色主题）
        )
    
    def _create_empty_placeholder(self, parent_tag: str):
        """创建空白占位符（N/A）"""
        empty_group_id = dpg.add_group(parent=parent_tag)
        dpg.add_text(
            self.i18n.t("not_available", default="N/A"),
            parent=empty_group_id,
            color=[200, 200, 200, 255]  # 浅灰色文字（深色主题）
        )
        dpg.add_text("", parent=empty_group_id, color=[255, 255, 255, 0])  # 空白占位
    
    def _load_images_async(self, image_ids: List[str]):
        """异步加载所有图片"""
        def load_func(id_str):
            """加载函数"""
            if id_str not in self.sav_pairs:
                return None
            
            main_file = self.sav_pairs[id_str][0]
            if not main_file:
                return None
            
            main_sav = os.path.join(self.storage_dir, main_file)
            if not os.path.exists(main_sav):
                return None
            
            # 加载图片
            image_data = load_image_from_sav(main_sav, cache_key=id_str)
            if image_data is not None:
                # 调整大小
                resized = resize_image(image_data, self.image_width, self.image_height)
                return resized
            return None
        
        def on_loaded(key: str, image_data):
            """图片加载完成回调"""
            if key not in self.placeholders:
                return
            
            if image_data is None:
                # 加载失败
                placeholder_id = self.placeholders[key]
                if dpg.does_item_exist(placeholder_id):
                    dpg.set_value(placeholder_id, self.i18n.t("preview_failed", default="加载失败"))
                    dpg.configure_item(placeholder_id, color=[255, 0, 0, 255])
                return
            
            # 转换为纹理
            # image_data应该是numpy数组（RGBA, 0-1范围）
            if isinstance(image_data, np.ndarray):
                texture_id = numpy_to_texture_id(image_data)
            else:
                return
            
            if texture_id:
                self.texture_cache[key] = texture_id
                
                # 更新UI：移除占位符，显示图片
                placeholder_group = f"placeholder_{key}"
                if dpg.does_item_exist(placeholder_group):
                    # 获取父容器
                    parent_tag = dpg.get_item_parent(placeholder_group)
                    # 删除占位符
                    dpg.delete_item(placeholder_group)
                    
                    # 创建图片显示
                    if parent_tag:
                        image_group_id = dpg.add_group(parent=parent_tag, tag=f"image_group_{key}")
                        dpg.add_image(
                            texture_tag=texture_id,
                            parent=image_group_id,
                            width=self.image_width,
                            height=self.image_height,
                            tag=f"image_{key}"
                        )
                        dpg.add_text(
                            key,
                            parent=image_group_id,
                            tag=f"image_id_{key}",
                            color=[255, 255, 255, 255]  # 白色文字（深色主题）
                        )
        
        # 异步加载所有图片
        for id_str in image_ids:
            load_image_async(
                lambda i=id_str: load_func(i),
                on_loaded,
                id_str
            )
    
    def close(self):
        """关闭窗口并清理资源"""
        # 清理纹理
        for texture_id in self.texture_cache.values():
            if dpg.does_item_exist(texture_id):
                try:
                    dpg.delete_item(texture_id)
                except:
                    pass
        
        # 删除窗口
        if dpg.does_item_exist("gallery_window"):
            dpg.delete_item("gallery_window")


class EndingsWindow:
    """结局条件窗口"""
    
    def __init__(self, endings: Set[str], collected_endings: Set[str], missing_endings: List[str]):
        """
        Args:
            endings: 所有结局ID集合
            collected_endings: 已收集的结局ID集合
            missing_endings: 未收集的结局ID列表
        """
        self.i18n = get_i18n()
        self.endings = endings
        self.collected_endings = collected_endings
        self.missing_endings = missing_endings
        
        self.create_window()
    
    def create_window(self):
        """创建窗口"""
        with dpg.window(
            label=self.i18n.t("endings_statistics", default="结局统计") + " - " + self.i18n.t("view_requirements", default="查看达成条件"),
            width=800,
            height=600,
            tag="endings_window",
            no_close=False,
            parent=0  # 明确指定为顶级窗口，确保独立显示
        ):
            # 标题
            dpg.add_text(
                self.i18n.t("endings_statistics", default="结局统计") + " - " + self.i18n.t("view_requirements", default="查看达成条件"),
                color=[255, 255, 255, 255]
            )
            
            # 提示
            if self.missing_endings:
                dpg.add_text(
                    f"⚠ {self.i18n.t('missing_endings', default='未收集')}: {len(self.missing_endings)}",
                    color=[255, 0, 0, 255]
                )
            
            # 可滚动区域
            with dpg.child_window(tag="endings_scroll_area", width=-1, height=-1):
                # 获取所有结局ID（1-45）
                all_ending_ids = [str(i) for i in range(1, 46)]
                collected_endings_set = set(self.collected_endings)
                
                # 分离已达成和未达成的结局
                collected_list = []
                missing_list = []
                
                for ending_id in all_ending_ids:
                    ending_key = f"END{ending_id}_unlock_cond"
                    condition_text = self.i18n.t(ending_key, default=f"END{ending_id} 达成条件")
                    
                    if ending_id not in collected_endings_set:
                        missing_list.append((ending_id, condition_text))
                    else:
                        collected_list.append((ending_id, condition_text))
                
                # 先显示未达成的，再显示已达成的
                display_order = missing_list + collected_list
                
                # 显示所有结局
                for ending_id, condition_text in display_order:
                    is_missing = ending_id not in collected_endings_set
                    
                    # 创建结局卡片
                    with dpg.group(tag=f"ending_{ending_id}"):
                        # 标题行
                        with dpg.group(horizontal=True):
                            # 结局标题
                            title_color = [255, 0, 0, 255] if is_missing else [0, 255, 0, 255]
                            dpg.add_text(f"END{ending_id}", color=title_color)
                            
                            # 状态标签
                            if is_missing:
                                status_text = "❌ " + self.i18n.t("missing_endings", default="未收集")
                                status_color = [255, 0, 0, 255]
                            else:
                                status_text = "✓ " + self.i18n.t("collected_endings", default="已收集")
                                status_color = [0, 255, 0, 255]
                            
                            dpg.add_text(status_text, color=status_color)
                        
                        # 达成条件文本
                        dpg.add_text(condition_text, wrap=700, color=[200, 200, 200, 255])
                        
                        # 分隔线
                        dpg.add_separator()

