from typing import Any

from pydantic import BaseModel, Field


class AgentChatRequest(BaseModel):
    periodId: int | None = None
    message: str = Field(min_length=1)


class AgentToolCall(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    resultSummary: str | None = None


class AgentSource(BaseModel):
    label: str
    tool: str


class AgentHighlight(BaseModel):
    label: str
    value: str


class AgentChatResponse(BaseModel):
    answer: str
    toolCalls: list[AgentToolCall] = Field(default_factory=list)
    sources: list[AgentSource] = Field(default_factory=list)
    highlights: list[AgentHighlight] = Field(default_factory=list)
