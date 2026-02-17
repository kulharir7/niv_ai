"""
LLM Provider with Native Function Calling
Supports: OpenAI, Anthropic, Mistral, Ollama
"""
import frappe
import json
from typing import List, Dict, Any, AsyncGenerator, Optional
from dataclasses import dataclass, field

@dataclass
class ToolCall:
    id: str
    name: str
    arguments: Dict[str, Any]

@dataclass
class StreamChunk:
    type: str  # "text", "tool_call", "tool_calls_complete"
    text: Optional[str] = None
    tool_call: Optional[ToolCall] = None

@dataclass
class MCPTool:
    name: str
    description: str
    parameters: Dict[str, Any]
    execute: Any  # callable

class LLMProvider:
    """
    Unified LLM interface with native function calling.
    No agent loops, no ReAct - just direct tool calling.
    """
    
    def __init__(
        self,
        provider: str,
        model: str,
        tools: List[MCPTool],
        system_prompt: str,
        api_key: str = None,
        base_url: str = None
    ):
        self.provider = provider.lower()
        self.model = model
        self.tools = tools
        self.system_prompt = system_prompt
        self.api_key = api_key
        self.base_url = base_url
        self.client = None
        
    async def initialize(self):
        """Initialize the LLM client"""
        if self.provider in ["openai", "mistral", "ollama"]:
            from openai import AsyncOpenAI
            
            if self.provider == "ollama":
                self.client = AsyncOpenAI(
                    base_url=self.base_url or "http://localhost:11434/v1",
                    api_key="ollama"
                )
            else:
                self.client = AsyncOpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url
                )
                
        elif self.provider == "anthropic":
            from anthropic import AsyncAnthropic
            self.client = AsyncAnthropic(api_key=self.api_key)
            
        elif self.provider == "google":
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self.client = genai
            
    def _tools_to_openai_format(self) -> List[Dict]:
        """Convert MCP tools to OpenAI function calling format"""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters
                }
            }
            for tool in self.tools
        ]
        
    def _tools_to_anthropic_format(self) -> List[Dict]:
        """Convert MCP tools to Anthropic tool format"""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.parameters
            }
            for tool in self.tools
        ]
        
    async def generate(
        self,
        messages: List[Dict],
        stream: bool = True
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Generate response with function calling support.
        Yields StreamChunk for text or tool calls.
        """
        # Add system prompt
        full_messages = [
            {"role": "system", "content": self.system_prompt},
            *messages
        ]
        
        if self.provider in ["openai", "mistral", "ollama"]:
            async for chunk in self._generate_openai(full_messages, stream):
                yield chunk
        elif self.provider == "anthropic":
            async for chunk in self._generate_anthropic(full_messages, stream):
                yield chunk
        elif self.provider == "google":
            async for chunk in self._generate_google(full_messages, stream):
                yield chunk
                
    async def _generate_openai(
        self,
        messages: List[Dict],
        stream: bool
    ) -> AsyncGenerator[StreamChunk, None]:
        """OpenAI-compatible generation with function calling"""
        
        tools = self._tools_to_openai_format() if self.tools else None
        
        if stream:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice="auto" if tools else None,
                stream=True
            )
            
            tool_calls_buffer = {}
            
            async for chunk in response:
                delta = chunk.choices[0].delta if chunk.choices else None
                
                if not delta:
                    continue
                    
                # Handle tool calls
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_buffer:
                            tool_calls_buffer[idx] = {
                                "id": tc.id or "",
                                "name": "",
                                "arguments": ""
                            }
                        if tc.id:
                            tool_calls_buffer[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_buffer[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls_buffer[idx]["arguments"] += tc.function.arguments
                                
                # Handle text content
                elif delta.content:
                    yield StreamChunk(type="text", text=delta.content)
                    
                # Check if done
                if chunk.choices[0].finish_reason == "tool_calls":
                    for idx, tc_data in tool_calls_buffer.items():
                        try:
                            args = json.loads(tc_data["arguments"]) if tc_data["arguments"] else {}
                        except:
                            args = {}
                        yield StreamChunk(
                            type="tool_call",
                            tool_call=ToolCall(
                                id=tc_data["id"],
                                name=tc_data["name"],
                                arguments=args
                            )
                        )
                    yield StreamChunk(type="tool_calls_complete")
        else:
            # Non-streaming
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice="auto" if tools else None
            )
            
            choice = response.choices[0]
            
            if choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    except:
                        args = {}
                    yield StreamChunk(
                        type="tool_call",
                        tool_call=ToolCall(
                            id=tc.id,
                            name=tc.function.name,
                            arguments=args
                        )
                    )
                yield StreamChunk(type="tool_calls_complete")
            elif choice.message.content:
                yield StreamChunk(type="text", text=choice.message.content)
                
    async def _generate_anthropic(
        self,
        messages: List[Dict],
        stream: bool
    ) -> AsyncGenerator[StreamChunk, None]:
        """Anthropic generation with tool use"""
        
        # Extract system message
        system = None
        chat_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                chat_messages.append(msg)
                
        tools = self._tools_to_anthropic_format() if self.tools else None
        
        if stream:
            async with self.client.messages.stream(
                model=self.model,
                max_tokens=4096,
                system=system,
                messages=chat_messages,
                tools=tools
            ) as response:
                async for event in response:
                    if event.type == "content_block_delta":
                        if hasattr(event.delta, "text"):
                            yield StreamChunk(type="text", text=event.delta.text)
                            
                # After stream, check for tool calls
                final = await response.get_final_message()
                for block in final.content:
                    if block.type == "tool_use":
                        yield StreamChunk(
                            type="tool_call",
                            tool_call=ToolCall(
                                id=block.id,
                                name=block.name,
                                arguments=block.input
                            )
                        )
                if any(b.type == "tool_use" for b in final.content):
                    yield StreamChunk(type="tool_calls_complete")
        else:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system,
                messages=chat_messages,
                tools=tools
            )
            
            for block in response.content:
                if block.type == "text":
                    yield StreamChunk(type="text", text=block.text)
                elif block.type == "tool_use":
                    yield StreamChunk(
                        type="tool_call",
                        tool_call=ToolCall(
                            id=block.id,
                            name=block.name,
                            arguments=block.input
                        )
                    )
            if any(b.type == "tool_use" for b in response.content):
                yield StreamChunk(type="tool_calls_complete")
                
    async def _generate_google(
        self,
        messages: List[Dict],
        stream: bool
    ) -> AsyncGenerator[StreamChunk, None]:
        """Google/Gemini generation"""
        # Simplified - Google has different tool calling API
        model = self.client.GenerativeModel(self.model)
        
        # Convert messages format
        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [msg["content"]]})
            
        if stream:
            response = await model.generate_content_async(
                contents,
                stream=True
            )
            async for chunk in response:
                if chunk.text:
                    yield StreamChunk(type="text", text=chunk.text)
        else:
            response = await model.generate_content_async(contents)
            yield StreamChunk(type="text", text=response.text)


def get_llm_provider(tools: List[MCPTool] = None, system_prompt: str = "") -> LLMProvider:
    """Factory function to get configured LLM provider"""
    from niv_ai.niv_core.utils import get_niv_settings
    settings = get_niv_settings()
    
    provider = (settings.get("default_provider") or "ollama").lower()
    model = settings.get("default_model") or "mistral"
    api_key = settings.get("api_key") or ""
    base_url = settings.get("base_url") or ""
    
    return LLMProvider(
        provider=provider,
        model=model,
        tools=tools or [],
        system_prompt=system_prompt,
        api_key=api_key,
        base_url=base_url
    )
