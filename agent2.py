"""
agent2.py
=========
Conversational, tool‑aware scheduling assistant (“ScheduleGPT”).

* Collects company/shift/employee data via natural‑language chat.
* Builds a JSON schema in‑memory.
* Invokes backend scheduling tools (from *tools.py*) once enough
  information is known.
* Falls back gracefully and guides the user when constraints are
  infeasible.

Run this script directly and start typing — it behaves like a small
REPL.  See the README for example sessions.
"""
import re
import textwrap
import json
import openai
from openai import APITimeoutError, APIConnectionError
import time
from tools import AVAILABLE_TOOLS, tool_functions, format_schedule_by_shift

# ---------------------------------------------------------------------
# Configuration toggles
# ---------------------------------------------------------------------
DEBUG = True  # global debug switch

SYSTEM_PROMPT = textwrap.dedent("""
You are **ScheduleGPT** – an expert scheduling assistant for small businesses.

-------------------------------------------------
🎯 PURPOSE
-------------------------------------------------
1. Collect enough structured data to build an **employee‑scheduling JSON schema**.
2. When the schema is ready, call the backend tool **build_schedule**.
3. Explain results in plain language (or show follow‑up questions) – never expose internal reasoning.

-------------------------------------------------
📋 REQUIRED SCHEMA FIELDS
-------------------------------------------------
* company_name (str)
* opening_hours (dict of 7 days → {open, close} in HH:MM 24‑h)
* shift_structure (list of objects)  
  └ each shift needs:  
    • name (str)  
    • hours (int)  
    • min_staff (int, ≥1)  
    • required_roles (dict role → min_count; may be empty)
* employees (list of objects)  
  • name (str)  
  • roles_primary (list[str]) – e.g., ["Baker"]  
  • employment_type ("full‑time"|"part‑time")  
  • work_percentage (int, default 100)  
  • senior (bool, default false) *or* experience_years (int)  
  • availability (object, optional)  
    · unavailable_days (list[str])  
    · unavailable_times (list[str] shift names)
* days (list of weekdays the schedule should cover)

If anything is missing or unclear, **ask a follow‑up question**.  
Use short, specific questions – one topic at a time.

-------------------------------------------------
🛠️  TOOL USAGE
-------------------------------------------------
* When >80 % of the mandatory data is known, call **build_schedule**:  
  • method="cp" (unless user insists on "greedy")  
  • fairness=true, fairness_weight=3  
  • rest_constraint=true  
  • seniority=true  
  (Adjust only if the user overrides.)
* If **method="cp"** fails **three times in a row** with
  “No feasible schedule…” you may retry **once** with
  `method="greedy"` as a fallback. Do **not** fallback after the
  first failure.

-------------------------------------------------
💾  OUTPUT RULES
-------------------------------------------------
1. When you output or update the full schema, reply with **only** the JSON wrapped in a ```json … ``` fence – absolutely no commentary outside the fence.
2. For normal conversation or questions, reply as chat text.
3. NEVER invent tool names; use only tools provided.

-------------------------------------------------
💡  FEW‑SHOT EXAMPLES
-------------------------------------------------
USER: We’re “Mario’s Pizza”, open 11‑23 daily. One 8‑h shift, 2 bakers + 1 cashier per shift.  
ASSISTANT:
```json
{
  "company_name": "Mario's Pizza",
  "opening_hours": {
    "Monday": {"open":"11:00","close":"23:00"},
    "Tuesday":{"open":"11:00","close":"23:00"},
    "Wednesday":{"open":"11:00","close":"23:00"},
    "Thursday":{"open":"11:00","close":"23:00"},
    "Friday":{"open":"11:00","close":"23:00"},
    "Saturday":{"open":"11:00","close":"23:00"},
    "Sunday":{"open":"11:00","close":"23:00"}
  },
  "shift_structure":[
    {"name":"Day","hours":8,"min_staff":3,"required_roles":{"Baker":2,"Cashier":1}}
  ],
  "employees": [],
  "days":["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
}
```

USER: Add Anna (full‑time baker) and Bob (60 % cashier).  
ASSISTANT:
```json
{
  "...": "DUMMY – full updated schema here"
}
```

USER: Great, make a schedule.  
ASSISTANT: *calls build_schedule with method="cp" fairness=true*  
-------------------------------------------------
""")

