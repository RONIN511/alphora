from enum import Enum


class HookEvent(str, Enum):
    TOOLS_BEFORE_EXECUTE = "tools.before_execute"
    TOOLS_AFTER_EXECUTE = "tools.after_execute"
    TOOLS_ON_ERROR = "tools.on_error"

    TOOLS_BEFORE_REGISTER = "tools.before_register"
    TOOLS_AFTER_REGISTER = "tools.after_register"
