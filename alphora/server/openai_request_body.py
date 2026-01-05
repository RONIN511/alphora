from pydantic import BaseModel, Field, model_validator, ConfigDict, PrivateAttr
from typing import Optional, Dict, Any, List, Literal, Annotated, Union
from typing_extensions import TypedDict


class Message(TypedDict, total=False):
    role: str
    content: str | Dict[str, Any] | List[Any]


class OpenAIRequest(BaseModel):

    model_config = ConfigDict(extra="allow", strict=True)

    _headers: Dict[str, Any] = PrivateAttr(default_factory=dict)

    model: str = Field(default="", description="The model to use")

    messages: List[Message] = Field(
        default_factory=lambda: [{
            "role": "system",
            "content": "You are a helpful assistant."
        }],
        description="List of chat messages with role (system, user, assistant, or file name),"
                    " content (Base64-encoded file or other data), and optional metadata"
    )

    stream: bool = Field(default=True, description="Enable streaming response")
    user: Optional[str] = Field(default=None, description="User identifier")
    session_id: Optional[str] = Field(default=None, description="Session ID")

    def get_user_query(self) -> str:
        """
        Extracts the user's query from the messages list.
        Returns the content of the first message with role 'user', or empty string if none exists.
        """
        for message in self.messages:
            if message.get('role') == 'user':
                content = message.get('content', '')
                return str(content) if content is not None else ''
        return ''

    def set_headers(self, headers: Dict[str, Any]):
        """供外部（Router）调用，注入 headers"""
        self._headers = headers

    def get_header(self, key: str | None = None, default: Any = None) -> Any:
        """
        获取 Header 信息
        key: header 名称
        """
        if key is None and default is None:
            return self._headers

        return self._headers.get(key.lower(), default)