class ConversationalScheduler:
    """
    Stateful chat wrapper that manages:
      • message history with the LLM
      • an in‑memory scheduling *schema* (dict)
      • a last generated *schedule*  (dict)

    The class offers a single public method, `handle_user()`, which
    consumes a raw user string, decides whether to ask the LLM, call a
    backend tool, or print debugging information, and then prints the
    assistant’s textual reply (or pretty‑formatted schedule).
    """
    SHOW_RE   = re.compile(r"^\s*(show|print)\s+(schema|schedule)\s*$", re.I)
    RESET_RE  = re.compile(r"^\s*(reset|delete)\s+schema\s*$", re.I)
    SCHED_RE = re.compile(
        r"\b(build(?:ing)?|make|create|generate)\s+(an?\s+)?(schedule|timetable)\b",
        re.I,
    )

    def __init__(self, model_name: str = "gpt-4o", temperature: float = 0.2):
        self.model_name = model_name
        self.temperature = temperature
        self.schema: dict | None = None
        self.schedule: dict | None = None
        self.chat = [{"role": "system", "content": SYSTEM_PROMPT}]

    # ------- LLM helper -------------------------------------------------
    def _llm(self, *, json_only: bool = False, tools_ok: bool = True):
        client = openai.OpenAI()
        # Base payload for the Chat Completions request.  We add tool /
        # format directives later depending on the call site.
        params = {
            "model": self.model_name,
            "temperature": self.temperature,
            "messages": self.chat,
        }
        if DEBUG:
            suffix = "enabled" if tools_ok else "disabled"
            fmt = "json‑only" if json_only else suffix
            print(f"⚙️  [DEBUG] calling LLM ({fmt})")

        # decide tool / format options
        if json_only:
            params["response_format"] = {"type": "json_object"}
        elif tools_ok:
            params["tools"] = AVAILABLE_TOOLS
            params["tool_choice"] = "auto"        # enable calling tools

        # OpenAI network calls occasionally time‑out.  Retry (with a back‑off)
        # up to three times so the CLI does not crash on a transient error.
        for attempt in range(3):          # at most 3 tries
            try:
                try:
                    # newer openai‑python accepts request_timeout
                    return client.chat.completions.create(request_timeout=60, **params)
                except TypeError:
                    # fallback for older sdk versions
                    return client.chat.completions.create(**params)
            except (APITimeoutError, APIConnectionError) as exc:
                if attempt == 2:
                    raise
                if DEBUG:
                    print(f"⚠️  [DEBUG] LLM timeout – retry {attempt+1}/3...")
                time.sleep(2 * (attempt + 1))

    # ------- single‑turn handler ---------------------------------------
    def handle_user(self, user_msg: str):
        if DEBUG:
            print(f"⚙️  [DEBUG] incoming user_msg = {repr(user_msg)}")
        # -----------------------------------------------------------------
        # Fast‑path: recognise a few *explicit* textual commands that the
        # user can type without involving the LLM (show schema, show
        # schedule, reset schema, or build schedule immediately).
        # -----------------------------------------------------------------
        # ----- explicit user commands (quick actions) -----------------
        if self.SHOW_RE.match(user_msg):
            if "schedule" in self.SHOW_RE.match(user_msg).group(2).lower():
                if self.schedule:
                    print(format_schedule_by_shift(self.schedule))
                else:
                    print("⚠️  No schedule stored yet.")
            else:  # show schema
                if self.schema:
                    print("Current schema:")
                    print(json.dumps(self.schema, indent=2))
                else:
                    print("⚠️  No schema stored yet.")
            return  # skip normal LLM flow

        if self.RESET_RE.match(user_msg):
            self.schema   = None
            self.schedule = None
            print("🗑️  Schema deleted – starting fresh.")
            # fall through to normal processing so assistant asks again

        if ("schedule" in user_msg.lower() or self.SCHED_RE.search(user_msg)) and self.schema:
            # direct call without waiting for LLM
            if DEBUG:
                print("⚙️  [DEBUG] quick‑path build_schedule with schema keys:",
                      list(self.schema.keys()) if self.schema else "None")
            print("🔧 Building schedule with default CP parameters...")
            res = tool_functions["build_schedule"](self.schema, method="cp", fairness=True, fairness_weight=3,
                                                   rest_constraint=True, seniority=True)
            if "error" in res:
                print("❌", res["error"])
            else:
                self.schedule = res
                print(format_schedule_by_shift(res))
            return

        # ➊ add user message
        self.chat.append({"role": "user", "content": user_msg})

        # ➋ let the model respond (enable tool calls only once a schema exists)
        allow_tools = self.schema is not None
        resp = self._llm(tools_ok=allow_tools)
        if resp is None:
            print("⚠️  LLM request failed repeatedly; please try again later.")
            return
        msg = resp.choices[0].message

        # If the assistant reply *requests* a tool invocation we execute it
        # synchronously here, then feed the tool’s JSON result back to the
        # model so it can turn the raw data into a nice explanation.
        # ---------- tool call branch ----------
        if getattr(msg, "tool_calls", None):
            tc = msg.tool_calls[0]
            name = tc.function.name
            args = json.loads(tc.function.arguments or "{}")
            if DEBUG:
                print(f"⚙️  [DEBUG] tool_call → {name}  args = {args}")

            # always keep the assistant message that requested the tool
            self.chat.append(msg)

            # ----- debug: show the exact schema the tool will receive -----
            if name == "build_schedule" and self.schema:
                print("🔧 DEBUG – schema passed to build_schedule:")
                print(json.dumps(self.schema, indent=2))
            # else:
            #     print("⚠️ DEBUG – build_schedule called with empty schema")

            if DEBUG and name == "build_schedule":
                print("⚙️  [DEBUG] schema available to tool?",
                      "YES" if self.schema else "NO")

            # ------------------------------------------------------------------
            # run (or stub) the tool so that every tool_call_id receives *some*
            # tool message – this keeps the Chat Completions protocol happy.
            # ------------------------------------------------------------------
            if name == "build_schedule" and not self.schema:
                result = {"error": "schema_incomplete"}
            elif name in tool_functions and (self.schema is not None or name == "validate_schema"):
                try:
                    result = tool_functions[name](self.schema or {}, **args)
                except Exception as exc:
                    result = {"error": f"internal tool exception: {exc}"}
            else:
                if not self.schema and name == "build_schedule":
                    result = {"error": "schema_incomplete"}
                else:
                    result = {"error": f"tool {name} not found"}

            # record (real or stub) tool response
            self.chat.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": name,
                    "content": json.dumps(result),
                }
            )

            # cache schedules for pretty‑printing
            if name == "build_schedule" and isinstance(result, dict) and all(
                isinstance(v, list) for v in result.values()
            ):
                self.schedule = result

            # ➍ let the model turn the tool output into user‑facing prose
            follow_up = self._llm(tools_ok=False)
            follow_msg = follow_up.choices[0].message
            self.chat.append({"role": "assistant", "content": follow_msg.content})
            print("\n" + follow_msg.content + "\n")

            # (removed pretty-print schedules block)
            return

        # Otherwise the assistant responded with normal chat text (may or
        # may not embed a JSON schema block).  Parse & store any schema,
        # and optionally auto‑invoke scheduling if the user asked for it.
        # ---------- plain text branch ----------
        if msg.content:
            m = re.search(r"```json\s*(\{.*?\})\s*```", msg.content, re.S)
            if m:
                try:
                    self.schema = json.loads(m.group(1))
                    if DEBUG:
                        print("⚙️  [DEBUG] parsed schema OK, keys:", list(self.schema.keys()))
                    print("✅ Schema stored/updated.")
                    # If the last user message contained a scheduling request, run CP once
                    if self.SCHED_RE.search(user_msg):
                        print("🔧 Attempting schedule with default CP parameters...")
                        res = tool_functions["build_schedule"](
                            self.schema,
                            method="cp",
                            fairness=True,
                            fairness_weight=3,
                            rest_constraint=True,
                            seniority=True,
                        )
                        if "error" in res:
                            print("❌", res["error"])
                        else:
                            self.schedule = res
                            print(format_schedule_by_shift(res))
                        return
                except json.JSONDecodeError:
                    print("⚠️  [DEBUG] JSON parse failed, raw content:\n", msg.content)
            else:
                print(msg.content)
            self.chat.append({"role": "assistant", "content": msg.content})


