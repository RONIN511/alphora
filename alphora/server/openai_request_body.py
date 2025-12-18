from pydantic import BaseModel, Field, model_validator, ConfigDict
from typing import Optional, Dict, Any, List, Literal, Annotated, Union
from typing_extensions import TypedDict


class Message(TypedDict, total=False):
    role: str
    content: str | Dict[str, Any] | List[Any]


class OpenAIRequest(BaseModel):

    model_config = ConfigDict(extra="allow", strict=True)

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
