"""
"""

from chatbi.utils.console_printer import ConsoleFramePrinter
from chatbi.models.llm.base import BaseLLM
from typing import Optional, List, Any, overload, Union, Dict, Iterator
from chatbi.server.stream_responser import DataStreamer
from uuid import uuid4
import functools
import os
import uuid
import logging
from dataclasses import dataclass
import time
import warnings
from chatbi.utils.printf import printf
from chatbi.models.llm.stream_helper import GeneratorOutput, BaseGenerator
from chatbi.models.embedding.emb_model import EmbeddingModel
from chatbi.agent.foundation.config.foundation_config import FoundationConfig
from chatbi.prompts.base import BasePrompt
import random
from chatbi.agent.postprocess.base import BasePostProcessor


class FoundationError(Exception):
    """Foundation层异常基类"""
    pass


class ComponentError(FoundationError):
    """组件错误"""
    pass


class ConfigurationError(FoundationError):
    """配置错误"""
    pass


@dataclass
class PromptTemplate:
    template_path: Optional[str] = None
    template_desc: Optional[str] = None


def _ensure_log_directory(log_file: str) -> None:
    """确保日志目录存在"""
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir, exist_ok=True)
            printf(color='green', title='日志目录创建成功', message=f'路径: {log_dir}')
        except Exception as e:
            printf(color='red', title='日志目录创建失败', message=str(e))
            raise ConfigurationError(f"Failed to create log directory: {str(e)}")


class Stream:
    def __init__(self, callback: Optional[DataStreamer] = None):
        self.callback = callback
        self.post_processors: List[BasePostProcessor] = []

    def stream_message(self,
                       content: str,
                       content_type: str = "char",
                       interval: float = 0) -> None:
        """
        给 OpenAI 兼容的接口发送流式消息
        Args:
            content: String 对应的消息内容
            content_type: char(character), think(reasoning), result, sql, chart等
            interval: 流式的发送间隔（秒）
        """
        if not isinstance(content, str):
            try:
                content = str(content)
            except Exception as e:
                raise TypeError("Content must be a string")

        if interval < 0:
            raise ValueError("Interval must be non-negative")

        # 创建一个自定义生成器类
        class StringGenerator(BaseGenerator[GeneratorOutput]):
            def __init__(self, content: str, content_type: str, interval: float):
                super().__init__(content_type)
                self.content = content
                self.interval = interval

            def generate(self) -> Iterator[GeneratorOutput]:
                if self.interval > 0:
                    # 模拟流式输出，每次输出1-5个字符
                    index = 0
                    while index < len(self.content):
                        num_chars = random.randint(1, 5)
                        chunk = self.content[index:index + num_chars]
                        index += num_chars
                        time.sleep(self.interval)
                        yield GeneratorOutput(content=chunk, content_type=self.content_type)
                else:
                    yield GeneratorOutput(content=self.content, content_type=self.content_type)

        # 创建并使用生成器
        generator = StringGenerator(content, content_type, interval)
        self.stream_to_response(generator)

    def stop(self, stop_reason: str = 'end') -> None:
        """
        终结流式输出
        """
        if self.callback:
            self.callback.stop(stop_reason)
        else:
            print(f"\n[Stream stopped: {stop_reason}]")

    def stream_to_response(self, generator: BaseGenerator) -> str:
        """
        将生成器转为实际的字符串，同时发送流式输出(如果有DS)
        Args:
            generator: BaseGenerator
        Returns: String
        """
        llm_logger = generator.llm_logger
        instruction = generator.instruction

        data_streamer: Optional[DataStreamer] = self.callback
        response = ''

        printer: Optional[ConsoleFramePrinter] = None

        # 应用所有后处理器
        processed_generator = generator
        for processor in self.post_processors:
            processed_generator = processor(processed_generator)

        if not data_streamer:
            printer = ConsoleFramePrinter(width=100, title="")
            printer.print_frame_start(query=None, instruction=instruction.content)

        # 处理最终的生成器
        for output_content in processed_generator:
            try:
                content = output_content.content
                content_type = output_content.content_type

                if content:
                    if data_streamer:
                        data_streamer.send_data(content_type=content_type, content=content)
                    else:
                        printer.print_content(content=content, content_type=content_type)

            except Exception as e:
                print(f"Streaming Parsing Error: {str(e)}")
                content = ''

            response += content

        if printer:
            printer.print_frame_end()

        if llm_logger:
            try:
                llm_logger.insert_log(prompt=instruction, response=response)
            except Exception as e:
                pass

        return response


