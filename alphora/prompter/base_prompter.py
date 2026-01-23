"""
BasePrompt (重构版)

重构要点:
- 移除所有自动记忆功能
- 在 call/acall 中支持传入 HistoryPayload
- build_messages 负责合并 system + history + user

使用示例:
```python
from alphora.memory import MemoryManager
from alphora.prompter import BasePrompt

# 初始化
memory = MemoryManager()
prompt = BasePrompt(
    system_prompt="你是一个友好的助手",
    user_prompt="{{query}}"
).add_llm(llm)

# 第一轮对话
response = await prompt.acall(query="你好")
memory.add_user("你好")
memory.add_assistant(response)

# 第二轮对话 (带历史)
history = memory.build_history(max_rounds=5)
response = await prompt.acall(query="今天天气怎么样？", history=history)
memory.add_user("今天天气怎么样？")
memory.add_assistant(response)

# 工具调用场景
history = memory.build_history()
tool_response = await prompt.acall(query="查询天气", history=history, tools=weather_tools)

# 记录工具调用
memory.add_user("查询天气")
memory.add_assistant(content=None, tool_calls=tool_response.tool_calls)

# 执行工具并记录结果
for tc in tool_response.tool_calls:
    result = await execute_tool(tc)
    memory.add_tool_result(tc["id"], tc["function"]["name"], result)

# 继续对话
history = memory.build_history()
final_response = await prompt.acall(query=None, history=history)
memory.add_assistant(final_response)
```
"""

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

from alphora.memory.history_payload import HistoryPayload, is_valid_history_payload

