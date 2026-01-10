"""
Router 编排器 - 条件路由

特性：
1. 根据条件路由到不同Agent
2. 支持多种路由策略（规则、LLM、自定义）
3. 支持默认路由
4. 支持路由链
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union, Awaitable
from enum import Enum

logger = logging.getLogger(__name__)


class RouteStrategy(str, Enum):
    """路由策略"""
    RULE_BASED = "rule_based"      # 基于规则
    LLM_BASED = "llm_based"        # 基于LLM判断
    KEYWORD = "keyword"            # 基于关键词
    REGEX = "regex"                # 基于正则表达式
    CUSTOM = "custom"              # 自定义函数


@dataclass
class RouterRule:
    """
    路由规则
    
    示例：
    ```python
    # 规则路由
    rule = RouterRule(
        name="tech_support",
        condition=lambda ctx: ctx.get("category") == "tech",
        handler=tech_agent.handle
    )
    
    # 关键词路由
    rule = RouterRule(
        name="billing",
        keywords=["账单", "支付", "退款"],
        handler=billing_agent.handle
    )
    
    # 正则路由
    rule = RouterRule(
        name="order_query",
        pattern=r"订单.*(\d{10,})",
        handler=order_agent.query
    )
    ```
    """
    name: str
    handler: Callable[..., Awaitable[Any]]
    condition: Optional[Callable[[Dict], bool]] = None
    keywords: Optional[List[str]] = None
    pattern: Optional[str] = None  # 正则表达式
    priority: int = 0  # 优先级，数字越大优先级越高
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def matches(self, context: Dict[str, Any], query: str = "") -> bool:
        """检查是否匹配此规则"""
        # 条件匹配
        if self.condition:
            return self.condition(context)
        
        # 关键词匹配
        if self.keywords:
            return any(kw in query for kw in self.keywords)
        
        # 正则匹配
        if self.pattern:
            return bool(re.search(self.pattern, query))
        
        return False


@dataclass
class RouteResult:
    """路由结果"""
    rule_name: str
    matched: bool
    output: Any = None
    error: Optional[str] = None
    route_reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class Router:
    """
    Router 编排器
    
    根据条件将请求路由到不同的Agent。
    
    使用示例：
    ```python
    # 创建Router
    router = Router(name="customer_service")
    
    # 添加路由规则
    router.add_rule(RouterRule(
        name="tech_support",
        keywords=["技术", "故障", "bug"],
        handler=tech_agent.handle,
        priority=10
    ))
    
    router.add_rule(RouterRule(
        name="sales",
        keywords=["价格", "购买", "优惠"],
        handler=sales_agent.handle,
        priority=5
    ))
    
    # 设置默认处理器
    router.set_default(general_agent.handle)
    
    # 路由请求
    result = await router.route(
        query="我的订单出了技术问题",
        context={"user_id": "123"}
    )
    ```
    """
    
    def __init__(
        self,
        name: str = "router",
        rules: Optional[List[RouterRule]] = None,
        default_handler: Optional[Callable[..., Awaitable[Any]]] = None,
        llm: Optional[Any] = None,  # 用于LLM路由
        route_prompt: Optional[str] = None
    ):
        self.name = name
        self.rules: List[RouterRule] = rules or []
        self.default_handler = default_handler
        self.llm = llm
        self.route_prompt = route_prompt or self._default_route_prompt()
        
        # 按优先级排序
        self._sort_rules()
    
    def _default_route_prompt(self) -> str:
        """默认的LLM路由提示词"""
        return """根据用户的问题，选择最合适的处理类别。

可用类别：
{categories}

用户问题：{query}

