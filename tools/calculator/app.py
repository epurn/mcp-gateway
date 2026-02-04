"""Exact computation tool service with deterministic math and strict validation."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from decimal import (
    Decimal,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    ROUND_HALF_EVEN,
    Context,
    localcontext,
)
from typing import Annotated, Dict, Iterable, List, Literal, Optional, Tuple, Union

from builtins import TimeoutError

from anyio import fail_after
from anyio.to_thread import run_sync
from fastapi import FastAPI, HTTPException
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    TypeAdapter,
    ValidationError,
    field_validator,
)
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

MAX_BODY_BYTES = int(os.getenv("MAX_BODY_BYTES", "16384"))
MAX_LIST_ITEMS = int(os.getenv("MAX_LIST_ITEMS", "1000"))
MAX_NUMBER_DIGITS = int(os.getenv("MAX_NUMBER_DIGITS", "200"))
MAX_PRECISION = int(os.getenv("MAX_PRECISION", "100"))
DEFAULT_PRECISION = int(os.getenv("DEFAULT_PRECISION", "28"))
REQUEST_TIMEOUT_MS = int(os.getenv("REQUEST_TIMEOUT_MS", "250"))
MAX_OUTPUT_CHARS = int(os.getenv("MAX_OUTPUT_CHARS", "4096"))
MAX_VALIDATION_ERRORS = int(os.getenv("MAX_VALIDATION_ERRORS", "5"))

NUMERIC_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d+)?|\.\d+)$")

BASE_UNIT_ORDER = ("m", "g", "s")
TOOL_NAME = "exact_compute"


class BodyTooLargeError(Exception):
    """Raised when the request body exceeds the configured limit."""
    pass


class MaxBodySizeMiddleware:
    """Reject requests that exceed the configured body size limit."""

    def __init__(self, app: ASGIApp, max_body_size: int) -> None:
        """Initialize the middleware with an app and size cap.

        Args:
            app: The downstream ASGI application.
            max_body_size: Maximum allowed request body size in bytes.
        """
        self.app = app
        self.max_body_size = max_body_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Enforce size limits before passing control to the app.

        Args:
            scope: ASGI connection scope.
            receive: ASGI receive callable.
            send: ASGI send callable.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        for header, value in scope.get("headers", []):
            if header == b"content-length":
                try:
                    size = int(value)
                except ValueError:
                    size = self.max_body_size + 1
                if size > self.max_body_size:
                    response = JSONResponse(
                        status_code=413,
                        content={"error": "request body too large"},
                    )
                    await response(scope, receive, send)
                    return

        received = 0

        async def receive_wrapper():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                body = message.get("body", b"")
                received += len(body)
                if received > self.max_body_size:
                    raise BodyTooLargeError()
            return message

        try:
            await self.app(scope, receive_wrapper, send)
        except BodyTooLargeError:
            response = JSONResponse(
                status_code=413,
                content={"error": "request body too large"},
            )
            await response(scope, receive, send)


def validate_decimal_string(value: str) -> str:
    """Validate that a string is a bounded decimal representation.

    Args:
        value: Candidate decimal string.

    Returns:
        The original string when valid.

    Raises:
        ValueError: If the string is invalid or exceeds configured limits.
    """
    if not isinstance(value, str):
        raise ValueError("numbers must be strings")
    if not NUMERIC_RE.match(value):
        raise ValueError("invalid decimal format")
    digit_count = sum(1 for ch in value if ch.isdigit())
    if digit_count > MAX_NUMBER_DIGITS:
        raise ValueError("number exceeds max digits")
    return value


def validate_precision(value: Optional[int]) -> int:
    """Validate precision bounds and return a default when absent.

    Args:
        value: Requested precision, if provided.

    Returns:
        A valid precision value.

    Raises:
        ValueError: If the precision is outside configured limits.
    """
    if value is None:
        return DEFAULT_PRECISION
    if not isinstance(value, int):
        raise ValueError("precision must be an integer")
    if value < 1 or value > MAX_PRECISION:
        raise ValueError("precision out of range")
    return value


def decimal_context(precision: int) -> Context:
    """Build a deterministic Decimal context that traps invalid operations.

    Args:
        precision: Significant digits to retain in arithmetic.

    Returns:
        A configured Decimal context.
    """
    context = Context(prec=precision, rounding=ROUND_HALF_EVEN)
    context.traps[DivisionByZero] = True
    context.traps[InvalidOperation] = True
    context.traps[Overflow] = True
    return context


def parse_decimals(values: Iterable[str]) -> List[Decimal]:
    """Parse decimal strings into Decimal values.

    Args:
        values: Iterable of validated decimal strings.

    Returns:
        Parsed Decimal values.
    """
    return [Decimal(value) for value in values]


def format_decimal(value: Decimal) -> str:
    """Format a Decimal deterministically without scientific notation.

    Args:
        value: The Decimal value to format.

    Returns:
        A normalized string representation.
    """
    normalized = value.normalize()
    if normalized.is_zero():
        return "0"
    return format(normalized, "f")


def enforce_output_size(text: str) -> str:
    """Ensure responses remain within the configured size bound.

    Args:
        text: Formatted result string.

    Returns:
        The original text when within size bounds.

    Raises:
        ValueError: If the output exceeds the configured limit.
    """
    if len(text) > MAX_OUTPUT_CHARS:
        raise ValueError("output exceeds size limit")
    return text


def format_validation_errors(exc: ValidationError) -> list[dict[str, object]]:
    """Sanitize validation errors for safe responses.

    Args:
        exc: Validation error instance.

    Returns:
        Limited list of simplified error details.
    """
    details: list[dict[str, object]] = []
    for item in exc.errors()[:MAX_VALIDATION_ERRORS]:
        details.append(
            {
                "loc": list(item.get("loc", [])),
                "msg": item.get("msg", "Invalid value"),
                "type": item.get("type", "value_error"),
            }
        )
    return details


@dataclass(frozen=True)
class UnitDef:
    """Defines a unit conversion factor and base dimensions."""

    to_base: Decimal
    dims: Tuple[int, int, int]


UNITS: Dict[str, UnitDef] = {
    "m": UnitDef(Decimal("1"), (1, 0, 0)),
    "cm": UnitDef(Decimal("0.01"), (1, 0, 0)),
    "mm": UnitDef(Decimal("0.001"), (1, 0, 0)),
    "km": UnitDef(Decimal("1000"), (1, 0, 0)),
    "in": UnitDef(Decimal("0.0254"), (1, 0, 0)),
    "ft": UnitDef(Decimal("0.3048"), (1, 0, 0)),
    "yd": UnitDef(Decimal("0.9144"), (1, 0, 0)),
    "mi": UnitDef(Decimal("1609.344"), (1, 0, 0)),
    "g": UnitDef(Decimal("1"), (0, 1, 0)),
    "kg": UnitDef(Decimal("1000"), (0, 1, 0)),
    "mg": UnitDef(Decimal("0.001"), (0, 1, 0)),
    "lb": UnitDef(Decimal("453.59237"), (0, 1, 0)),
    "s": UnitDef(Decimal("1"), (0, 0, 1)),
    "min": UnitDef(Decimal("60"), (0, 0, 1)),
    "h": UnitDef(Decimal("3600"), (0, 0, 1)),
    "day": UnitDef(Decimal("86400"), (0, 0, 1)),
}


def format_unit_dims(dims: Tuple[int, int, int]) -> str:
    """Format base-unit dimensions into a canonical string.

    Args:
        dims: Exponents for (m, g, s) in that order.

    Returns:
        A canonical dimension string.
    """
    parts = []
    for unit, power in zip(BASE_UNIT_ORDER, dims):
        if power == 0:
            continue
        if power == 1:
            parts.append(unit)
        else:
            parts.append(f"{unit}^{power}")
    return "*".join(parts) if parts else "1"


def add_dims(left: Tuple[int, int, int], right: Tuple[int, int, int]) -> Tuple[int, int, int]:
    """Add base dimensions for multiplication semantics.

    Args:
        left: Left-hand dimension exponents.
        right: Right-hand dimension exponents.

    Returns:
        Combined dimension exponents.
    """
    return (left[0] + right[0], left[1] + right[1], left[2] + right[2])


def sub_dims(left: Tuple[int, int, int], right: Tuple[int, int, int]) -> Tuple[int, int, int]:
    """Subtract base dimensions for division semantics.

    Args:
        left: Left-hand dimension exponents.
        right: Right-hand dimension exponents.

    Returns:
        Resulting dimension exponents.
    """
    return (left[0] - right[0], left[1] - right[1], left[2] - right[2])


class StrictModel(BaseModel):
    """Base model that forbids unknown fields for strict schemas."""

    model_config = ConfigDict(extra="forbid")


class ArithmeticParams(StrictModel):
    """Parameters for exact arithmetic operations."""

    operator: Literal["add", "sub", "mul", "div"]
    operands: List[StrictStr] = Field(min_length=1)
    precision: Optional[StrictInt] = None

    @field_validator("operands")
    @classmethod
    def validate_operands(cls, values: List[str]) -> List[str]:
        """Validate operand count and formats.

        Args:
            values: Operand strings.

        Returns:
            Validated operand strings.

        Raises:
            ValueError: If count or format validation fails.
        """
        if len(values) > MAX_LIST_ITEMS:
            raise ValueError("too many operands")
        return [validate_decimal_string(value) for value in values]

    @field_validator("precision")
    @classmethod
    def validate_precision_field(cls, value: Optional[int]) -> Optional[int]:
        """Validate optional precision for arithmetic parameters.

        Args:
            value: Optional precision.

        Returns:
            The validated precision or None.
        """
        if value is None:
            return None
        return validate_precision(value)


class StatisticsParams(StrictModel):
    """Parameters for exact statistics operations."""

    function: Literal[
        "mean",
        "median",
        "variance",
        "stdev",
        "min",
        "max",
        "sum",
        "count",
    ]
    values: List[StrictStr] = Field(min_length=1)
    precision: Optional[StrictInt] = None
    sample: StrictBool = False

    @field_validator("values")
    @classmethod
    def validate_values(cls, values: List[str]) -> List[str]:
        """Validate value count and formats.

        Args:
            values: Input value strings.

        Returns:
            Validated input value strings.

        Raises:
            ValueError: If count or format validation fails.
        """
        if len(values) > MAX_LIST_ITEMS:
            raise ValueError("too many values")
        return [validate_decimal_string(value) for value in values]

    @field_validator("precision")
    @classmethod
    def validate_precision_field(cls, value: Optional[int]) -> Optional[int]:
        """Validate optional precision for statistics parameters.

        Args:
            value: Optional precision.

        Returns:
            The validated precision or None.
        """
        if value is None:
            return None
        return validate_precision(value)


class UnitValue(StrictModel):
    """Value and unit pair for unit-aware operations."""

    value: StrictStr
    unit: StrictStr

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: str) -> str:
        """Validate decimal formatting for unit values.

        Args:
            value: Input value string.

        Returns:
            Validated value string.
        """
        return validate_decimal_string(value)

    @field_validator("unit")
    @classmethod
    def validate_unit(cls, value: str) -> str:
        """Ensure the unit is in the supported unit list.

        Args:
            value: Unit identifier.

        Returns:
            Validated unit identifier.
        """
        if value not in UNITS:
            raise ValueError("unsupported unit")
        return value


class UnitConvertParams(StrictModel):
    """Parameters for unit conversion operations."""

    action: Literal["convert"]
    value: StrictStr
    unit: StrictStr
    to_unit: StrictStr
    precision: Optional[StrictInt] = None

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: str) -> str:
        """Validate decimal formatting for conversion values.

        Args:
            value: Input value string.

        Returns:
            Validated value string.
        """
        return validate_decimal_string(value)

    @field_validator("unit", "to_unit")
    @classmethod
    def validate_unit(cls, value: str) -> str:
        """Ensure conversion units are supported.

        Args:
            value: Unit identifier.

        Returns:
            Validated unit identifier.
        """
        if value not in UNITS:
            raise ValueError("unsupported unit")
        return value

    @field_validator("precision")
    @classmethod
    def validate_precision_field(cls, value: Optional[int]) -> Optional[int]:
        """Validate optional precision for conversions.

        Args:
            value: Optional precision.

        Returns:
            The validated precision or None.
        """
        if value is None:
            return None
        return validate_precision(value)


class UnitArithmeticParams(StrictModel):
    """Parameters for unit-aware arithmetic operations."""

    action: Literal["arithmetic"]
    operator: Literal["add", "sub", "mul", "div"]
    left: UnitValue
    right: UnitValue
    result_unit: Optional[StrictStr] = None
    precision: Optional[StrictInt] = None

    @field_validator("result_unit")
    @classmethod
    def validate_result_unit(cls, value: Optional[str]) -> Optional[str]:
        """Validate the requested result unit, if provided.

        Args:
            value: Optional unit identifier.

        Returns:
            The validated unit identifier or None.
        """
        if value is None:
            return None
        if value not in UNITS:
            raise ValueError("unsupported result unit")
        return value

    @field_validator("precision")
    @classmethod
    def validate_precision_field(cls, value: Optional[int]) -> Optional[int]:
        """Validate optional precision for unit arithmetic.

        Args:
            value: Optional precision.

        Returns:
            The validated precision or None.
        """
        if value is None:
            return None
        return validate_precision(value)


class ArithmeticRequest(StrictModel):
    """Request wrapper for arithmetic operations."""

    operation: Literal["arithmetic"]
    params: ArithmeticParams


class StatisticsRequest(StrictModel):
    """Request wrapper for statistics operations."""

    operation: Literal["statistics"]
    params: StatisticsParams


class UnitRequest(StrictModel):
    """Request wrapper for unit operations."""

    operation: Literal["unit"]
    params: UnitConvertParams | UnitArithmeticParams


ComputeRequest = Annotated[
    Union[ArithmeticRequest, StatisticsRequest, UnitRequest],
    Field(discriminator="operation"),
]

COMPUTE_REQUEST_ADAPTER = TypeAdapter(ComputeRequest)


class ComputeResponse(StrictModel):
    """Response payload for compute operations."""

    operation: str
    result: str
    unit: Optional[str] = None


class MCPToolCallParams(StrictModel):
    """Parameters for MCP tool invocation."""

    name: StrictStr
    arguments: dict[str, object] = Field(default_factory=dict)


class MCPRequest(StrictModel):
    """JSON-RPC request envelope for MCP tool calls."""

    jsonrpc: Literal["2.0"] = Field(default="2.0")
    method: StrictStr
    params: MCPToolCallParams
    id: StrictStr | StrictInt


class MCPErrorDetail(StrictModel):
    """JSON-RPC error detail payload."""

    code: StrictInt
    message: StrictStr
    data: object | None = None


class MCPResponse(StrictModel):
    """JSON-RPC response envelope for MCP tool calls."""

    jsonrpc: Literal["2.0"] = Field(default="2.0")
    result: object | None = None
    error: MCPErrorDetail | None = None
    id: StrictStr | StrictInt

    @classmethod
    def success(cls, request_id: str | int, result: object) -> "MCPResponse":
        """Create a success response.

        Args:
            request_id: Request identifier.
            result: Result payload.

        Returns:
            MCPResponse with a result.
        """
        return cls(id=request_id, result=result)

    @classmethod
    def error_response(
        cls,
        request_id: str | int,
        code: int,
        message: str,
        data: object | None = None,
    ) -> "MCPResponse":
        """Create an error response.

        Args:
            request_id: Request identifier.
            code: Error code.
            message: Error message.
            data: Optional error metadata.

        Returns:
            MCPResponse with an error.
        """
        return cls(id=request_id, error=MCPErrorDetail(code=code, message=message, data=data))


class MCPErrorCodes:
    """MCP/JSON-RPC error codes."""

    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    TOOL_NOT_FOUND = -32001
    BACKEND_TIMEOUT = -32003


app = FastAPI(title="Exact Computation Tool", version="1.0")
app.add_middleware(MaxBodySizeMiddleware, max_body_size=MAX_BODY_BYTES)


@app.get("/health")
async def health() -> Dict[str, str]:
    """Return service health for liveness checks.

    Returns:
        Health status payload.
    """
    return {"status": "ok"}


@app.get("/mcp/tools")
async def list_mcp_tools() -> dict[str, list[dict]]:
    """Return available MCP tools with their schemas."""
    return {
        "tools": [
            {
                "name": "exact_calculate",
                "description": "Perform exact arithmetic operations (add, subtract, multiply, divide) with configurable precision",
                "category": "math",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "operator": {
                            "type": "string",
                            "enum": ["add", "sub", "mul", "div"],
                            "description": "Arithmetic operation to perform"
                        },
                        "operands": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 1,
                            "description": "Decimal numbers as strings"
                        },
                        "precision": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 100,
                            "description": "Significant digits (default: 28)"
                        }
                    },
                    "required": ["operator", "operands"]
                }
            },
            {
                "name": "exact_statistics",
                "description": "Calculate exact statistics (mean, median, variance, standard deviation, min, max, sum, count) over decimal values",
                "category": "math",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "function": {
                            "type": "string",
                            "enum": ["mean", "median", "variance", "stdev", "min", "max", "sum", "count"],
                            "description": "Statistical function to compute"
                        },
                        "values": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 1,
                            "description": "Decimal numbers as strings"
                        },
                        "precision": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 100,
                            "description": "Significant digits (default: 28)"
                        },
                        "sample": {
                            "type": "boolean",
                            "description": "Use sample variance/stdev (N-1) instead of population (default: false)"
                        }
                    },
                    "required": ["function", "values"]
                }
            },
            {
                "name": "exact_convert_units",
                "description": "Convert values between compatible units (length: m/cm/mm/km/in/ft/yd/mi, mass: g/kg/mg/lb, time: s/min/h/day)",
                "category": "math",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "value": {
                            "type": "string",
                            "description": "Decimal number as string"
                        },
                        "from_unit": {
                            "type": "string",
                            "enum": ["m", "cm", "mm", "km", "in", "ft", "yd", "mi", "g", "kg", "mg", "lb", "s", "min", "h", "day"],
                            "description": "Source unit"
                        },
                        "to_unit": {
                            "type": "string",
                            "enum": ["m", "cm", "mm", "km", "in", "ft", "yd", "mi", "g", "kg", "mg", "lb", "s", "min", "h", "day"],
                            "description": "Target unit"
                        },
                        "precision": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 100,
                            "description": "Significant digits (default: 28)"
                        }
                    },
                    "required": ["value", "from_unit", "to_unit"]
                }
            },
            {
                "name": "exact_unit_arithmetic",
                "description": "Perform arithmetic on values with units, handling dimension checking (e.g., 2m + 3ft = 2.9144m)",
                "category": "math",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "operator": {
                            "type": "string",
                            "enum": ["add", "sub", "mul", "div"],
                            "description": "Arithmetic operation"
                        },
                        "left": {
                            "type": "object",
                            "properties": {
                                "value": {"type": "string"},
                                "unit": {"type": "string"}
                            },
                            "required": ["value", "unit"]
                        },
                        "right": {
                            "type": "object",
                            "properties": {
                                "value": {"type": "string"},
                                "unit": {"type": "string"}
                            },
                            "required": ["value", "unit"]
                        },
                        "result_unit": {
                            "type": "string",
                            "description": "Optional desired output unit"
                        },
                        "precision": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 100
                        }
                    },
                    "required": ["operator", "left", "right"]
                }
            }
        ]
    }


@app.post("/v1/compute", response_model=ComputeResponse)
async def compute(request: ComputeRequest) -> ComputeResponse:
    """Execute a compute request with a strict timeout.

    Args:
        request: Structured compute request.

    Returns:
        Computation result payload.

    Raises:
        HTTPException: For validation or execution failures.
    """
    try:
        return await execute_compute(request)
    except TimeoutError as exc:
        raise HTTPException(status_code=408, detail={"error": "timeout"}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
    except (DivisionByZero, InvalidOperation, Overflow) as exc:
        raise HTTPException(status_code=400, detail={"error": "invalid arithmetic operation"}) from exc


@app.post("/mcp", response_model=MCPResponse)
async def mcp_tool_call(request: MCPRequest) -> MCPResponse:
    """Handle MCP tool invocations for multiple exact computation tools.

    Args:
        request: MCP JSON-RPC request envelope.

    Returns:
        MCPResponse with result or error payload.
    """
    if request.method != "tools/call":
        return MCPResponse.error_response(
            request_id=request.id,
            code=MCPErrorCodes.METHOD_NOT_FOUND,
            message="Method not found",
        )

    # Route by tool name
    tool_name = request.params.name
    
    # Map tool names to internal operations
    tool_routing = {
        "exact_calculate": ("arithmetic", ArithmeticParams),
        "exact_statistics": ("statistics", StatisticsParams),
        "exact_convert_units": ("unit", UnitConvertParams),
        "exact_unit_arithmetic": ("unit", UnitArithmeticParams),
    }
    
    if tool_name not in tool_routing:
        # Fallback for backward compatibility or error
        if tool_name == TOOL_NAME:
            # Handle legacy tool name if needed, but for now strict matching
            pass
            
        return MCPResponse.error_response(
            request_id=request.id,
            code=MCPErrorCodes.TOOL_NOT_FOUND,
            message=f"Tool not found: {tool_name}",
        )
    
    operation_type, param_class = tool_routing[tool_name]
    
    try:
        # Validate parameters based on tool type
        if tool_name == "exact_calculate":
            params = ArithmeticParams(**request.params.arguments)
            compute_request = ArithmeticRequest(operation="arithmetic", params=params)
        elif tool_name == "exact_statistics":
            params = StatisticsParams(**request.params.arguments)
            compute_request = StatisticsRequest(operation="statistics", params=params)
        elif tool_name == "exact_convert_units":
            # Map from_unit/to_unit to unit/to_unit for compatibility
            args = request.params.arguments.copy()
            if "from_unit" in args:
                args["unit"] = args.pop("from_unit")
            args["action"] = "convert"
            params = UnitConvertParams(**args)
            compute_request = UnitRequest(operation="unit", params=params)
        elif tool_name == "exact_unit_arithmetic":
            args = request.params.arguments.copy()
            args["action"] = "arithmetic"
            params = UnitArithmeticParams(**args)
            compute_request = UnitRequest(operation="unit", params=params)
            
    except ValidationError as exc:
        return MCPResponse.error_response(
            request_id=request.id,
            code=MCPErrorCodes.INVALID_PARAMS,
            message="Invalid params",
            data={"details": format_validation_errors(exc)},
        )

    try:
        result = await execute_compute(compute_request)
        return MCPResponse.success(request_id=request.id, result=result.model_dump())
    except TimeoutError:
        return MCPResponse.error_response(
            request_id=request.id,
            code=MCPErrorCodes.BACKEND_TIMEOUT,
            message="Timeout",
        )
    except ValueError as exc:
        return MCPResponse.error_response(
            request_id=request.id,
            code=MCPErrorCodes.INVALID_PARAMS,
            message=str(exc),
        )
    except (DivisionByZero, InvalidOperation, Overflow):
        return MCPResponse.error_response(
            request_id=request.id,
            code=MCPErrorCodes.INVALID_PARAMS,
            message="Invalid arithmetic operation",
        )


async def execute_compute(request: ComputeRequest) -> ComputeResponse:
    """Run compute operations with timeout enforcement.

    Args:
        request: Structured compute request.

    Returns:
        ComputeResponse with deterministic result.
    """
    with fail_after(REQUEST_TIMEOUT_MS / 1000):
        return await run_sync(handle_compute, request)


def handle_compute(request: ComputeRequest) -> ComputeResponse:
    """Route compute requests by operation type.

    Args:
        request: Structured compute request.

    Returns:
        Computation result payload.
    """
    if isinstance(request, ArithmeticRequest):
        return compute_arithmetic(request.params)
    if isinstance(request, StatisticsRequest):
        return compute_statistics(request.params)
    if isinstance(request, UnitRequest):
        return compute_unit(request.params)
    raise ValueError("unsupported operation")


def compute_arithmetic(params: ArithmeticParams) -> ComputeResponse:
    """Compute high-precision arithmetic using deterministic decimals.

    Args:
        params: Arithmetic parameters.

    Returns:
        Arithmetic result payload.
    """
    if params.operator in ("sub", "div") and len(params.operands) < 2:
        raise ValueError("sub and div require at least 2 operands")

    precision = validate_precision(params.precision)
    context = decimal_context(precision)

    with localcontext(context):
        operands = parse_decimals(params.operands)
        if params.operator == "add":
            result = sum(operands, Decimal("0"))
        elif params.operator == "sub":
            result = operands[0]
            for value in operands[1:]:
                result -= value
        elif params.operator == "mul":
            result = Decimal("1")
            for value in operands:
                result *= value
        elif params.operator == "div":
            result = operands[0]
            for value in operands[1:]:
                result /= value
        else:
            raise ValueError("unsupported arithmetic operator")

    result_text = enforce_output_size(format_decimal(result))
    return ComputeResponse(operation="arithmetic", result=result_text)


def compute_statistics(params: StatisticsParams) -> ComputeResponse:
    """Compute deterministic statistics over decimal values.

    Args:
        params: Statistics parameters.

    Returns:
        Statistics result payload.
    """
    precision = validate_precision(params.precision)
    context = decimal_context(precision)

    with localcontext(context):
        values = parse_decimals(params.values)
        count = len(values)

        if params.function in ("variance", "stdev") and count < 2:
            raise ValueError("variance and stdev require at least 2 values")

        if params.function == "count":
            result = Decimal(count)
        elif params.function == "sum":
            result = sum(values, Decimal("0"))
        elif params.function == "min":
            result = min(values)
        elif params.function == "max":
            result = max(values)
        elif params.function == "mean":
            result = sum(values, Decimal("0")) / Decimal(count)
        elif params.function == "median":
            values.sort()
            mid = count // 2
            if count % 2 == 1:
                result = values[mid]
            else:
                result = (values[mid - 1] + values[mid]) / Decimal("2")
        elif params.function in ("variance", "stdev"):
            mean = sum(values, Decimal("0")) / Decimal(count)
            variance_sum = sum(((value - mean) ** 2 for value in values), Decimal("0"))
            denom = Decimal(count - 1 if params.sample else count)
            variance = variance_sum / denom
            if params.function == "variance":
                result = variance
            else:
                result = context.sqrt(variance)
        else:
            raise ValueError("unsupported statistics function")

    result_text = enforce_output_size(format_decimal(result))
    return ComputeResponse(operation="statistics", result=result_text)


def compute_unit(params: UnitConvertParams | UnitArithmeticParams) -> ComputeResponse:
    """Compute unit conversions and unit-aware arithmetic.

    Args:
        params: Unit operation parameters.

    Returns:
        Unit-aware result payload.
    """
    if isinstance(params, UnitConvertParams):
        return compute_unit_convert(params)
    if isinstance(params, UnitArithmeticParams):
        return compute_unit_arithmetic(params)
    raise ValueError("unsupported unit action")


def compute_unit_convert(params: UnitConvertParams) -> ComputeResponse:
    """Convert values between compatible units.

    Args:
        params: Unit conversion parameters.

    Returns:
        Unit conversion result payload.
    """
    precision = validate_precision(params.precision)
    context = decimal_context(precision)

    from_unit = UNITS[params.unit]
    to_unit = UNITS[params.to_unit]
    if from_unit.dims != to_unit.dims:
        raise ValueError("incompatible units")

    with localcontext(context):
        value = Decimal(params.value)
        base_value = value * from_unit.to_base
        result = base_value / to_unit.to_base

    result_text = enforce_output_size(format_decimal(result))
    return ComputeResponse(operation="unit", result=result_text, unit=params.to_unit)


def compute_unit_arithmetic(params: UnitArithmeticParams) -> ComputeResponse:
    """Perform arithmetic on unit-bearing values with dimension checks.

    Args:
        params: Unit arithmetic parameters.

    Returns:
        Unit-aware arithmetic result payload.
    """
    precision = validate_precision(params.precision)
    context = decimal_context(precision)

    left_unit = UNITS[params.left.unit]
    right_unit = UNITS[params.right.unit]

    with localcontext(context):
        left_value = Decimal(params.left.value) * left_unit.to_base
        right_value = Decimal(params.right.value) * right_unit.to_base

        if params.operator in ("add", "sub"):
            if left_unit.dims != right_unit.dims:
                raise ValueError("incompatible units for add/sub")
            result_base = left_value + right_value if params.operator == "add" else left_value - right_value
            output_unit = params.result_unit or params.left.unit
            out_def = UNITS[output_unit]
            if out_def.dims != left_unit.dims:
                raise ValueError("result unit incompatible")
            result = result_base / out_def.to_base
            result_unit = output_unit
        elif params.operator == "mul":
            result_base = left_value * right_value
            dims = add_dims(left_unit.dims, right_unit.dims)
            if params.result_unit:
                out_def = UNITS[params.result_unit]
                if out_def.dims != dims:
                    raise ValueError("result unit incompatible")
                result = result_base / out_def.to_base
                result_unit = params.result_unit
            else:
                result = result_base
                result_unit = format_unit_dims(dims)
        elif params.operator == "div":
            result_base = left_value / right_value
            dims = sub_dims(left_unit.dims, right_unit.dims)
            if params.result_unit:
                out_def = UNITS[params.result_unit]
                if out_def.dims != dims:
                    raise ValueError("result unit incompatible")
                result = result_base / out_def.to_base
                result_unit = params.result_unit
            else:
                result = result_base
                result_unit = format_unit_dims(dims)
        else:
            raise ValueError("unsupported unit operator")

    result_text = enforce_output_size(format_decimal(result))
    return ComputeResponse(operation="unit", result=result_text, unit=result_unit)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Return structured error payloads without leaking internals."""
    return JSONResponse(status_code=exc.status_code, content=exc.detail)
