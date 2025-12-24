import json
from typing import Iterator, AsyncIterator
from json_repair import repair_json
from alphora.models.llms.stream_helper import BaseGenerator, GeneratorOutput
from alphora.postprocess.base import BasePostProcessor


class JsonKeyExtractorPP(BasePostProcessor):
    """
    流式 JSON key 提取后处理器
    """

    def __init__(
            self,
            target_key: str,
            content_type: str = "text",
            stream_only_target: bool = True,
            response_only_target: bool = False,
    ):
        self.target_key = target_key
        self.output_content_type = content_type
        self.stream_only_target = stream_only_target
        self.response_only_target = response_only_target

    def process(self, generator: BaseGenerator[GeneratorOutput]) -> BaseGenerator[GeneratorOutput]:
        class JsonKeyExtractingGenerator(BaseGenerator[GeneratorOutput]):
            def __init__(self, original_generator, target_key, out_type, stream_only_target, response_only_target):
                super().__init__(out_type)
                self.original_generator = original_generator
                self.target_key = target_key
                self.stream_only_target = stream_only_target
                self.response_only_target = response_only_target

                # 状态变量优化
                self.raw_buffer = ""          # 原始流式内容缓冲区
                self.last_output_len = 0      # 记录上一次输出的目标值长度（核心：避免重复）
                self.target_full_value = None # 完整的目标值
                self.finished = False         # 是否提取完成

            def _extract_target_value(self) -> tuple[any, bool, int]:
                """
                利用json_repair修复后解析JSON
                返回：(当前完整目标值, 是否完整, 本次新增长度)
                """
                if not self.raw_buffer:
                    return None, False, 0

                try:
                    # 修复不完整JSON
                    repaired_json = repair_json(self.raw_buffer)
                    parsed = json.loads(repaired_json)

                    # 只处理字典类型
                    if isinstance(parsed, dict) and self.target_key in parsed:
                        current_val = parsed[self.target_key]
                        val_str = str(current_val)
                        val_len = len(val_str)

                        # 判断是否完整（修复后的值在原始缓冲区中闭合）
                        is_complete = (
                                json.dumps(current_val).strip() in self.raw_buffer.strip() or
                                # 兼容复杂值的判断：缓冲区包含结束标记
                                (val_str and any(
                                    end_char in self.raw_buffer
                                    for end_char in ['"', '}', ']']
                                ) and not self.raw_buffer.strip().endswith(val_str[-1]))
                        )

                        # 计算本次新增长度（核心：只输出新增部分）
                        new_len = val_len - self.last_output_len if val_len > self.last_output_len else 0
                        return current_val, is_complete, new_len
                except Exception:
                    pass
                return None, False, 0

            async def agenerate(self) -> AsyncIterator[GeneratorOutput]:
                """异步生成器（修复重复输出：只输出新增内容）"""
                async for output in self.original_generator:
                    if self.finished:
                        yield GeneratorOutput(content=output.content, content_type='[BOTH_IGNORE]')
                        continue

                    # 1. 流式输出原始内容（按配置标记）
                    stream_ctype = '[STREAM_IGNORE]' if self.stream_only_target else self.content_type
                    yield GeneratorOutput(content=output.content, content_type=stream_ctype)

                    # 2. 积累原始内容
                    self.raw_buffer += output.content

                    # 3. 提取目标值（只取新增部分）
                    current_val, is_complete, new_len = self._extract_target_value()
                    if current_val is not None and new_len > 0:
                        self.target_full_value = current_val
                        # 只输出新增的部分（核心修复）
                        new_content = str(current_val)[-new_len:]
                        yield GeneratorOutput(
                            content=new_content,
                            content_type=self.content_type
                        )
                        # 更新已输出长度
                        self.last_output_len = len(str(current_val))

                        # 4. 完整值已提取，终止流程
                        if is_complete:
                            self.finished = True
                            break

                # 最终兜底：确保完整值输出（仅未完成时）
                if self.target_full_value and not self.finished:
                    # 只输出未输出的剩余部分
                    remaining = str(self.target_full_value)[self.last_output_len:]
                    if remaining:
                        yield GeneratorOutput(
                            content=remaining,
                            content_type=self.content_type
                        )

            def generate(self) -> Iterator[GeneratorOutput]:
                """同步生成器（同异步逻辑）"""
                for output in self.original_generator:
                    if self.finished:
                        continue

                    self.raw_buffer += output.content

                    current_val, is_complete, new_len = self._extract_target_value()
                    if current_val is not None and new_len > 0:
                        self.target_full_value = current_val
                        new_content = str(current_val)[-new_len:]
                        yield GeneratorOutput(
                            content=new_content,
                            content_type=self.content_type
                        )
                        self.last_output_len = len(str(current_val))

                        if is_complete:
                            self.finished = True
                            break

                if self.target_full_value and not self.finished:
                    remaining = str(self.target_full_value)[self.last_output_len:]
                    if remaining:
                        yield GeneratorOutput(
                            content=remaining,
                            content_type=self.content_type
                        )

        return JsonKeyExtractingGenerator(
            generator,
            self.target_key,
            self.output_content_type,
            self.stream_only_target,
            self.response_only_target,
        )