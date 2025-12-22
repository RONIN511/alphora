import inspect
from typing import Type, Dict, Any

from alphora.agent.base import BaseAgent
from alphora.server.openai_request_body import OpenAIRequest


class AgentValidationError(ValueError):
    """Agent校验异常"""
    pass


def validate_agent_class(agent_cls: Type[BaseAgent]) -> None:
    """
    校验Agent类合法性
    :param agent_cls: Agent类
    :raise AgentValidationError: 校验失败
    """
    if not inspect.isclass(agent_cls) or not issubclass(agent_cls, BaseAgent):
        raise AgentValidationError(
            f"agent_cls必须是BaseAgent子类，当前类型: {type(agent_cls)}"
        )


def validate_agent_method(
        agent_cls: Type[BaseAgent],
        agent_init_kwargs: Dict[str, Any],
        method_name: str
) -> None:
    """
    校验Agent方法合法性
    :param agent_cls: Agent类
    :param agent_init_kwargs: Agent初始化参数
    :param method_name: 方法名
    :raise AgentValidationError: 校验失败
    """
    # 创建临时实例校验方法
    temp_agent = agent_cls(** agent_init_kwargs)

    # 校验方法存在性
    if not hasattr(temp_agent, method_name):
        raise AgentValidationError(
            f"Agent类 {agent_cls.__name__} 不存在方法: {method_name}"
        )

    # 校验方法是异步的
    method = getattr(temp_agent, method_name)
    if not inspect.iscoroutinefunction(method):
        raise AgentValidationError(
            f"方法 {method_name} 必须是async def定义的异步方法"
        )

    # 校验方法参数
    sig = inspect.signature(method)
    params = list(sig.parameters.values())
    if len(params) != 1:
        raise AgentValidationError(
            f"方法 {method_name} 必须且只能有一个参数（OpenAIRequest类型），当前参数数: {len(params)}"
        )

    param = params[0]
    if param.annotation is not OpenAIRequest:
        raise AgentValidationError(
            f"方法 {method_name} 的参数必须注解为OpenAIRequest，当前注解: {param.annotation}"
        )
