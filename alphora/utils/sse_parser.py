import json
from collections.abc import Iterator
from typing import Any, List, Optional, Union, Dict
import requests


def _flatten_json(obj: Any, parent_key: str = '', sep: str = '.') -> Dict[str, Any]:
    """
    将嵌套 JSON 展平为路径 -> 值 的字典。
    例如: {"a": {"b": "hello"}} -> {"a.b": "hello"}
    注意：数组用 [index] 表示，如 choices[0].delta.content
    """
    items = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_key = f"{parent_key}.{k}" if parent_key else k
            items.extend(_flatten_json(v, new_key, sep).items())
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            new_key = f"{parent_key}[{i}]"
            items.extend(_flatten_json(v, new_key, sep).items())
    else:
        return {parent_key: obj}
    return dict(items)


def _find_common_content_path(samples: List[Dict]) -> Optional[str]:
    """
    从多个 JSON 样本中找出共有的、非空的字符串字段路径，
    优先选择路径名中包含 'content' 的。
    """
    if not samples:
        return None

    # 收集每个样本中所有非空字符串字段的路径
    all_paths_sets = []
    for sample in samples:
        flat = _flatten_json(sample)
        str_paths = {
            path for path, value in flat.items()
            if isinstance(value, str) and value.strip()
        }
        all_paths_sets.append(str_paths)

    if not all_paths_sets:
        return None

    # 求交集：所有样本都包含的路径
    common_paths = set.intersection(*all_paths_sets)
    if not common_paths:
        # 如果没有完全交集，尝试找“多数存在”的路径（至少在 2/3 样本中出现）
        from collections import Counter
        path_counter = Counter()
        for paths in all_paths_sets:
            for p in paths:
                path_counter[p] += 1
        min_support = max(2, len(samples) - 1)  # 至少出现在 n-1 个样本中
        common_paths = {p for p, cnt in path_counter.items() if cnt >= min_support}

    if not common_paths:
        return None

    # 优先选择包含 'content' 的路径（不区分大小写）
    content_paths = [p for p in common_paths if 'content' in p.lower()]
    if content_paths:
        # 选最长的（通常更具体）
        return max(content_paths, key=len)

    # 否则选任意一个（取最长的，避免太泛如 'id'）
    return max(common_paths, key=len)


def _get_value_by_path(obj: Any, path: str) -> Optional[str]:
    """
    根据路径字符串（如 'choices[0].delta.content'）从对象中取值。
    """
    try:
        current = obj
        parts = []
        # 分割路径：支持 . 和 [index]
        raw_parts = path.replace('[', '.[').split('.')
        for part in raw_parts:
            if part == '':
                continue
            if part.startswith('[') and part.endswith(']'):
                idx = int(part[1:-1])
                current = current[idx]
            else:
                current = current[part]
        if isinstance(current, str) and current.strip():
            return current
        return None
    except (KeyError, IndexError, TypeError, ValueError):
        return None


class AdaptiveSSEContentIterator(Iterator):
    def __init__(self, response: requests.Response, warmup_samples: int = 3):
        self._iter_lines = response.iter_lines(decode_unicode=True)
        self._warmup_samples = warmup_samples
        self._buffered_data = []  # 存储前几个 data 块（JSON 对象）
        self._content_path = None
        self._warmup_done = False
        self._data_queue = []  # 预读的数据，用于 warmup 后消费

    def __iter__(self):
        return self

    def __next__(self) -> str:
        if not self._warmup_done:
            self._perform_warmup()

        # 消费预读队列
        while self._data_queue:
            item = self._data_queue.pop(0)
            if item == '[DONE]':
                raise StopIteration
            if isinstance(item, str):
                # 非 JSON 或无法提取，直接返回
                return item
            elif isinstance(item, dict):
                if self._content_path:
                    content = _get_value_by_path(item, self._content_path)
                    if content is not None:
                        return content
                # fallback: 返回整个 data 字符串？
                return json.dumps(item)

        # 继续读新行
        while True:
            try:
                line = next(self._iter_lines)
            except StopIteration:
                raise StopIteration

            if not line or line.startswith(':'):
                continue

            if line.startswith('data:'):
                payload = line[len('data:'):].strip()
                if payload == '[DONE]':
                    raise StopIteration

                # 尝试解析 JSON
                try:
                    json_obj = json.loads(payload)
                    if self._content_path:
                        content = _get_value_by_path(json_obj, self._content_path)
                        if content is not None:
                            return content
                        else:
                            # 无法提取，但继续流
                            return json.dumps(json_obj)
                    else:
                        # 理论上不会到这里（warmup 已完成）
                        return payload
                except json.JSONDecodeError:
                    return payload

    def _perform_warmup(self):
        """读取前几个有效 data 块，推断 content 路径"""
        samples = []
        raw_datas = []

        while len(samples) < self._warmup_samples:
            try:
                line = next(self._iter_lines)
            except StopIteration:
                break

            if not line or line.startswith(':'):
                continue

            if line.startswith('data:'):
                payload = line[len('data:'):].strip()
                if payload == '[DONE]':
                    self._data_queue.append('[DONE]')
                    break

                raw_datas.append(payload)
                try:
                    json_obj = json.loads(payload)
                    samples.append(json_obj)
                except json.JSONDecodeError:
                    # 非 JSON，无法学习结构，直接放入队列
                    self._data_queue.append(payload)

        # 推断路径
        if samples:
            self._content_path = _find_common_content_path(samples)
            # 把 samples 转为 dict 放入队列供后续消费
            for s in samples:
                self._data_queue.append(s)
        else:
        # 全是非 JSON，全部已入队

        # 把剩余 raw_datas 中未处理的（非 JSON）也入队
        # （实际上上面已经处理了）

        self._warmup_done = True


def parse_adaptive_sse_stream(
        response: requests.Response,
        warmup_samples: int = 3
) -> AdaptiveSSEContentIterator:
    """
    自适应解析 SSE 流：接收前几个块后自动推断 content 提取路径。

    参数:
        response: requests.Response 对象（需 stream=True）
        warmup_samples: 用于推断结构的样本数（默认 3）

    返回:
        一个可迭代对象，for 循环即可获得 content 字符串。
    """
    return AdaptiveSSEContentIterator(response, warmup_samples=warmup_samples)