class FoundationLayer(object):
    def __init__(self,
                 callback: Optional[DataStreamer] = None,
                 embedding_model: Optional[EmbeddingModel] = None,
                 model: Optional[BaseLLM] = None,
                 user: Optional[dict] = None,
                 verbose: bool = False,
                 vision_model: Optional[BaseLLM] = None,
                 **kwargs):

        # 收集所有配置
        self.config = FoundationConfig()

        self.verbose = verbose

        self.prompts: List[BasePrompt] = []
        self.trace_id: Optional[str] = None

        self.agent_id = str(uuid.uuid4())[:5]  # 每次实例化一个Agent都会随机给一个编号

        self.vision_model: Optional[LLM] = vision_model

        # 设置流式响应对象
        self.stream = Stream(callback=callback)

        # 设置所有配置
        self.config.update(
            callback=callback,
            embedding_model=embedding_model,
            llm=model,
            user=user
        )

        # 设置观察者（放在最后设置不会触发配置变更）
        self.config.add_observer(self._on_config_change)

        if self.config.llm:
            self.config.llm.callback = self.config.callback
            self.config.llm.verbose = self.verbose
            self.config.llm.agent_id = self.agent_id

        if self.vision_model:
            self.vision_model.callback = self.config.callback
            self.vision_model.verbose = self.verbose
            self.vision_model.agent_id = self.agent_id

        self.subprocess: List[BasePostProcessor] = []

        self._model_map: Dict[str, LLM] = {}

    def _on_config_change(self,
                          field: str,
                          value: Any) -> None:
        """配置变更处理"""
        if field == 'llm' and value:
            value.verbose = self.verbose
            value.callback = self.config.callback

    @overload
    def configure(self, *,
                  llm: Optional[BaseLLM] = None,
                  embedding_model: Optional[EmbeddingModel] = None,
                  callback: Optional[DataStreamer] = None,
                  user: Optional[dict] = None) -> None:
        ...

    def configure(self, **kwargs) -> None:
        """
        更新Agent配置
        """
        try:
            self.config.update(**kwargs)
            printf(color='green', title='Configuration Success', message=f'{self.get_configurations()}')
        except (ValueError, AttributeError) as e:
            raise ConfigurationError(f"Configuration failed: {str(e)}")

    def get_configurations(self) -> str:
        """获取当前配置的JSON表示"""
        return self.config.to_json()

    def add_model(self, model: BaseLLM | Dict[str, BaseLLM]) -> 'FoundationLayer':
        """设置LLM模型
        后续在Agent中可以指定模型
        add_model({'vision': vision_model})
        """
        if model is None:
            raise ComponentError('Model cannot be None')

        if isinstance(model, Dict):
            for key, value in model.items():
                value.callback = self.config.callback
                value.verbose = self.verbose
                self._model_map[key] = value
            return self

        # 配置模型属性
        model.callback = self.config.callback
        model.verbose = self.verbose

        self.config.update(llm=model)
        return self

    @staticmethod
    def generate_trace_id() -> str:
        """生成追踪ID"""
        return str(uuid4()).replace('-', '')[:10]

    @classmethod
    def auto_logger(cls, func):
        """方法调用日志装饰器"""

        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            if not self.config.llm:
                raise ComponentError("LLM model is not configured")

            self.trace_id = cls.generate_trace_id()
            self.config.llm.set_trace_id(trace_id=self.trace_id)
            # self.logger.add_log_details(trace_id=self.trace_id)

            try:
                func_resp = func(self, *args, **kwargs)
                # self.logger.log_llm(str(self.config.llm.response_infos))
                return func_resp
            except Exception as e:
                logging.error(f"Error in {func.__name__}: {str(e)}")
                raise

        return wrapper

    def add_embedding_model(self, model: EmbeddingModel) -> None:
        """添加向量模型"""
        if not isinstance(model, EmbeddingModel):
            raise ComponentError("Model must be an instance of BaseEmbedding")

        self.config.update(embedding_model=model)

    def create_prompt(
            self,
            prompt: str = None,
            template_path: str = None,
            template_desc: str = None,
            model: BaseLLM | str = None) -> BasePrompt:
        """
        快速创建提示词模板
        Args:
            template_path: 提示词路径（建议为相对路径）
            template_desc: 提示词描述
            prompt: Optional
            model: LLM 需要用到的推理大模型

        Returns: BasePrompt实例
        """
        if isinstance(model, str):
            model = self._model_map.get(model, None)
            if model is None:
                raise ComponentError("Model not found")

        if model is None:
            model: LLM | None = self.config.llm

        if not model:
            raise ComponentError("LLM model is not configured")

        if template_path is None and prompt:
            camel_case_name = 'TempPrompt'
            template = PromptTemplate(
                template_path=template_path,
                template_desc=template_desc
            )
        else:
            tmpl_name = os.path.basename(template_path)
            if not tmpl_name.endswith('.tmpl'):
                raise ValueError(f"The file '{tmpl_name}' is not in the .tmpl format.")

            template = PromptTemplate(
                template_path=template_path,
                template_desc=template_desc
            )

            base_name = os.path.splitext(tmpl_name)[0]
            camel_case_name = ''.join(word.capitalize() for word in base_name.split('_'))

        sub_prompt_class = type(
            camel_case_name,
            (BasePrompt,),
            {
                "template_path": template.template_path,
                "template_desc": template.template_desc,
            }
        )

        try:
            instance: BasePrompt = sub_prompt_class()

            if prompt:
                instance.load_from_string(prompt=prompt)

            instance.verbose = self.verbose

            instance.add_llm(model=model)
            instance.prompt_id = f'{str(uuid.uuid4())[:7]}'

            # 保存到提示词列表
            self.prompts.append(instance)
            return instance

        except Exception as e:
            error_msg = f'Failed to create prompt: {str(e)}'
            logging.error(error_msg)
            raise ComponentError(error_msg)

    def run(self, **kwargs) -> ...:
        """
        基于FDLayer开发的Agent，进行调用这个Agent的入口方法，后续并行调用Agent也需要使用该方法
        必须传入query，如果涉及其他参数要传递，请在agent里写一个辅助函数传入。
        """
        raise NotImplementedError(
            f"'{self.__class__.__name__}.run' must be implemented "
        )

    def __or__(self, other):
        from chatbi.agent.foundation.utils.parallel import ParallelFoundationLayer
        """允许在FoundationLayer后面加入 | 实现并行"""
        if isinstance(other, FoundationLayer):
            return ParallelFoundationLayer([self, other])
        elif isinstance(other, ParallelFoundationLayer):
            other.agents.append(self)
            return other
        else:
            raise TypeError("The right-hand side of the 'or' must be an instance of FDLayer or Parallel FDlayer.")

    def add_model_postprocessor(self, postprocessor: BasePostProcessor) -> ...:
        if self.vision_model:
            self.vision_model.add_postprocessor(self.agent_id, postprocessor)
        if self.config.llm:
            self.config.llm.add_postprocessor(self.agent_id, postprocessor)
        pass

    def __rshift__(self, postprocessor: BasePostProcessor) -> 'FoundationLayer':
        """支持使用 >> 在FoundationLayer后面加入对流式输出内容 或者 文本内容 操作的操作"""
        if isinstance(postprocessor, BasePostProcessor):
            self.subprocess.append(postprocessor)
            self.stream.post_processors = self.subprocess
            self.add_model_postprocessor(postprocessor=postprocessor)
            return self
        else:
            raise TypeError('subprocessor must be an instance of Subprocess')

    def stream_to_response(self, generator: BaseGenerator) -> str:
        # 懒得改了，先兼容着
        warnings.warn(
            "The stream_to_response function will be deprecated in wtchatbi v3.9 version."
            " Please use self.stream.stream_to_response instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return self.stream.stream_to_response(generator=generator)

    def stream_response_openai(self,
                               content: str,
                               content_type: str = "char",
                               interval: float = 0) -> None:

        # 懒得改了，先兼容着
        warnings.warn(
            "The stream_response_openai function will be deprecated in wtchatbi v3.9 version."
            " Please use self.stream.stream_message instead.",
            DeprecationWarning,
            stacklevel=2
        )
        return self.stream.stream_message(content=content,
                                          content_type=content_type,
                                          interval=interval)


if __name__ == '__main__':
    from chatbi.models import LLM

    cm = LLM()

    fd = FoundationLayer()

