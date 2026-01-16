class ToolError(Exception):
    """工具组件的基础异常"""
    pass


class ToolRegistrationError(ToolError):
    """注册工具时发生的错误（如重名、Schema解析失败）"""
    pass


class ToolValidationError(ToolError):
    """参数验证失败"""
    pass


class ToolExecutionError(ToolError):
    """工具执行过程中发生的运行时错误"""
    pass
