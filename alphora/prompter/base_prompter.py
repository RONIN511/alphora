import json
import logging
import time
import os
import re
import uuid
from pathlib import Path
from typing import Optional, List, Callable, Any, Union, Dict, Literal, TYPE_CHECKING

from jinja2 import Environment, Template, BaseLoader, meta

from alphora.models.message import Message
from alphora.postprocess.base_pp import BasePostProcessor
from alphora.server.stream_responser import DataStreamer

from json_repair import repair_json

from alphora.models.llms.base import BaseLLM
from alphora.models.llms.stream_helper import BaseGenerator
from alphora.models.llms.types import ToolCall

if TYPE_CHECKING:
    from alphora.memory import MemoryManager

from alphora.debugger import tracer

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class PrompterOutput(str):

    def __new__(cls, content: str, reasoning: str = "", finish_reason: str = "",
                continuation_count: int = 0):
        instance = super().__new__(cls, content)
        instance._reasoning = reasoning
        instance._finish_reason = finish_reason
        instance._continuation_count = continuation_count
        return instance

    @property
    def reasoning(self):
        return self._reasoning

    @property
    def finish_reason(self):
        return self._finish_reason

    @property
    def continuation_count(self):
        """返回续写次数（long_response 模式）"""
        return self._continuation_count


