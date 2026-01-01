from typing import Any, Dict, List, Optional, Callable
from pydantic import BaseModel, Field

class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: Optional[Any] = None
    id: Optional[Any] = None

class JsonRpcResponse(BaseModel):
    jsonrpc: str = "2.0"
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    id: Optional[Any] = None

class McpHandler:
    def __init__(self):
        self.methods: Dict[str, Callable] = {}

    def register_tool(self, name: str, func: Callable):
        """Register a function as an MCP tool."""
        self.methods[name] = func

    async def handle_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming JSON-RPC request."""
        try:
            req = JsonRpcRequest(**request_data)
        except Exception as e:
            return self._error_response(None, -32700, "Parse error")

        if req.method not in self.methods:
            return self._error_response(req.id, -32601, "Method not found")

        try:
            # Execute method
            # Support both dict params and list params (positional)
            # For simplicity, assuming params is a dict for now as per plan
            func = self.methods[req.method]
            if isinstance(req.params, dict):
                result = await func(**req.params) if self._is_async(func) else func(**req.params)
            elif isinstance(req.params, list):
                result = await func(*req.params) if self._is_async(func) else func(*req.params)
            else:
                result = await func() if self._is_async(func) else func()
            
            return JsonRpcResponse(result=result, id=req.id).dict(exclude_none=True)

        except Exception as e:
            import traceback
            traceback.print_exc()
            return self._error_response(req.id, -32000, str(e))

    def _error_response(self, req_id, code, message):
        return JsonRpcResponse(
            error={"code": code, "message": message},
            id=req_id
        ).dict(exclude_none=True)

    def _is_async(self, func):
        import inspect
        return inspect.iscoroutinefunction(func)

# Global MCP Registry
mcp_registry = McpHandler()
