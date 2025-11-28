import os
import zipfile
import shutil
from datetime import datetime
import tempfile
import random

# 版本常量
VERSION = "0.3.0"

class BackupRestore:
    def __init__(self, storage_dir):
        """
        初始化备份/还原管理器
        
        Args:
            storage_dir: _storage文件夹的路径
        """
        self.storage_dir = storage_dir
    
    def get_backup_dir(self):
        """
        获取备份目录路径（不自动创建）
        
        Returns:
            备份目录的绝对路径
        """
        if not self.storage_dir:
            return None
        
        # 获取_storage的父目录
        parent_dir = os.path.dirname(self.storage_dir)
        backup_dir = os.path.join(parent_dir, "dcsm_backups")
        
        return os.path.abspath(backup_dir)
    
    def format_size(self, size_bytes):
        """
        格式化文件大小为可读格式
        
        Args:
            size_bytes: 文件大小（字节）
        
        Returns:
            格式化后的字符串（如 "1.5 MB"）
        """
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.2f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.2f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
    
    def estimate_compressed_size(self, storage_dir):
        """
        估算压缩后的大小
        
        Args:
            storage_dir: _storage文件夹路径
        
        Returns:
            估算的大小（字节），如果失败返回None
        """
        if not os.path.exists(storage_dir):
            return None
        
        try:
            # 收集所有文件路径
            all_files = []
            total_size = 0
            
            for root, dirs, files in os.walk(storage_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        file_size = os.path.getsize(file_path)
                        all_files.append((file_path, file_size))
                        total_size += file_size
                    except Exception:
                        # 如果无法获取文件大小，跳过该文件
                        continue
            
            if not all_files:
                return 0
            
            # 选择前10%的文件进行实际压缩测试
            sample_count = max(1, len(all_files) // 10)
            sample_files = all_files[:sample_count]
            sample_total_size = sum(size for _, size in sample_files)
            
            # 创建临时zip文件进行压缩测试
            # 使用mkstemp避免Windows上的文件锁定问题
            temp_fd, temp_zip_path = tempfile.mkstemp(suffix='.zip')
            compressed_sample_size = None
            try:
                os.close(temp_fd)  # 关闭文件描述符，让ZipFile自己打开
                with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=7) as test_zip:
                    for file_path, _ in sample_files:
                        try:
                            # 计算相对路径
                            rel_path = os.path.relpath(file_path, storage_dir)
                            test_zip.write(file_path, rel_path)
                        except Exception:
                            # 如果某个文件无法读取，跳过它
                            continue
                
                # 获取压缩后的大小（确保ZipFile已关闭）
                if os.path.exists(temp_zip_path):
                    compressed_sample_size = os.path.getsize(temp_zip_path)
            finally:
                # 清理临时文件
                try:
                    if os.path.exists(temp_zip_path):
                        os.remove(temp_zip_path)
                except Exception:
                    pass
            
            # 计算压缩比
            if compressed_sample_size is not None and sample_total_size > 0:
                compression_ratio = compressed_sample_size / sample_total_size
            else:
                # 如果无法获取压缩大小或样本总大小为0，使用默认压缩比
                compression_ratio = 0.7  # 默认压缩比
            
            # 估算总大小
            estimated_size = int(total_size * compression_ratio)
            return estimated_size
            
        except Exception:
            return None
    
    def create_backup(self, storage_dir, progress_callback=None):
        """
        创建备份
        
        Args:
            storage_dir: _storage文件夹路径
            progress_callback: 进度回调函数，接收 (current, total) 参数
        
        Returns:
            (备份文件路径, 实际大小, 绝对路径) 或 None（如果失败）
        """
        if not os.path.exists(storage_dir):
            return None
        
        backup_dir = self.get_backup_dir()
        if not backup_dir:
            return None
        
        # 如果备份目录不存在，创建它
        if not os.path.exists(backup_dir):
            try:
                os.makedirs(backup_dir)
            except OSError:
                return None
        
        try:
            # 生成文件名
            now = datetime.now()
            filename = f"DC_storage_backup_{now.strftime('%Y%m%d_%H%M%S')}.zip"
            backup_path = os.path.join(backup_dir, filename)
            
            # 先收集所有文件，用于计算进度
            all_files = []
            for root, dirs, files in os.walk(storage_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    all_files.append(file_path)
            
            total_files = len(all_files) + 1  # +1 for INFO file
            
            # 创建临时目录用于存放INFO文件
            with tempfile.TemporaryDirectory() as temp_dir:
                info_file_path = os.path.join(temp_dir, "dcsmINFO.txt")
                
                # 写入INFO文件
                timestamp_str = now.strftime('%Y-%m-%d %H:%M:%S')
                with open(info_file_path, 'w', encoding='utf-8') as f:
                    f.write(f"{timestamp_str}\n")
                    f.write("This backup .zip was created using https://github.com/Hxueit/Devil-Connection-Sav-Manager/\n")
                    f.write(f"ver:{VERSION}\n")
                
                # 创建zip文件
                current = 0
                with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=7) as zipf:
                    # 添加INFO文件
                    zipf.write(info_file_path, "dcsmINFO.txt")
                    current += 1
                    if progress_callback:
                        progress_callback(current, total_files)
                    
                    # 添加_storage文件夹中的所有文件
                    for file_path in all_files:
                        try:
                            # 计算相对路径（相对于storage_dir）
                            rel_path = os.path.relpath(file_path, storage_dir)
                            zipf.write(file_path, rel_path)
                            current += 1
                            if progress_callback:
                                progress_callback(current, total_files)
                        except Exception:
                            # 如果某个文件无法读取，跳过它
                            continue
                
                # 获取实际大小
                actual_size = os.path.getsize(backup_path)
                abs_path = os.path.abspath(backup_path)
                
                return (backup_path, actual_size, abs_path)
                
        except Exception:
            return None
    
    def scan_backups(self, backup_dir):
        """
        扫描备份目录，返回备份列表
        
        Args:
            backup_dir: 备份目录路径
        
        Returns:
            备份列表：[(zip_path, timestamp, has_info, file_size), ...]
            按时间戳排序（有INFO的在前，按时间倒序；无INFO的在后）
        """
        if not os.path.exists(backup_dir):
            return []
        
        backups = []
        
        try:
            # 扫描所有zip文件
            for filename in os.listdir(backup_dir):
                if filename.endswith('.zip'):
                    zip_path = os.path.join(backup_dir, filename)
                    
                    if not os.path.isfile(zip_path):
                        continue
                    
                    file_size = os.path.getsize(zip_path)
                    timestamp = None
                    has_info = False
                    
                    # 尝试读取INFO文件
                    try:
                        with zipfile.ZipFile(zip_path, 'r') as zipf:
                            if 'dcsmINFO.txt' in zipf.namelist():
                                has_info = True
                                # 读取第一行时间戳
                                with zipf.open('dcsmINFO.txt') as info_file:
                                    first_line = info_file.readline().decode('utf-8').strip()
                                    try:
                                        # 解析时间戳
                                        timestamp = datetime.strptime(first_line, '%Y-%m-%d %H:%M:%S')
                                    except ValueError:
                                        timestamp = None
                    except Exception:
                        pass
                    
                    backups.append((zip_path, timestamp, has_info, file_size))
            
            # 排序：有INFO的在前（按时间倒序），无INFO的在后
            backups_with_info = [(p, t, h, s) for p, t, h, s in backups if h and t is not None]
            backups_without_info = [(p, t, h, s) for p, t, h, s in backups if not h or t is None]
            
            # 有INFO的按时间倒序排序
            backups_with_info.sort(key=lambda x: x[1], reverse=True)
            
            # 合并列表
            return backups_with_info + backups_without_info
            
        except Exception:
            return []
    
    def check_required_files(self, zip_path):
        """
        检查zip文件中是否包含必需文件
        
        Args:
            zip_path: zip文件路径
        
        Returns:
            缺失文件列表，如果都存在则返回空列表
        """
        required_files = ['DevilConnection_sf.sav', 'DevilConnection_tyrano_data.sav']
        missing_files = []
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zipf:
                file_list = zipf.namelist()
                for required_file in required_files:
                    if required_file not in file_list:
                        missing_files.append(required_file)
        except Exception:
            # 如果无法打开zip，认为所有文件都缺失
            return required_files
        
        return missing_files
    
    def restore_backup(self, zip_path, storage_dir):
        """
        还原备份
        
        Args:
            zip_path: 备份zip文件路径
            storage_dir: _storage文件夹路径
        
        Returns:
            True if successful, False otherwise
        """
        if not os.path.exists(zip_path):
            return False
        
        try:
            # 删除_storage目录中的所有现有文件
            if os.path.exists(storage_dir):
                for root, dirs, files in os.walk(storage_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        try:
                            os.remove(file_path)
                        except Exception:
                            pass
                    for dir_name in dirs:
                        dir_path = os.path.join(root, dir_name)
                        try:
                            shutil.rmtree(dir_path)
                        except Exception:
                            pass
            
            # 解压zip文件
            with zipfile.ZipFile(zip_path, 'r') as zipf:
                # 解压所有文件
                for member in zipf.namelist():
                    # 跳过INFO文件
                    if member == 'dcsmINFO.txt':
                        continue
                    
                    # 解压文件
                    zipf.extract(member, storage_dir)
            
            return True
            
        except Exception:
            return False
    
    def delete_backup(self, zip_path):
        """
        删除备份文件，如果备份目录为空则删除目录
        
        Args:
            zip_path: 备份zip文件路径
        
        Returns:
            True if successful, False otherwise
        """
        if not os.path.exists(zip_path):
            return False
        
        try:
            # 获取备份目录
            backup_dir = os.path.dirname(zip_path)
            
            # 删除备份文件
            os.remove(zip_path)
            
            # 检查备份目录是否为空
            if os.path.exists(backup_dir):
                try:
                    # 检查目录中是否还有其他文件
                    remaining_files = os.listdir(backup_dir)
                    if not remaining_files:
                        # 目录为空，删除目录
                        os.rmdir(backup_dir)
                except Exception:
                    # 如果无法删除目录，忽略错误（可能还有其他文件）
                    pass
            
            return True
            
        except Exception:
            return False

