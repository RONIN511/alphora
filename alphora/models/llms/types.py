from typing import List, Dict, Any, Optional


class ToolCall(list):
    """
    本质上是一个列表，但携带了额外的元数据（如 usage）
    """
    def __init__(self, tool_calls: List[Dict[str, Any]], content: Optional[str] = None):
        super().__init__(tool_calls)

        self.content = content

    def __repr__(self):

        if self.content:
            return f"{self.content}"

        elif self:
            return super().__repr__()

