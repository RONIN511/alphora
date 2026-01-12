import json
import re
from typing import Iterator, AsyncIterator, List, Union, Any
from json_repair import repair_json
from alphora.models.llms.stream_helper import BaseGenerator, GeneratorOutput
from alphora.postprocess.base_pp import BasePostProcessor


class JsonKeyExtractorPP(BasePostProcessor):
    """
    流式 JSON key 提取后处理器

    功能：
    - 从流式 JSON 输出中提取指定 key 的值
    - 支持嵌套路径: "data.product.desc"
    - 支持数组索引: "items[0].name"
    - 支持多 key 提取: ["title", "content"]

    输出模式（output_mode）：
    - "target_only"（默认）: 只输出提取的目标值，丢弃原始 JSON
    - "raw_only": 只输出原始 JSON，不提取（相当于透传）
    - "both": 流式输出目标值，响应返回原始 JSON

    使用示例:
        # 单个 key，只输出目标值
        pp = JsonKeyExtractorPP(target_key="analysis")

        # 嵌套 key
        pp = JsonKeyExtractorPP(target_key="data.result.content")

        # 多个 key（用分隔符连接）
        pp = JsonKeyExtractorPP(target_keys=["title", "content"], separator="\\n---\\n")

        # 流式显示目标值，但响应返回原始 JSON
        pp = JsonKeyExtractorPP(target_key="content", output_mode="both")
    """

    def __init__(
            self,
            target_key: str = None,
            target_keys: List[str] = None,
            separator: str = "\n",
            content_type: str = "text",
            output_mode: str = "both",  # "target_only" | "raw_only" | "both"
    ):
        """
        Args:
            target_key: 单个目标 key（支持嵌套路径如 "a.b.c" 或 "a[0].b"）
            target_keys: 多个目标 key 列表
            separator: 多 key 时的分隔符
            content_type: 输出的 content_type
            output_mode: 输出模式
                - "target_only": 只输出目标值（流式+响应都是目标值）
                - "raw_only": 只输出原始内容（透传）
                - "both": 流式输出目标值，响应返回原始 JSON
        """
        if target_key is None and target_keys is None:
            raise ValueError("必须指定 target_key 或 target_keys")
        if target_key is not None and target_keys is not None:
            raise ValueError("target_key 和 target_keys 不能同时指定")

        if output_mode not in ("target_only", "raw_only", "both"):
            raise ValueError("output_mode 必须是 'target_only', 'raw_only' 或 'both'")

        self.target_keys = [target_key] if target_key else target_keys
        self.separator = separator
        self.output_content_type = content_type
        self.output_mode = output_mode
        self.single_key_mode = target_key is not None

    @staticmethod
    def parse_key_path(path: str) -> List[Union[str, int]]:
        """解析 key 路径: "data.items[0].name" -> ["data", "items", 0, "name"]"""
        result = []
        for match in re.finditer(r'([^.\[\]]+)|\[(\d+)\]', path):
            if match.group(1):
                result.append(match.group(1))
            elif match.group(2):
                result.append(int(match.group(2)))
        return result

    @staticmethod
    def get_nested_value(data: Any, path_parts: List[Union[str, int]]) -> tuple:
        """获取嵌套值，返回 (value, found)"""
        current = data
        for part in path_parts:
            try:
                if isinstance(part, int):
                    if isinstance(current, list) and 0 <= part < len(current):
                        current = current[part]
                    else:
                        return None, False
                else:
                    if isinstance(current, dict) and part in current:
                        current = current[part]
                    else:
                        return None, False
            except (KeyError, IndexError, TypeError):
                return None, False
        return current, True

    def process(self, generator: BaseGenerator[GeneratorOutput]) -> BaseGenerator[GeneratorOutput]:
        extractor = self

        class JsonKeyExtractingGenerator(BaseGenerator[GeneratorOutput]):
            def __init__(self, original_generator, out_type):
                super().__init__(out_type)
                self.original_generator = original_generator
                self.raw_buffer = ""
                self.last_emitted = ""  # 记录已输出的完整字符串
                self.finished = False

            def _extract_values(self) -> dict:
                """提取所有目标 key 的当前值"""
                if not self.raw_buffer:
                    return {}

                try:
                    repaired = repair_json(self.raw_buffer)
                    parsed = json.loads(repaired)

                    result = {}
                    for key_path in extractor.target_keys:
                        path_parts = extractor.parse_key_path(key_path)
                        value, found = extractor.get_nested_value(parsed, path_parts)
                        if found and value is not None:
                            result[key_path] = value
                    return result
                except Exception:
                    return {}

            def _build_output(self, values: dict) -> str:
                """构建输出字符串"""
                if extractor.single_key_mode:
                    key = extractor.target_keys[0]
                    val = values.get(key)
                    return str(val) if val is not None else ""
                else:
                    parts = []
                    for key in extractor.target_keys:
                        val = values.get(key)
                        if val is not None:
                            parts.append(str(val))
                    return extractor.separator.join(parts)

            def _get_incremental(self, current: str) -> str:
                """
                安全计算增量：只有当新值是旧值的前缀扩展时才输出
                """
                if not current:
                    return ""

                if current.startswith(self.last_emitted):
                    incremental = current[len(self.last_emitted):]
                    if incremental:
                        self.last_emitted = current
                    return incremental

                if not self.last_emitted:
                    self.last_emitted = current
                    return current

                return ""

            def _is_json_complete(self) -> bool:
                """检查 JSON 是否完整"""
                try:
                    json.loads(self.raw_buffer)
                    return True
                except json.JSONDecodeError:
                    return False

            async def agenerate(self) -> AsyncIterator[GeneratorOutput]:
                async for output in self.original_generator:
                    if self.finished:
                        continue

                    # 累积原始内容
                    self.raw_buffer += output.content

                    # 根据 output_mode 决定输出策略
                    if extractor.output_mode == "raw_only":
                        # 透传原始内容
                        yield GeneratorOutput(
                            content=output.content,
                            content_type=extractor.output_content_type
                        )

                    elif extractor.output_mode == "target_only":
                        # 只输出目标值
                        values = self._extract_values()
                        if values:
                            current_output = self._build_output(values)
                            incremental = self._get_incremental(current_output)
                            if incremental:
                                yield GeneratorOutput(
                                    content=incremental,
                                    content_type=extractor.output_content_type
                                )

                    elif extractor.output_mode == "both":
                        # 原始内容：不流式输出，但加到响应
                        yield GeneratorOutput(
                            content=output.content,
                            content_type='[STREAM_IGNORE]'
                        )

                        # 目标值：流式输出，但不加到响应
                        values = self._extract_values()
                        if values:
                            current_output = self._build_output(values)
                            incremental = self._get_incremental(current_output)
                            if incremental:
                                yield GeneratorOutput(
                                    content=incremental,
                                    content_type='[RESPONSE_IGNORE]'
                                )

                    # 检查是否完成
                    if self._is_json_complete():
                        self.finished = True

            def generate(self) -> Iterator[GeneratorOutput]:
                for output in self.original_generator:
                    if self.finished:
                        continue

                    self.raw_buffer += output.content

                    if extractor.output_mode == "raw_only":
                        yield GeneratorOutput(
                            content=output.content,
                            content_type=extractor.output_content_type
                        )

                    elif extractor.output_mode == "target_only":
                        values = self._extract_values()
                        if values:
                            current_output = self._build_output(values)
                            incremental = self._get_incremental(current_output)
                            if incremental:
                                yield GeneratorOutput(
                                    content=incremental,
                                    content_type=extractor.output_content_type
                                )

                    elif extractor.output_mode == "both":
                        yield GeneratorOutput(
                            content=output.content,
                            content_type='[STREAM_IGNORE]'
                        )

                        values = self._extract_values()
                        if values:
                            current_output = self._build_output(values)
                            incremental = self._get_incremental(current_output)
                            if incremental:
                                yield GeneratorOutput(
                                    content=incremental,
                                    content_type='[RESPONSE_IGNORE]'
                                )

                    if self._is_json_complete():
                        self.finished = True

        return JsonKeyExtractingGenerator(generator, self.output_content_type)