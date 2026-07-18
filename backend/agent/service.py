import json
import os
import ssl
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .prompts import ACCOUNTING_AGENT_SYSTEM_PROMPT
from .schemas import (
    AgentChatRequest,
    AgentChatResponse,
    AgentHighlight,
    AgentSource,
    AgentToolCall,
)
from .tools import (
    BASE_DIR,
    DEFAULT_DB_PATH,
    get_income_statement,
    get_monthly_income_summary,
    get_period_summary,
    get_trial_balance,
)


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_OPENAI_MODEL = "gpt-5.5"
MAX_TOOL_ROUNDS = 4


def run_agent_chat(
    request: AgentChatRequest,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> AgentChatResponse:
    load_local_env()
    period_id = request.periodId or get_latest_period_id(db_path)
    api_key = os.getenv("OPENAI_API_KEY", "").strip()

    if not api_key:
        return run_local_agent_chat(request, period_id, db_path)

    return run_openai_agent_chat(request, period_id, api_key, db_path)


def run_openai_agent_chat(
    request: AgentChatRequest,
    period_id: int,
    api_key: str,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> AgentChatResponse:
    model = os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL).strip()
    input_items: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": build_system_prompt(),
        },
        {
            "role": "user",
            "content": (
                f"Selected accounting period id: {period_id}\n"
                f"User question: {request.message}"
            ),
        },
    ]
    executed_tool_calls: list[AgentToolCall] = []

    for _ in range(MAX_TOOL_ROUNDS):
        response = create_openai_response(
            api_key=api_key,
            model=model,
            input_items=input_items,
            tools=get_openai_tool_definitions(),
        )
        function_calls = get_function_calls(response)

        if not function_calls:
            return build_agent_response_from_model(response, executed_tool_calls)

        input_items.extend(response.get("output", []))

        for function_call in function_calls:
            tool_name = function_call["name"]
            tool_result = execute_read_only_tool(tool_name, period_id, db_path)
            result_summary = summarize_tool_result(tool_name, tool_result)
            executed_tool_calls.append(
                AgentToolCall(
                    name=tool_name,
                    arguments={"period_id": period_id},
                    resultSummary=result_summary,
                )
            )
            input_items.append(
                {
                    "type": "function_call_output",
                    "call_id": function_call["call_id"],
                    "output": json.dumps(tool_result, separators=(",", ":")),
                }
            )

    return AgentChatResponse(
        answer=(
            "I could not finish the tool-based analysis in the allowed number "
            "of tool rounds. Try asking a narrower question."
        ),
        toolCalls=executed_tool_calls,
        sources=build_sources_from_tool_calls(executed_tool_calls),
    )


def run_local_agent_chat(
    request: AgentChatRequest,
    period_id: int,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> AgentChatResponse:
    period_summary = get_period_summary(period_id, db_path)
    trial_balance = get_trial_balance(period_id, db_path)
    income_statement = get_income_statement(period_id, db_path)

    period = period_summary["period"]
    journal = period_summary["journal"]
    imports = period_summary["imports"]
    is_balanced = trial_balance["is_balanced"]
    debit_total = trial_balance["total_debit_balances"]
    credit_total = trial_balance["total_credit_balances"]
    net_income = income_statement["totals"]["net_income"]

    answer = (
        f"For {period['label']}, the trial balance is "
        f"{'balanced' if is_balanced else 'not balanced'} with "
        f"${debit_total:,.2f} in debit balances and ${credit_total:,.2f} "
        f"in credit balances. Net income is ${net_income:,.2f}. "
        f"This period has {imports['importCount']} import"
        f"{'' if imports['importCount'] == 1 else 's'}, "
        f"{journal['proposedEntries']} proposed entries, "
        f"{journal['pendingEntries']} pending entries, and "
        f"{journal['flaggedEntries']} flagged entries."
    )

    return AgentChatResponse(
        answer=answer,
        toolCalls=[
            AgentToolCall(
                name="get_period_summary",
                arguments={"period_id": period_id},
                resultSummary=(
                    f"Loaded {period['label']} with "
                    f"{journal['proposedEntries']} proposed entries."
                ),
            ),
            AgentToolCall(
                name="get_trial_balance",
                arguments={"period_id": period_id},
                resultSummary=(
                    "Trial balance is balanced."
                    if is_balanced
                    else "Trial balance is not balanced."
                ),
            ),
            AgentToolCall(
                name="get_income_statement",
                arguments={"period_id": period_id},
                resultSummary=f"Net income is ${net_income:,.2f}.",
            ),
        ],
        sources=[
            AgentSource(label="Period summary", tool="get_period_summary"),
            AgentSource(label="Trial balance", tool="get_trial_balance"),
            AgentSource(label="Income statement", tool="get_income_statement"),
        ],
        highlights=[
            AgentHighlight(
                label="Trial balance",
                value="Balanced" if is_balanced else "Out of balance",
            ),
            AgentHighlight(
                label="Debit balances",
                value=f"${debit_total:,.2f}",
            ),
            AgentHighlight(
                label="Credit balances",
                value=f"${credit_total:,.2f}",
            ),
            AgentHighlight(
                label="Net income",
                value=f"${net_income:,.2f}",
            ),
        ],
    )


def load_local_env() -> None:
    env_paths = [
        Path.cwd() / ".env",
        BASE_DIR / ".env",
        Path(__file__).resolve().parent / ".env",
    ]

    for env_path in env_paths:
        if not env_path.exists():
            continue

        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()

            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue

            key, value = stripped.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            if key:
                os.environ.setdefault(key, value)


def build_system_prompt() -> str:
    return (
        ACCOUNTING_AGENT_SYSTEM_PROMPT
        + """

Available tools are read-only and always operate on the selected accounting
period supplied by the backend. Do not ask the user for a period id unless they
are trying to switch periods.

Final response format:
Return a JSON object with this shape:
{
  "answer": "plain English answer",
  "sources": [{"label": "Trial balance", "tool": "get_trial_balance"}],
  "highlights": [{"label": "Net income", "value": "$123.45"}]
}
Do not wrap the JSON in Markdown.
"""
    )


def get_openai_tool_definitions() -> list[dict[str, Any]]:
    empty_parameters = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }

    return [
        {
            "type": "function",
            "name": "get_period_summary",
            "description": (
                "Get read-only metadata and summary counts for the selected "
                "accounting period."
            ),
            "parameters": empty_parameters,
        },
        {
            "type": "function",
            "name": "get_trial_balance",
            "description": (
                "Get the read-only trial balance for the selected accounting "
                "period, including account balances and whether it balances."
            ),
            "parameters": empty_parameters,
        },
        {
            "type": "function",
            "name": "get_income_statement",
            "description": (
                "Get the read-only income statement for the selected accounting "
                "period, including revenue, expenses, and net income."
            ),
            "parameters": empty_parameters,
        },
        {
            "type": "function",
            "name": "get_monthly_income_summary",
            "description": (
                "Get read-only monthly income summaries across available "
                "accounting periods, including revenue, expenses, and net income. "
                "Use this for multi-month net income or trend questions."
            ),
            "parameters": empty_parameters,
        },
    ]