class BasePrompt:

    def __init__(self,
                 # --- User Part，也就是传入大模型接口中 role=user 的部分 ---
                 user_prompt: str = None,
                 template_path: str = None,
                 # --- System 部分 ---
                 system_prompt: Union[str, List[str], None] = None,  # 支持传列表
                 # --- 通用设置 ---
                 verbose: bool = False,
                 callback: Optional[DataStreamer] = None,
                 content_type: Optional[str] = None,
                 enable_memory: bool = False,
                 memory: Optional['MemoryManager'] = None,
                 memory_id: Optional[str] = None,
                 max_history_rounds: int = 10,
                 auto_save_memory: bool = True,
                 agent_id: str | None = None,
                 **kwargs):

        """
        Args:
            template_path: 模板文件路径（传统模式）
            template_desc: 模板描述
            verbose: 是否打印大模型的中间过程
            callback: 流式回调
            content_type: 内容类型
            system_prompt: 系统提示词（新模式，支持占位符）
            enable_memory: 是否启用记忆（仅新模式可用）
            memory: MemoryManager 实例
            memory_id: 记忆ID，用于区分不同会话
            max_history_rounds: 最大历史轮数
            auto_save_memory: 是否自动保存对话到记忆
            **kwargs: 占位符
        """

        self.agent_id = agent_id
        self.prompt_id = str(uuid.uuid4())[:8]

        self.template_path = template_path

        self.is_stream: bool = False

        self.llm: BaseLLM | None = None
        self.callback: Optional[DataStreamer] = callback
        self.verbose: bool = verbose
        self.content_type = content_type or 'char'
        self.context = kwargs

        self._resolved_prompt = None
        self.parser = []

        self.prompt: Optional[Template] = None
        self.content: Optional[str] = None  # 原始的tmpl文件的内容，字符串，包含了占位符

        self.prompt, self.content = self.load_template()  # 将文件路径读取，并加载为Template和content

        # 1. 初始化环境
        self.env = Environment(loader=BaseLoader())

        # 2. 处理 User 模板 (User Prompt)
        self.user_template: Optional[Template] = None
        self._user_prompt_raw: Optional[str] = None  # 用于存储原始字符串以便扫描变量

        if user_prompt:
            # 优先级最高：直接使用传入的字符串
            self._user_prompt_raw = user_prompt
            self.user_template = self.env.from_string(user_prompt)
        elif template_path:
            # 优先级次之：从文件读取
            self.template_path = template_path
            # 复用原来的读取逻辑，返回 (Template, str_content)
            tmpl, content = self.load_template()
            self.user_template = tmpl
            self._user_prompt_raw = content

        # 3. 处理 System 模板
        self.system_templates: List[Template] = []
        self._raw_system_prompts = []

        if system_prompt:
            if isinstance(system_prompt, str):
                self._raw_system_prompts = [system_prompt]
            elif isinstance(system_prompt, list):
                self._raw_system_prompts = system_prompt

            for sp in self._raw_system_prompts:
                self.system_templates.append(self.env.from_string(sp))

        # 4. 扫描所有变量 (包括 User 和 System)
        self.placeholders = self._scan_all_variables()

        self.enable_memory = enable_memory
        self._memory = memory
        self._memory_id = memory_id or f"prompt_{uuid.uuid4().hex[:8]}"
        self.max_history_rounds = max_history_rounds
        self.auto_save_memory = auto_save_memory

        # 如果启用记忆但没有传入 memory，自动创建内存存储的
        if self.enable_memory and self._memory is None:
            from alphora.memory import MemoryManager
            self._memory = MemoryManager()

    def _scan_all_variables(self) -> List[str]:
        """扫描 User 和 System 模板中的所有未定义变量"""
        vars_set = set()

        # 扫描 User 模板 (来源于 user_prompt 或 template_path)
        if self._user_prompt_raw:
            try:
                parsed = self.env.parse(self._user_prompt_raw)
                vars_set.update(meta.find_undeclared_variables(parsed))
            except Exception:
                pass  # 忽略解析错误

        # 扫描 System 模板
        for sp in self._raw_system_prompts:
            try:
                parsed = self.env.parse(sp)
                vars_set.update(meta.find_undeclared_variables(parsed))
            except Exception:
                pass

        if 'query' in vars_set:
            vars_set.remove('query')

        return list(vars_set)

    def _render_user_content(self, query: str) -> str:
        """渲染 User 部分的内容"""
        # 1. 准备渲染上下文
        render_context = self.context.copy()

        # 将 query 放入上下文，这样模板里的 {{query}} 就能取到值
        if query is not None:
            render_context['query'] = query

        # 2. 如果定义了 user_template (无论是通过 user_prompt 还是 template_path)
        if self.user_template:
            try:
                return self.user_template.render(render_context)
            except Exception as e:
                logger.error(f"User 模板渲染失败: {e}")
                return query or ""  # 降级处理

        # 3. 如果没定义模板，直接把 query 当作 User 消息内容
        return query or ""

    def update_placeholder(self, **kwargs):
        """
        更新占位符值（User & System 通用），包含校验和追踪逻辑
        """
        # 1. 参数校验
        invalid_placeholders = [k for k in kwargs if k not in self.placeholders]

        # 这里的检查稍微放宽：只要 context 或 kwargs 里有就算 cover 了
        missing_placeholders = [p for p in self.placeholders if p not in kwargs and p not in self.context]

        if invalid_placeholders:
            logger.info(f"传入了未定义占位符: <{', '.join(invalid_placeholders)}> (可用: {self.placeholders})")

        if missing_placeholders:
            logger.info(f"存在未赋值占位符: <{', '.join(missing_placeholders)}>")

        # 2. 更新上下文
        valid_kwargs = {k: v for k, v in kwargs.items() if k in self.placeholders}
        self.context.update(valid_kwargs)

        # 3. 调试追踪 (Render Preview)
        try:
            sys_rendered = self._render_system_prompts()
            sys_str = "\n".join([f"[System]: {s}" for s in sys_rendered if s.strip()])
            user_str = f"[User]: {self._render_user_content('{{query}}')}"
            combined_preview = f"{sys_str}\n\n{user_str}".strip()

            tracer.track_prompt_render(
                agent_id=self.agent_id,
                prompt_id=self.prompt_id,
                rendered_prompt=combined_preview,
                placeholders=valid_kwargs
            )
        except Exception:
            pass

        return self

    def _render_system_prompts(self) -> List[str]:
        """渲染所有的 System 模板"""
        return [tmpl.render(self.context) for tmpl in self.system_templates]

    def build_messages(
            self,
            query: str,
            force_json: bool = False,
            runtime_system_prompt: Union[str, List[str], None] = None
    ) -> List[Dict[str, str]]:
        """
        [核心方法] 统一构建发送给 LLM 的消息列表
        结构: [Force JSON] + [System Templates] + [Runtime System] + [History] + [User]
        """
        messages = []

        # 1. Force JSON 指令
        if force_json:
            messages.append({
                "role": "system",
                "content": "请严格使用 JSON 格式输出"
            })

        # 2. 预设 System Prompts (渲染初始化时传入的 system_prompt)
        # 即使初始化没传，这里返回空列表，不会报错
        rendered_sys = self._render_system_prompts()
        for content in rendered_sys:
            if content.strip():
                messages.append({"role": "system", "content": content})

        # 3. 运行时动态追加的 System Prompts (在 call/acall 时传入)
        if runtime_system_prompt:
            extras = [runtime_system_prompt] if isinstance(runtime_system_prompt, str) else runtime_system_prompt
            for content in extras:
                if content:
                    messages.append({"role": "system", "content": content})

        # 4. 历史记录 (Memory)
        if self.enable_memory and self._memory:
            history = self._memory.build_history(
                memory_id=self._memory_id,
                max_round=self.max_history_rounds,
                format="messages",
                include_timestamp=False
            )
            if history:
                messages.extend(history)

        # 5. User Content (渲染模板 或 直接使用 Query)
        user_content = self._render_user_content(query)
        messages.append({"role": "user", "content": user_content})

        return messages

    @property
    def memory(self) -> Optional['MemoryManager']:
        """获取记忆管理器"""
        return self._memory

    @memory.setter
    def memory(self, value: 'MemoryManager'):
        """设置记忆管理器"""
        self._memory = value
        if value is not None:
            self.enable_memory = True

    @property
    def memory_id(self) -> str:
        """获取记忆ID"""
        return self._memory_id

    @memory_id.setter
    def memory_id(self, value: str):
        """设置记忆ID"""
        self._memory_id = value

    def get_memory(self) -> Optional['MemoryManager']:
        """
        获取记忆管理器实例

        可用于：
        - 共享给其他 Prompt
        - 手动操作记忆（添加、搜索等）
        - 获取历史记录

        Returns:
            MemoryManager 实例
        """
        return self._memory

    def set_memory(
            self,
            memory: 'MemoryManager',
            memory_id: Optional[str] = None
    ) -> 'BasePrompt':
        """
        设置记忆管理器

        Args:
            memory: MemoryManager 实例
            memory_id: 记忆ID（可选）

        Returns:
            self（支持链式调用）
        """
        self._memory = memory
        if memory_id:
            self._memory_id = memory_id
        self.enable_memory = True
        return self

    def clear_memory(self) -> 'BasePrompt':
        """
        清空当前 memory_id 的记忆

        Returns:
            self（支持链式调用）
        """
        if self._memory:
            self._memory.clear_memory(self._memory_id)
        return self

    def get_history(
            self,
            format: Literal["text", "messages"] = "messages",
            max_round: Optional[int] = None
    ) -> Union[str, List[Dict[str, str]]]:
        """
        获取对话历史

        Args:
            format: 输出格式
                - "messages": List[Dict]，可直接用于 LLM
                - "text": 字符串格式
            max_round: 最大轮数（不传则使用 max_history_rounds）

        Returns:
            对话历史
        """
        if not self._memory:
            return [] if format == "messages" else ""

        return self._memory.build_history(
            memory_id=self._memory_id,
            max_round=max_round or self.max_history_rounds,
            format=format,
            include_timestamp=False
        )

    def _save_to_memory(self, query: str, response: str):
        """保存对话到记忆（query 原文 + LLM 响应原文）"""
        if self.enable_memory and self._memory and self.auto_save_memory:
            self._memory.add_memory("user", query, memory_id=self._memory_id)
            self._memory.add_memory("assistant", response, memory_id=self._memory_id)

    def _save_payload_to_memory(self, payload: Any):
        """保存对话到记忆（query 原文 + LLM 响应原文）"""
        if self.enable_memory and self._memory and self.auto_save_memory:
            self._memory.add_payload(payload=payload, memory_id=self._memory_id)

    @staticmethod
    def _get_base_path():
        """
        自动获取包的绝对路径
        Returns:
        """

        current_file = os.path.abspath(__file__)

        base_path = os.path.dirname(current_file)
        base_path = os.path.dirname(base_path)
        base_path = os.path.dirname(base_path)

        return base_path

    def load_template(self) -> [Optional[Template], str]:
        """
        加载 template_path 为
        Returns:
        """
        content = None

        # 尝试使用传入路径加载模板
        if self.template_path:
            template_file = Path(self.template_path)

            if template_file.is_file():
                try:
                    content = template_file.read_text(encoding='utf-8')
                except Exception as e:
                    raise Exception(f"Error reading template file: {e}")

            else:
                # 尝试使用项目的绝对位置来拼接
                template_path = os.path.join(self._get_base_path(), self.template_path)
                template_file = Path(template_path)
                if template_file.is_file():
                    try:
                        content = template_file.read_text(encoding='utf-8')
                    except Exception as e:
                        raise Exception(f"Error reading template file: {e}")
                print(f"Template file not found at path: {self.template_path}")

            # 加载模板内容到 self.prompt
            if content:
                try:
                    self.prompt = Template(content)
                    return self.prompt, content
                except Exception as e:
                    raise Exception(f"Error initializing template: {e}")

            raise Exception(f"Template file is not loaded: {self.template_path}")

        else:
            # 当template_path为None时，直接返回None
            return None, ""

    def _get_template_variables(self):
        """使用AST分析获取所有变量"""
        if not self.prompt:
            raise ValueError("Prompt is not initialized")

        parsed_content = self.env.parse(self.content)
        variables = meta.find_undeclared_variables(parsed_content)
        return [var for var in variables if var != 'query']

    def __or__(self, other: "BasePrompt") -> "ParallelPrompt":
        from alphora.prompter.parallel import ParallelPrompt
        if not isinstance(other, BasePrompt):
            return NotImplemented

        if isinstance(self, ParallelPrompt):
            new_prompts = self.prompts + [other]
        else:
            new_prompts = [self, other]

        return ParallelPrompt(new_prompts)

    def load_from_string(self, prompt: str) -> None:
        """
        从字符串加载 User 提示词 (更新为对接 user_template)
        """
        if self.env is None:
            self.env = Environment(loader=BaseLoader())

        # 同时更新旧属性（为了兼容）和新属性
        self.prompt = self.env.from_string(prompt)
        self.content = prompt

        # 对接新逻辑：直接作为 user_template
        self.user_template = self.prompt
        self._user_prompt_raw = prompt

        # 重新扫描变量
        self.placeholders = self._scan_all_variables()

    def render(self) -> str:
        """
        [兼容方法] 获取渲染后的 User 文本
        """
        # 依然支持外部直接调用 render() 获取文本
        return self._render_user_content("{{query}}")

    def add_llm(self, model=None) -> "BasePrompt":
        """
        241025修改，支持解耦调用
        -241127更新，增加支持混合流式

        add_llm(model=qwen')

        Args:
            model:BaseLLM
        Returns: BasePrompt
        """
        self.llm = model
        return self

    def call(self,
             query: str = None,
             is_stream: bool = False,
             tools: Optional[List] = None,
             multimodal_message: Message = None,
             return_generator: bool = False,
             content_type: str = None,
             postprocessor: BasePostProcessor | List[BasePostProcessor] | None  = None,
             enable_thinking: bool = False,
             force_json: bool = False,
             long_response: bool = False,
             system_prompt: Union[str, List[str], None] = None,  # 运行时追加
             save_to_memory: Optional[bool] = None,
             ) -> BaseGenerator | str | Any | ToolCall:

        if not self.llm:
            raise ValueError("LLM not initialized")

        # 1. 构建消息
        messages = self.build_messages(query=query, force_json=force_json, runtime_system_prompt=system_prompt)

        msg_payload = messages if not multimodal_message else multimodal_message

        # 2. 工具调用 (非流式优先，若未开启流式)
        if tools and not is_stream:
            return self.llm.get_non_stream_response(
                message=msg_payload, tools=tools, prompt_id=self.prompt_id
            )

        # 3. 流式调用 (含流式工具处理)
        if is_stream:
            try:
                # 准备生成器参数
                gen_kwargs = {
                    "message": msg_payload,
                    "content_type": content_type or self.content_type,
                    "enable_thinking": enable_thinking,
                    "prompt_id": self.prompt_id,
                    "system_prompt": None  # system_prompt 已融合进 messages
                }

                # 增加 tools 传参支持
                if tools:
                    gen_kwargs["tools"] = tools

                if long_response:
                    from alphora.prompter.long_response import LongResponseGenerator
                    generator = LongResponseGenerator(llm=self.llm, original_message=msg_payload,
                                                      **{k: v for k, v in gen_kwargs.items() if k != "message"})
                else:
                    generator = self.llm.get_streaming_response(**gen_kwargs)

                # 后处理
                if postprocessor:
                    if isinstance(postprocessor, List):
                        for p in postprocessor: generator = p(generator)
                    else:
                        generator = postprocessor(generator)

                if return_generator:
                    return generator

                # 消费流
                output_str = ''
                reasoning_content = ''

                for ck in generator:
                    content = ck.content
                    ctype = ck.content_type

                    if ctype == 'think' and enable_thinking:
                        reasoning_content += content
                        print(content, end='', flush=True)
                        continue

                    if ctype == '[STREAM_IGNORE]':
                        output_str += content
                        continue
                    if ctype == '[RESPONSE_IGNORE]':
                        print(content, end='', flush=True)
                        continue
                    if ctype == '[BOTH_IGNORE]':
                        continue

                    if content:
                        print(content, end='', flush=True)
                        output_str += content

                # 流结束后，检查是否有累计的 Tool Calls
                collected_tools = getattr(generator, 'collected_tool_calls', None)
                if collected_tools:
                    # 如果有工具调用，返回 ToolCall 对象
                    # 如果同时有文本(output_str)，也放入 ToolCall 的 content 中
                    return ToolCall(tool_calls=collected_tools, content=output_str)

                if force_json:
                    try:
                        output_str = repair_json(json_str=output_str)
                    except Exception:
                        pass

                # 保存记忆
                should_save = save_to_memory if save_to_memory is not None else self.auto_save_memory
                if should_save:
                    self._save_to_memory(query, output_str)

                return PrompterOutput(
                    content=output_str,
                    reasoning=reasoning_content,
                    finish_reason=getattr(generator, 'finish_reason', ''),
                    continuation_count=getattr(generator, 'continuation_count', 0)
                )

            except Exception as e:
                raise RuntimeError(f"流式响应错误: {e}")

        else:
            # 4. 非流式调用 (无 tools 的普通调用)
            try:
                resp = self.llm.invoke(message=msg_payload)

                should_save = save_to_memory if save_to_memory is not None else self.auto_save_memory
                if should_save:
                    self._save_to_memory(query, resp)

                return PrompterOutput(content=resp, reasoning="", finish_reason="")
            except Exception as e:
                raise RuntimeError(f"非流式响应错误: {e}")

    async def acall(self,
                    query: str = None,
                    is_stream: bool = False,
                    tools: Optional[List] = None,
                    multimodal_message: Message = None,
                    return_generator: bool = False,
                    content_type: Optional[str] = None,
                    postprocessor: BasePostProcessor | List[BasePostProcessor] | None = None,
                    enable_thinking: bool = False,
                    force_json: bool = False,
                    long_response: bool = False,
                    system_prompt: Union[str, List[str], None] = None,
                    save_to_memory: Optional[bool] = None,
                    ) -> BaseGenerator | str | Any | ToolCall:

        if not self.llm:
            raise ValueError("LLM not initialized")

        if not content_type:
            content_type = self.content_type or 'char'

        # 1. 构建消息
        messages = self.build_messages(query=query, force_json=force_json, runtime_system_prompt=system_prompt)
        msg_payload = messages if not multimodal_message else multimodal_message

        # 2. 工具调用 (非流式优先)
        if tools and not is_stream:

            tool_resp = await self.llm.aget_non_stream_response(
                message=msg_payload, system_prompt=None, tools=tools, prompt_id=self.prompt_id
            )

            should_save = save_to_memory if save_to_memory is not None else self.auto_save_memory

            if should_save:
                self._memory.add_memory("user", query, memory_id=self._memory_id)

                if tool_resp:
                    logger.debug(f'Detected ToolCall. Delegating persistence to ToolExecutor.')
                    pass

                if tool_resp.content:
                    logger.debug(f'Saving standard LLM response to memory.')
                    self._save_to_memory(query, tool_resp.content)

            return tool_resp

        # 3. 流式调用
        if is_stream:
            try:
                gen_kwargs = {
                    "message": msg_payload,
                    "content_type": content_type,
                    "enable_thinking": enable_thinking,
                    "prompt_id": self.prompt_id,
                    "system_prompt": None
                }

                # 增加 tools 传参支持
                if tools:
                    gen_kwargs["tools"] = tools

                if long_response:
                    gen_kwargs.pop('prompt_id')
                    from alphora.prompter.long_response import LongResponseGenerator
                    generator = LongResponseGenerator(llm=self.llm, original_message=msg_payload,
                                                      **{k: v for k, v in gen_kwargs.items() if k != "message"})
                else:
                    generator = await self.llm.aget_streaming_response(**gen_kwargs)

                if postprocessor:
                    if isinstance(postprocessor, List):
                        for p in postprocessor:
                            generator = p(generator)
                    else:
                        generator = postprocessor(generator)

                if return_generator:
                    return generator

                output_str = ''
                reasoning_content = ''

                async for ck in generator:
                    content = ck.content
                    ctype = ck.content_type

                    if self.callback:
                        if ctype == 'think' and enable_thinking:
                            await self.callback.send_data(content_type=ctype, content=content)
                            reasoning_content += content
                            continue
                        if ctype == '[STREAM_IGNORE]':
                            output_str += content
                            continue
                        if ctype == '[RESPONSE_IGNORE]':
                            await self.callback.send_data(content_type=ctype, content=content)
                            continue
                        if ctype == '[BOTH_IGNORE]': continue

                        await self.callback.send_data(content_type=ctype, content=content)
                        output_str += content
                    else:
                        if ctype == 'think' and enable_thinking:
                            reasoning_content += content
                            print(content, end='', flush=True)
                            continue
                        if content and ctype != '[STREAM_IGNORE]':
                            print(content, end='', flush=True)
                        if ctype != '[RESPONSE_IGNORE]':
                            output_str += content

                # 流结束后，检查是否有累计的 Tool Calls
                collected_tools = getattr(generator, 'collected_tool_calls', None)
                if collected_tools:
                    return ToolCall(tool_calls=collected_tools, content=output_str)

                if force_json:
                    try:
                        output_str = json.dumps(json.loads(repair_json(json_str=output_str)), ensure_ascii=False)
                    except:
                        pass

                should_save = save_to_memory if save_to_memory is not None else self.auto_save_memory
                if should_save:
                    self._save_to_memory(query, output_str)

                return PrompterOutput(
                    content=output_str,
                    reasoning=reasoning_content,
                    finish_reason=getattr(generator, 'finish_reason', ''),
                    continuation_count=getattr(generator, 'continuation_count', 0)
                )

            except Exception as e:
                if self.callback: await self.callback.stop(stop_reason=str(e))
                raise RuntimeError(f"流式响应错误: {e}")

        else:
            # 4. 非流式
            try:
                resp = await self.llm.ainvoke(message=msg_payload)
                should_save = save_to_memory if save_to_memory is not None else self.auto_save_memory
                if should_save:
                    self._save_to_memory(query, resp)
                return PrompterOutput(content=resp, reasoning="", finish_reason="")
            except Exception as e:
                raise RuntimeError(f"非流式响应错误: {e}")

    def __str__(self) -> str:
        try:
            sys_rendered = self._render_system_prompts()
            sys_str = ""
            if sys_rendered:
                sys_str = "[System Prompts]\n" + "\n".join([f" - {s}" for s in sys_rendered]) + "\n"
            user_str = "[User Prompt]\n" + self._render_user_content("{{query}}")
            return sys_str + "\n" + user_str
        except Exception as e:
            return f"BasePrompt (Render Error: {str(e)})"