from alphora.debugger import tracer

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class PrompterOutput(str):
    """
    Prompter 输出包装类

    继承自 str，可以直接作为字符串使用，同时携带额外元数据。
    """

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
    """
    提示词基类 (重构版)

    重构要点:
    - 完全移除自动记忆功能
    - 支持通过 history 参数传入 HistoryPayload
    - 消息构建流程: [Force JSON] + [System] + [History] + [User]

    Attributes:
        system_templates: 系统提示词模板列表
        user_template: 用户提示词模板
        llm: 绑定的 LLM 实例
        context: 占位符上下文
    """

    def __init__(self,
                 # --- User Part ---
                 user_prompt: str = None,
                 template_path: str = None,
                 # --- System 部分 ---
                 system_prompt: Union[str, List[str], None] = None,
                 # --- 通用设置 ---
                 verbose: bool = False,
                 callback: Optional[DataStreamer] = None,
                 content_type: Optional[str] = None,
                 agent_id: str | None = None,
                 **kwargs):
        """
        Args:
            user_prompt: 用户提示词模板字符串
            template_path: 模板文件路径（与 user_prompt 二选一）
            system_prompt: 系统提示词（支持字符串或字符串列表，支持 Jinja2 模板）
            verbose: 是否打印中间过程
            callback: 流式回调
            content_type: 内容类型
            agent_id: Agent ID (用于追踪)
            **kwargs: 模板占位符初始值
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
        self.content: Optional[str] = None

        self.prompt, self.content = self.load_template()

        # 1. 初始化 Jinja2 环境
        self.env = Environment(loader=BaseLoader())

        # 2. 处理 User 模板
        self.user_template: Optional[Template] = None
        self._user_prompt_raw: Optional[str] = None

        if user_prompt:
            self._user_prompt_raw = user_prompt
            self.user_template = self.env.from_string(user_prompt)
        elif template_path:
            self.template_path = template_path
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

        # 4. 扫描所有变量
        self.placeholders = self._scan_all_variables()

    def _scan_all_variables(self) -> List[str]:
        """扫描 User 和 System 模板中的所有未定义变量"""
        vars_set = set()

        if self._user_prompt_raw:
            try:
                parsed = self.env.parse(self._user_prompt_raw)
                vars_set.update(meta.find_undeclared_variables(parsed))
            except Exception:
                pass

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
        render_context = self.context.copy()

        if query is not None:
            render_context['query'] = query

        if self.user_template:
            try:
                return self.user_template.render(render_context)
            except Exception as e:
                logger.error(f"User 模板渲染失败: {e}")
                return query or ""

        return query or ""

    def _render_system_prompts(self) -> List[str]:
        """渲染所有的 System 模板"""
        return [tmpl.render(self.context) for tmpl in self.system_templates]

    def update_placeholder(self, **kwargs):
        """
        更新占位符值
        """
        invalid_placeholders = [k for k in kwargs if k not in self.placeholders]
        missing_placeholders = [p for p in self.placeholders if p not in kwargs and p not in self.context]

        if invalid_placeholders:
            logger.info(f"传入了未定义占位符: <{', '.join(invalid_placeholders)}> (可用: {self.placeholders})")

        if missing_placeholders:
            logger.info(f"存在未赋值占位符: <{', '.join(missing_placeholders)}>")

        valid_kwargs = {k: v for k, v in kwargs.items() if k in self.placeholders}
        self.context.update(valid_kwargs)

        # 调试追踪
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

    def build_messages(
            self,
            query: str = None,
            force_json: bool = False,
            runtime_system_prompt: Union[str, List[str], None] = None,
            history: Optional[HistoryPayload] = None,
    ) -> List[Dict[str, str]]:
        """
        [核心方法] 构建发送给 LLM 的消息列表

        消息结构: [Force JSON] + [System Templates] + [Runtime System] + [History] + [User]

        Args:
            query: 用户输入 (会渲染到 user_template 中)
            force_json: 是否强制 JSON 输出
            runtime_system_prompt: 运行时追加的系统提示词
            history: HistoryPayload 对象 (由 MemoryManager.build_history() 返回)

        Returns:
            OpenAI 格式的消息列表

        Raises:
            TypeError: 如果 history 不是有效的 HistoryPayload
        """
        messages = []

        # 1. Force JSON 指令
        if force_json:
            messages.append({
                "role": "system",
                "content": "请严格使用 JSON 格式输出"
            })

        # 2. 预设 System Prompts
        rendered_sys = self._render_system_prompts()
        for content in rendered_sys:
            if content.strip():
                messages.append({"role": "system", "content": content})

        # 3. 运行时动态追加的 System Prompts
        if runtime_system_prompt:
            extras = [runtime_system_prompt] if isinstance(runtime_system_prompt, str) else runtime_system_prompt
            for content in extras:
                if content:
                    messages.append({"role": "system", "content": content})

        # 4. 插入历史记录 (来自 HistoryPayload)
        if history is not None:
            if not is_valid_history_payload(history):
                raise TypeError(
                    "history must be a valid HistoryPayload from MemoryManager.build_history(). "
                    "Got: {type(history).__name__}"
                )

            # 检查工具链完整性警告
            if history.has_tool_calls and not history.tool_chain_valid:
                logger.warning(
                    f"History contains incomplete tool chain (session={history.session_id}). "
                    "This may cause LLM errors."
                )

            # 合并历史消息
            messages.extend(history.to_list())

        # 5. User Content
        if query is not None:
            user_content = self._render_user_content(query)
            messages.append({"role": "user", "content": user_content})

        return messages

    @staticmethod
    def _get_base_path():
        """自动获取包的绝对路径"""
        current_file = os.path.abspath(__file__)
        base_path = os.path.dirname(current_file)
        base_path = os.path.dirname(base_path)
        base_path = os.path.dirname(base_path)
        return base_path

    def load_template(self) -> [Optional[Template], str]:
        """加载 template_path 为 Template 和原始字符串"""
        content = None

        if self.template_path:
            template_file = Path(self.template_path)

            if template_file.is_file():
                try:
                    content = template_file.read_text(encoding='utf-8')
                except Exception as e:
                    raise Exception(f"Error reading template file: {e}")

            else:
                template_path = os.path.join(self._get_base_path(), self.template_path)
                template_file = Path(template_path)
                if template_file.is_file():
                    try:
                        content = template_file.read_text(encoding='utf-8')
                    except Exception as e:
                        raise Exception(f"Error reading template file: {e}")
                print(f"Template file not found at path: {self.template_path}")

            if content:
                try:
                    self.prompt = Template(content)
                    return self.prompt, content
                except Exception as e:
                    raise Exception(f"Error initializing template: {e}")

            raise Exception(f"Template file is not loaded: {self.template_path}")

        else:
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
        """从字符串加载 User 提示词"""
        if self.env is None:
            self.env = Environment(loader=BaseLoader())

        self.prompt = self.env.from_string(prompt)
        self.content = prompt
        self.user_template = self.prompt
        self._user_prompt_raw = prompt
        self.placeholders = self._scan_all_variables()

    def render(self) -> str:
        """[兼容方法] 获取渲染后的 User 文本"""
        return self._render_user_content("{{query}}")

    def add_llm(self, model=None) -> "BasePrompt":
        """绑定 LLM 实例"""
        self.llm = model
        return self

    def call(self,
             query: str = None,
             is_stream: bool = False,
             tools: Optional[List] = None,
             multimodal_message: Message = None,
             return_generator: bool = False,
             content_type: str = None,
             postprocessor: BasePostProcessor | List[BasePostProcessor] | None = None,
             enable_thinking: bool = False,
             force_json: bool = False,
             long_response: bool = False,
             runtime_system_prompt: Union[str, List[str], None] = None,
             history: Optional[HistoryPayload] = None,
             ) -> BaseGenerator | str | Any | ToolCall:
        """
        同步调用 LLM

        Args:
            query: 用户输入 (可选，如果只是继续工具调用则不需要)
            is_stream: 是否流式输出
            tools: 工具列表
            multimodal_message: 多模态消息
            return_generator: 是否返回生成器
            content_type: 内容类型
            postprocessor: 后处理器
            enable_thinking: 是否启用思考过程
            force_json: 是否强制 JSON 输出
            long_response: 是否长文本模式
            runtime_system_prompt: 运行时系统提示词
            history: 历史记录 (HistoryPayload，由 MemoryManager.build_history() 返回)

        Returns:
            LLM 响应 (PrompterOutput / ToolCall / Generator)

        Example:
            # 简单调用
            response = prompt.call(query="你好")

            # 带历史
            history = memory.build_history(max_rounds=5)
            response = prompt.call(query="你好", history=history)

            # 工具调用
            history = memory.build_history()
            tool_response = prompt.call(query=None, history=history, tools=tools)
        """
        if not self.llm:
            raise ValueError("LLM not initialized. Call add_llm() first.")

        # 1. 构建消息
        messages = self.build_messages(
            query=query,
            force_json=force_json,
            runtime_system_prompt=runtime_system_prompt,
            history=history
        )

        msg_payload = messages if not multimodal_message else multimodal_message

        # 2. 工具调用 (非流式优先)
        if tools and not is_stream:
            return self.llm.get_non_stream_response(
                message=msg_payload, tools=tools, prompt_id=self.prompt_id
            )

        # 3. 流式调用
        if is_stream:
            try:
                gen_kwargs = {
                    "message": msg_payload,
                    "content_type": content_type or self.content_type,
                    "enable_thinking": enable_thinking,
                    "prompt_id": self.prompt_id,
                    "system_prompt": None
                }

                if tools:
                    gen_kwargs["tools"] = tools

                if long_response:
                    from alphora.prompter.long_response import LongResponseGenerator
                    generator = LongResponseGenerator(
                        llm=self.llm,
                        original_message=msg_payload,
                        **{k: v for k, v in gen_kwargs.items() if k != "message"}
                    )
                else:
                    generator = self.llm.get_streaming_response(**gen_kwargs)

                # 后处理
                if postprocessor:
                    if isinstance(postprocessor, List):
                        for p in postprocessor:
                            generator = p(generator)
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

                # 流结束后，检查工具调用
                collected_tools = getattr(generator, 'collected_tool_calls', None)

                if tools:
                    return ToolCall(tool_calls=collected_tools, content=output_str)

                # if collected_tools:
                #     return ToolCall(tool_calls=collected_tools, content=output_str)

                if force_json:
                    try:
                        output_str = repair_json(json_str=output_str)
                    except Exception:
                        pass

                return PrompterOutput(
                    content=output_str,
                    reasoning=reasoning_content,
                    finish_reason=getattr(generator, 'finish_reason', ''),
                    continuation_count=getattr(generator, 'continuation_count', 0)
                )

            except Exception as e:
                raise RuntimeError(f"流式响应错误: {e}")

        else:
            # 4. 非流式
            try:
                resp = self.llm.invoke(message=msg_payload)
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
                    runtime_system_prompt: Union[str, List[str], None] = None,
                    history: Optional[HistoryPayload] = None,
                    ) -> BaseGenerator | str | Any | ToolCall:
        """
        异步调用 LLM

        Args:
            query: 用户输入 (可选，如果只是继续工具调用则不需要)
            is_stream: 是否流式输出
            tools: 工具列表
            multimodal_message: 多模态消息
            return_generator: 是否返回生成器
            content_type: 内容类型
            postprocessor: 后处理器
            enable_thinking: 是否启用思考过程
            force_json: 是否强制 JSON 输出
            long_response: 是否长文本模式
            runtime_system_prompt: 运行时系统提示词
            history: 历史记录 (HistoryPayload，由 MemoryManager.build_history() 返回)

        Returns:
            LLM 响应 (PrompterOutput / ToolCall / Generator)

        Example:
            # 简单调用
            response = await prompt.acall(query="你好")

            # 带历史
            history = memory.build_history(max_rounds=5)
            response = await prompt.acall(query="你好", history=history)

            # 工具调用流程
            memory.add_user("查询天气")
            history = memory.build_history()
            tool_response = await prompt.acall(query=None, history=history, tools=tools)

            # 记录并执行工具
            memory.add_assistant(content=None, tool_calls=tool_response.tool_calls)
            for tc in tool_response.tool_calls:
                result = await execute_tool(tc)
                memory.add_tool_result(tc["id"], tc["function"]["name"], result)

            # 获取最终回复
            history = memory.build_history()
            final = await prompt.acall(query=None, history=history)
            memory.add_assistant(final)
        """
        if not self.llm:
            raise ValueError("LLM not initialized. Call add_llm() first.")

        if not content_type:
            content_type = self.content_type or 'char'

        # 1. 构建消息
        messages = self.build_messages(
            query=query,
            force_json=force_json,
            runtime_system_prompt=runtime_system_prompt,
            history=history
        )
        msg_payload = messages if not multimodal_message else multimodal_message

        # 2. 工具调用 (非流式优先)
        if tools and not is_stream:
            tool_resp = await self.llm.aget_non_stream_response(
                message=msg_payload, system_prompt=None, tools=tools, prompt_id=self.prompt_id
            )
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

                if tools:
                    gen_kwargs["tools"] = tools

                if long_response:
                    gen_kwargs.pop('prompt_id')
                    from alphora.prompter.long_response import LongResponseGenerator
                    generator = LongResponseGenerator(
                        llm=self.llm,
                        original_message=msg_payload,
                        **{k: v for k, v in gen_kwargs.items() if k != "message"}
                    )
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
                        if ctype == '[BOTH_IGNORE]':
                            continue

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

                # 流结束后，检查工具调用
                collected_tools = getattr(generator, 'collected_tool_calls', None)

                if tools:
                    return ToolCall(tool_calls=collected_tools, content=output_str)

                # 20260123 注释
                # if collected_tools:
                #     return ToolCall(tool_calls=collected_tools, content=output_str)

                if force_json:
                    try:
                        output_str = json.dumps(json.loads(repair_json(json_str=output_str)), ensure_ascii=False)
                    except:
                        pass

                return PrompterOutput(
                    content=output_str,
                    reasoning=reasoning_content,
                    finish_reason=getattr(generator, 'finish_reason', ''),
                    continuation_count=getattr(generator, 'continuation_count', 0)
                )

            except Exception as e:
                if self.callback:
                    await self.callback.stop(stop_reason=str(e))
                raise RuntimeError(f"流式响应错误: {e}")

        else:
            # 4. 非流式
            try:
                resp = await self.llm.ainvoke(message=msg_payload)
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