请只返回类别名称，不要返回其他内容。"""
    
    def _sort_rules(self):
        """按优先级排序规则"""
        self.rules.sort(key=lambda r: r.priority, reverse=True)
    
    def add_rule(self, rule: RouterRule) -> "Router":
        """添加路由规则"""
        self.rules.append(rule)
        self._sort_rules()
        return self
    
    def add_rules(self, rules: List[RouterRule]) -> "Router":
        """批量添加路由规则"""
        self.rules.extend(rules)
        self._sort_rules()
        return self
    
    def remove_rule(self, name: str) -> bool:
        """移除路由规则"""
        for i, rule in enumerate(self.rules):
            if rule.name == name:
                self.rules.pop(i)
                return True
        return False
    
    def set_default(self, handler: Callable[..., Awaitable[Any]]) -> "Router":
        """设置默认处理器"""
        self.default_handler = handler
        return self
    
    async def _llm_route(self, query: str, context: Dict[str, Any]) -> Optional[str]:
        """使用LLM进行路由"""
        if not self.llm:
            return None
        
        # 构建类别描述
        categories = "\n".join([
            f"- {rule.name}: {rule.description or '无描述'}"
            for rule in self.rules
        ])
        
        prompt = self.route_prompt.format(
            categories=categories,
            query=query
        )
        
        try:
            response = await self.llm.ainvoke(prompt)
            response = response.strip()
            
            # 检查响应是否匹配已知规则
            for rule in self.rules:
                if rule.name.lower() in response.lower():
                    return rule.name
            
            return None
            
        except Exception as e:
            logger.error(f"LLM routing failed: {e}")
            return None
    
    async def route(
        self,
        query: str = "",
        context: Optional[Dict[str, Any]] = None,
        strategy: RouteStrategy = RouteStrategy.RULE_BASED,
        **kwargs
    ) -> RouteResult:
        """
        路由请求
        
        Args:
            query: 用户查询
            context: 上下文信息
            strategy: 路由策略
            **kwargs: 传递给handler的额外参数
        
        Returns:
            路由结果
        """
        context = context or {}
        context["query"] = query
        
        matched_rule: Optional[RouterRule] = None
        route_reason = ""
        
        # 根据策略选择路由方式
        if strategy == RouteStrategy.LLM_BASED and self.llm:
            # LLM路由
            rule_name = await self._llm_route(query, context)
            if rule_name:
                for rule in self.rules:
                    if rule.name == rule_name:
                        matched_rule = rule
                        route_reason = f"LLM selected: {rule_name}"
                        break
        else:
            # 规则路由
            for rule in self.rules:
                if rule.matches(context, query):
                    matched_rule = rule
                    route_reason = f"Rule matched: {rule.name}"
                    break
        
        # 如果没有匹配的规则，使用默认处理器
        if matched_rule is None:
            if self.default_handler:
                logger.info(f"Router '{self.name}': using default handler")
                try:
                    output = await self.default_handler(query=query, context=context, **kwargs)
                    return RouteResult(
                        rule_name="default",
                        matched=True,
                        output=output,
                        route_reason="No rule matched, using default handler"
                    )
                except Exception as e:
                    return RouteResult(
                        rule_name="default",
                        matched=False,
                        error=str(e),
                        route_reason="Default handler failed"
                    )
            else:
                return RouteResult(
                    rule_name="none",
                    matched=False,
                    error="No matching rule and no default handler",
                    route_reason="No rule matched"
                )
        
        # 执行匹配的规则
        logger.info(f"Router '{self.name}': routed to '{matched_rule.name}'")
        
        try:
            output = await matched_rule.handler(query=query, context=context, **kwargs)
            return RouteResult(
                rule_name=matched_rule.name,
                matched=True,
                output=output,
                route_reason=route_reason
            )
        except Exception as e:
            logger.error(f"Router handler failed: {e}")
            return RouteResult(
                rule_name=matched_rule.name,
                matched=True,
                error=str(e),
                route_reason=route_reason
            )
    
    async def route_all(
        self,
        query: str = "",
        context: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> List[RouteResult]:
        """
        路由到所有匹配的规则（并行执行）
        
        用于需要多个Agent同时处理的场景
        """
        context = context or {}
        context["query"] = query
        
        matched_rules = [
            rule for rule in self.rules
            if rule.matches(context, query)
        ]
        
        if not matched_rules:
            return []
        
        # 并行执行所有匹配的处理器
        tasks = [
            rule.handler(query=query, context=context, **kwargs)
            for rule in matched_rules
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        route_results = []
        for rule, result in zip(matched_rules, results):
            if isinstance(result, Exception):
                route_results.append(RouteResult(
                    rule_name=rule.name,
                    matched=True,
                    error=str(result)
                ))
            else:
                route_results.append(RouteResult(
                    rule_name=rule.name,
                    matched=True,
                    output=result
                ))
        
        return route_results
    
    def get_rules_info(self) -> List[Dict[str, Any]]:
        """获取所有规则的信息"""
        return [
            {
                "name": rule.name,
                "description": rule.description,
                "priority": rule.priority,
                "keywords": rule.keywords,
                "pattern": rule.pattern,
                "has_condition": rule.condition is not None
            }
            for rule in self.rules
        ]
    
    def __repr__(self) -> str:
        rule_names = [r.name for r in self.rules]
        return f"Router(name='{self.name}', rules={rule_names})"


# 便捷装饰器
def route(
    router: Router,
    name: str,
    keywords: Optional[List[str]] = None,
    pattern: Optional[str] = None,
    condition: Optional[Callable[[Dict], bool]] = None,
    priority: int = 0,
    description: str = ""
):
    """
    路由装饰器
    
    使用示例：
    ```python
    router = Router()
    
    @route(router, name="greeting", keywords=["你好", "hi"])
    async def handle_greeting(query: str, context: dict):
        return "Hello!"
    ```
    """
    def decorator(func: Callable[..., Awaitable[Any]]):
        rule = RouterRule(
            name=name,
            handler=func,
            keywords=keywords,
            pattern=pattern,
            condition=condition,
            priority=priority,
            description=description
        )
        router.add_rule(rule)
        return func
    return decorator