# ---------------------------------------------------------------------
# CLI entry‑point
# ---------------------------------------------------------------------
if __name__ == "__main__":
    print("👋 Hi, I can help build your employee schedule. Tell me about your company!")
    agent = ConversationalScheduler()

    # ------------- improved multiline / paste friendly reader -------------
    import sys, time, select

    def read_user_block() -> str:
        """
        * Enter  → send the block
        * Shift+Enter (typed as a trailing back‑slash) → newline inside block
        * Multi‑line paste: any burst of lines arriving within 0.25 s is
          concatenated automatically.
        """
        # Implementation notes:
        # * A trailing '\' on a line is treated like Shift+Enter in chat
        #   UIs → forces a newline without sending.
        # * For big clipboard pastes we look at *stdin readiness* and
        #   collect lines that arrive within 0.25 s into the same message
        #   so we don't hammer the LLM with 20 tiny requests.
        lines: list[str] = []
        prompt = "> "
        t_last = time.time()

        while True:
            try:
                line = input(prompt if not lines else "... ")
            except EOFError:
                return ""

            # Shift+Enter simulation: line ending with '\' continues
            if line.endswith("\\"):
                lines.append(line[:-1])
                prompt = "... "
                t_last = time.time()
                continue

            lines.append(line)

            # non‑interactive pastes: keep reading as long as stdin has data
            now = time.time()
            if sys.stdin in select.select([sys.stdin], [], [], 0)[0] and (now - t_last) < 0.25:
                t_last = now
                prompt = "... "
                continue
            break

        return "\n".join(lines).strip()

    while True:
        try:
            user_msg = read_user_block()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break
        if not user_msg:
            continue
        agent.handle_user(user_msg)