import json
import os
from typing import List, Dict, Any, Optional, TypeVar, Generic, Type
from datetime import datetime
from pathlib import Path
from pydantic import BaseModel

# 定义泛型类型变量
T = TypeVar('T', bound=BaseModel)

class JSONStorage(Generic[T]):
    """JSON文件存储服务，用于存储数据模型"""
    
    def __init__(self, file_path: Path, model_class: Type[T]):
        """
        初始化JSON存储
        
        Args:
            file_path: JSON文件路径
            model_class: 数据模型类
        """
        self.file_path = file_path
        self.model_class = model_class
        
        # 确保目录存在
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # 如果文件不存在，创建空的JSON文件
        if not os.path.exists(file_path):
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False)
    
    def _read_all(self) -> List[Dict[str, Any]]:
        """读取所有数据"""
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []
    
    def _write_all(self, data: List[Dict[str, Any]]) -> None:
        """写入所有数据"""
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, default=self._json_serial)
    
    def _json_serial(self, obj):
        """处理JSON序列化中的特殊对象"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Type {type(obj)} not serializable")
    
    def get_all(self) -> List[T]:
        """获取所有记录"""
        data = self._read_all()
        return [self.model_class.parse_obj(item) for item in data]
    
    def get_by_id(self, id: str) -> Optional[T]:
        """根据ID获取单个记录"""
        data = self._read_all()
        for item in data:
            if item.get('id') == id:
                return self.model_class.parse_obj(item)
        return None
    
    def get_by_field(self, field: str, value: Any) -> List[T]:
        """根据字段值获取记录"""
        data = self._read_all()
        result = []
        for item in data:
            if item.get(field) == value:
                result.append(self.model_class.parse_obj(item))
        return result
    
    def create(self, item: T) -> T:
        """创建新记录"""
        data = self._read_all()
        item_dict = item.dict()
        data.append(item_dict)
        self._write_all(data)
        return item
    
    def update(self, id: str, item: T) -> Optional[T]:
        """更新记录"""
        data = self._read_all()
        item_dict = item.dict()
        
        for i, existing_item in enumerate(data):
            if existing_item.get('id') == id:
                # 更新更新时间
                if hasattr(item, 'updated_at'):
                    item_dict['updated_at'] = datetime.utcnow().isoformat()
                
                data[i] = item_dict
                self._write_all(data)
                return item
        
        return None
    
    def update_partial(self, id: str, update_data: Dict[str, Any]) -> Optional[T]:
        """部分更新记录"""
        data = self._read_all()
        
        for i, item in enumerate(data):
            if item.get('id') == id:
                # 更新字段
                for key, value in update_data.items():
                    if key in item:
                        item[key] = value
                
                # 更新更新时间
                item['updated_at'] = datetime.utcnow().isoformat()
                
                self._write_all(data)
                return self.model_class.parse_obj(item)
        
        return None
    
    def delete(self, id: str) -> bool:
        """删除记录"""
        data = self._read_all()
        initial_length = len(data)
        
        data = [item for item in data if item.get('id') != id]
        
        if len(data) < initial_length:
            self._write_all(data)
            return True
        
        return False 