def create_openai_response(
    api_key: str,
    model: str,
    input_items: list[dict[str, Any]],
    tools: list[dict[str, Any]],
) -> dict[str, Any]:
    payload = {
        "model": model,
        "input": input_items,
        "tools": tools,
        "tool_choice": "auto",
        "store": False,
    }
    request = urllib.request.Request(
        OPENAI_RESPONSES_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=45,
            context=get_ssl_context(),
        ) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI request failed: {detail}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"OpenAI request failed: {error.reason}") from error
    except TimeoutError as error:
        raise RuntimeError("OpenAI request timed out.") from error


def get_ssl_context() -> ssl.SSLContext:
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()

    return ssl.create_default_context(cafile=certifi.where())


def get_function_calls(response: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        output_item
        for output_item in response.get("output", [])
        if output_item.get("type") == "function_call"
    ]


def execute_read_only_tool(
    tool_name: str,
    period_id: int,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    if tool_name == "get_period_summary":
        return get_period_summary(period_id, db_path)

    if tool_name == "get_trial_balance":
        return get_trial_balance(period_id, db_path)

    if tool_name == "get_income_statement":
        return get_income_statement(period_id, db_path)

    if tool_name == "get_monthly_income_summary":
        return get_monthly_income_summary(db_path)

    raise ValueError(f"Unknown or unavailable read-only tool: {tool_name}")


def summarize_tool_result(tool_name: str, result: dict[str, Any]) -> str:
    if tool_name == "get_period_summary":
        period = result["period"]
        journal = result["journal"]
        return (
            f"Loaded {period['label']} with "
            f"{journal['proposedEntries']} proposed entries."
        )

    if tool_name == "get_trial_balance":
        return (
            "Trial balance is balanced."
            if result["is_balanced"]
            else "Trial balance is not balanced."
        )

    if tool_name == "get_income_statement":
        totals = result["totals"]
        return f"Net income is ${totals['net_income']:,.2f}."

    if tool_name == "get_monthly_income_summary":
        period_count = len(result["periods"])
        net_income = result["totals"]["netIncome"]
        return (
            f"Loaded {period_count} monthly income summaries with "
            f"${net_income:,.2f} total net income."
        )

    return "Tool result returned."


def build_agent_response_from_model(
    response: dict[str, Any],
    executed_tool_calls: list[AgentToolCall],
) -> AgentChatResponse:
    response_text = extract_response_text(response)
    parsed = parse_model_json_response(response_text)

    return AgentChatResponse(
        answer=parsed.get("answer") or response_text,
        toolCalls=executed_tool_calls,
        sources=[
            AgentSource(**source)
            for source in parsed.get("sources", [])
            if "label" in source and "tool" in source
        ]
        or build_sources_from_tool_calls(executed_tool_calls),
        highlights=[
            AgentHighlight(**highlight)
            for highlight in parsed.get("highlights", [])
            if "label" in highlight and "value" in highlight
        ],
    )


def extract_response_text(response: dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str):
        return response["output_text"]

    chunks: list[str] = []

    for output_item in response.get("output", []):
        if output_item.get("type") != "message":
            continue

        for content_item in output_item.get("content", []):
            text = content_item.get("text")

            if isinstance(text, str):
                chunks.append(text)

    return "\n".join(chunks).strip()


def parse_model_json_response(response_text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(response_text)
    except json.JSONDecodeError:
        return {}

    return parsed if isinstance(parsed, dict) else {}


def build_sources_from_tool_calls(
    tool_calls: list[AgentToolCall],
) -> list[AgentSource]:
    source_labels = {
        "get_period_summary": "Period summary",
        "get_trial_balance": "Trial balance",
        "get_income_statement": "Income statement",
        "get_monthly_income_summary": "Monthly income summary",
    }

    return [
        AgentSource(
            label=source_labels.get(tool_call.name, tool_call.name),
            tool=tool_call.name,
        )
        for tool_call in tool_calls
    ]


def get_latest_period_id(db_path: str | Path = DEFAULT_DB_PATH) -> int:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT id
            FROM accounting_periods
            ORDER BY period_start DESC, id DESC
            LIMIT 1
            """
        ).fetchone()

    if row is None:
        raise ValueError("No accounting period is available for the agent.")

    return int(row[0])
