"""
LEGACY MODULE – kept for reference only
--------------------------------------
This file contains the first‑generation, highly structured scheduling agent
prototype.  It has been superseded by `agent2.py`, which provides a more
flexible, conversational workflow.  The code in this module is **no longer
executed** by default; feel free to browse it for historical context or
implementation ideas, but use `agent2.py` for all practical purposes.
"""
# agent.py
from tools import AVAILABLE_TOOLS, tool_functions, format_schedule_by_shift
import openai
import json
import os
import re

# === CONFIGURATION ===
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # Set this before running
MODEL_NAME = "gpt-4o"
TEMPERATURE = 0.2
JSON_OBJECT = {"type": "json_object"}   # module‑level constant

EXAMPLE_SCHEMA = {
    "company_name": "Example Pizza",
    "opening_hours": {
        day: {"open": "11:00", "close": "23:00"}
        for day in ["Monday","Tuesday","Wednesday",
                    "Thursday","Friday","Saturday","Sunday"]
    },
    "shift_structure": [
        {"name": "Day", "hours": 8},
        {"name": "Night", "hours": 6}
    ],
    "employees": [
        {"name": "Alice", "employment_type": "full-time",
         "work_percentage": 100, "roles_primary": ["Baker"],
         "availability": {"unavailable_days": [], "unavailable_times": []}}
    ],
    "days": ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
}

BASE_SCHEMA_MSG = f"""
You are a scheduling assistant.

**Output format**
Return ONE valid JSON object – no markdown fences, no commentary.

**Schema prototype**
{json.dumps(EXAMPLE_SCHEMA, indent=2)}

**Mandatory keys**
- company_name
- opening_hours  (dict of 7 days → {{open, close}})
- shift_structure (list of {{name, hours}})
- employees      (list)
- days           (list of weekdays)
"""

def build_schema_prompt(task: str) -> str:
    """
    task = "init"  → generate a brand‑new schema from user prose
    task = "edit"  → merge user edits into the provided schema
    """
    if task == "init":
        extra = "\nTask: Using ONLY the user’s natural‑language description, " \
                "produce a complete schema that matches the prototype above."
    elif task == "edit":
        extra = "\nTask: You are given the current schema and a user request. " \
                "Update only the fields the user mentions; keep everything " \
                "else unchanged, then output the FULL updated object."
    else:
        raise ValueError("task must be 'init' or 'edit'")
    return BASE_SCHEMA_MSG + extra


# === SCHEMA VALIDATION ===
def validate_schema(schema_data):
    warnings = []
    if "company_name" not in schema_data or not schema_data.get("company_name"):
        warnings.append("Missing company_name.")
    if "opening_hours" not in schema_data or not schema_data.get("opening_hours"):
        warnings.append("Missing opening_hours.")
    if "employees" not in schema_data or not schema_data["employees"]:
        warnings.append("Missing or empty employees list.")
    if "shift_structure" not in schema_data or not schema_data["shift_structure"]:
        #print("ℹ️ No shift structure provided. Assuming default: one 8-hour shift per day.")
        #schema_data["shift_structure"] = [{"name": "Default", "hours": 8}]
        warnings.append("Missing shift_structure.")
    return warnings

class SchedulingAgent:
    def __init__(self, model_name=MODEL_NAME, temperature=TEMPERATURE):
        self.model_name = model_name
        self.temperature = temperature
        self.message_history = []
        self.schema_data = None
        self.schedule_output = None
        self.mode = "schema_building"


    def _chat_completion(self, messages, *, system_prompt=None,
                        json_mode: bool = False):
        client = openai.OpenAI(api_key=OPENAI_API_KEY)

        base = {"model": self.model_name,
                "temperature": self.temperature,
                "messages": [{"role": "system", "content": system_prompt}]
                        + messages if system_prompt else messages}

        if json_mode:                                     # ← schema work
            base["response_format"] = JSON_OBJECT
            #base["tool_choice"] = "none"                  # disable tool calls
        else:                                             # ← normal chat
            base["tools"] = AVAILABLE_TOOLS
            base["tool_choice"] = "auto"

        return client.chat.completions.create(**base)

    def _run_tool(self, tool_name, tool_args):
        if tool_name not in tool_functions:
            return {"error": f"Tool {tool_name} not found."}
        tool = tool_functions[tool_name]
        return tool(self.schema_data, **tool_args)
    def _validate_schema(self):
        warnings = validate_schema(self.schema_data)
        if warnings:
            print("\n[Schema Validation Warnings]:")
            for warning in warnings:
                print(f"- {warning}")
            print()

    def _save_schema(self):
        os.makedirs("data", exist_ok=True)
        with open("data/current_schema.json", "w") as f:
            json.dump(self.schema_data, f, indent=2)

    def collect_initial_inputs(self) -> str:
        parts = []
        company_name = input("📛 What is your company name?: ")
        parts.append(f"Company name: {company_name}")
        company = input("📄 Please describe your company and its location: ")
        parts.append(f"Company description: {company}")
        period = input("\n🗓️ What is your planning period? (weekly, biweekly, monthly): ")
        parts.append(f"Planning period: {period}")
        shifts = input("\n🕑 Please describe your shift structure (e.g., shifts per day, times, weekend differences): ")
        parts.append(f"Shift structure: {shifts}")
        weekend = input("\n📆 Are weekends treated differently in terms of hours or shifts? If so, how?: ")
        parts.append(f"Weekend policy: {weekend}")
        print("\n👥 Let's add your employees one by one.")
        print("Type 'x' when you're done adding employees.\n")
        employee_lines = []
        while True:
            entry = input("Add employee (e.g., Anna, full-time, 100%, Baker): ").strip()
            if entry.lower() == "x":
                break
            employee_lines.append(entry)
        employees = "\n".join(employee_lines)
        parts.append(f"Employees:\n{employees}")
        seniority = input("\n👔 Do any shifts require a senior employee or a minimum number of years of experience?: ")
        parts.append(f"Seniority constraint: {seniority}")
        fairness = input("\n⚖️ Do you want the schedule to be fair (i.e., balanced shift count per employee)?: ")
        parts.append(f"Fairness preference: {fairness}")
        preferences = input("\n❤️ Do any employees have preferences (e.g., mornings only, weekend preference)?: ")
        parts.append(f"Employee preferences: {preferences}")
        availability = input("\n🕒 Do any employees have specific availability (e.g., unavailable days/times)?: ")
        parts.append(f"Employee availability: {availability}")
        constraints = input("\n🚫 Do you have any constraints (e.g., max hours per week, max shifts per day)?: ")
        parts.append(f"Constraints: {constraints}")
        conditions = input("\n📋 Please describe any additional special conditions (e.g., students, pairs, specific restrictions): ")
        parts.append(f"Special conditions: {conditions}")
        return "\n".join(parts)

    def initialize_from_text(self, user_text: str):
        response = self._chat_completion(
            messages=[{"role": "user", "content": user_text}],
            system_prompt=build_schema_prompt("init"),
            json_mode=True #"json"
        )
        content = response.choices[0].message.content
        print(f"\n[Extracted schema]:\n{content}\n")
        try:
            self.schema_data = json.loads(content)
            self._validate_schema()
        except json.JSONDecodeError:
            print("[Error]: Failed to parse schema.")

    def initialize_with_schema(self, schema_data: dict):
        self.schema_data = schema_data
        self.mode = "schema_building"

    def run(self):
        while True:
            user_input = input("\nUser: ").strip().lower()
            if user_input == "help":
                print("\nAvailable commands:")
                print("  - create basic")
                print("  - create optimized")
                print("  - create partial")
                print("  - edit")
                print("  - exit")
                print("  - reset")
                print("  - validate")
                print("  - schema\n")
                
                continue
            elif user_input.startswith("create"):
                warnings = validate_schema(self.schema_data)
                if warnings:
                    print("⚠️ Cannot create schedule. Please fix the following issues in your schema:")
                    for w in warnings:
                        print(" -", w)
                    print("Tip: type 'edit' to re-enter schema editing mode.\n")
                    continue
                self.mode = "schedule_building"
                _, schedule_type = user_input.split(maxsplit=1)
                if schedule_type == "basic":
                    result = tool_functions["build_basic_schedule"](self.schema_data)
                elif schedule_type == "partial":
                    threshold = int(input("Enter work percentage threshold (e.g., 50): "))
                    result = tool_functions["build_partial_schedule_high_percentage"](self.schema_data, threshold=threshold)
                elif schedule_type == "optimized":
                    result = tool_functions["build_optimized_schedule_cp"](self.schema_data)
                else:
                    print("Unknown schedule type.")
                    continue
                if "error" in result:
                    print("❌ Scheduling failed:", result["error"])
                else:
                    print("✅ Schedule created:\n")
                    print(format_schedule_by_shift(result))
                continue
            elif user_input == "exit":
                print("Exiting Scheduling Agent. Goodbye!")
                break
            elif user_input == "reset":
                print("🗑️ Schema reset requested. Exiting program.")
                os.remove("data/current_schema.json")
                exit()
                
            elif user_input == "validate":
                warnings = validate_schema(self.schema_data)
                if warnings:
                    print("\nSchema issues:")
                    for w in warnings:
                        print(" •", w)
                else:
                    print("\n✅ Schema looks good!")
                continue

            elif user_input == "schema":
                print("\n📄 Current schema:\n")
                print(json.dumps(self.schema_data, indent=2))
                continue
                
            elif user_input == "edit":
                self.mode = "schema_building"
                print("Switched back to schema editing mode.")
                schema_edit = input("\nDescribe what to change in your schema: ")
                update_prompt = "You are an assistant. Given a JSON schema and a user description of edits, return the full updated schema as JSON ONLY. Return only a single valid JSON object, no markdown, no comments."
                messages = [
                    #{"role": "system", "content": update_prompt},
                    {"role": "user", "content": f"Current schema:\n{json.dumps(self.schema_data, indent=2)}"},
                    {"role": "user", "content": f"User request:\n{schema_edit}"}
                ]
                response = self._chat_completion(messages=messages, system_prompt=build_schema_prompt("edit"), json_mode=True) #"json_object")
                try:

                    new_schema = json.loads(response.choices[0].message.content)
                    self.schema_data = new_schema
                    print("🔄 Schema updated.")
                    self._validate_schema()
                    self._save_schema()
                except json.JSONDecodeError:
                    print("[Error]: Failed to parse updated schema.")
                continue
            
            else:
                # ➊ add the user message to history
                self.message_history.append({"role": "user", "content": user_input})

                # ➋ get the assistant’s reply (may contain tool_calls)
                response = self._chat_completion(self.message_history)
                message = response.choices[0].message

                # ➌ if the model wants to call a tool
                if getattr(message, "tool_calls", None):
                    tool_call   = message.tool_calls[0]
                    tool_name   = tool_call.function.name
                    tool_args   = json.loads(tool_call.function.arguments)
                    print(f"\n[Agent decided to call function: {tool_name}]")

                    # keep the assistant msg that requested the tool
                    self.message_history.append(message)

                    # run the tool
                    tool_result = self._run_tool(tool_name, tool_args)

                    # store the tool result
                    self.message_history.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": json.dumps(tool_result)
                    })

                    # ➍ let the model turn the result into a user‑facing reply
                    follow_up = self._chat_completion(self.message_history[-3:])
                    assistant_reply = follow_up.choices[0].message
                    self.message_history.append(assistant_reply)
                    print("\n" + assistant_reply.content + "\n")

                    # pretty‑print schedules
                    if tool_name.startswith("build_"):
                        if "error" in tool_result:
                            print("❌ Scheduling failed:", tool_result["error"])
                        elif isinstance(tool_result, dict) and all(
                                isinstance(v, list) for v in tool_result.values()):  # looks like a schedule
                            print("✅ Schedule created:\n")
                            print(format_schedule_by_shift(tool_result))
                        else:  # fallback for message / status dicts
                            print("✅", tool_result.get("message", "Done."))
                            if "selected_employees" in tool_result:
                                print(json.dumps(tool_result["selected_employees"], indent=2))
                # ➎ normal chat – just print the content
                elif message.content:
                    self.message_history.append(message)
                    print("\n[Agent]:\n" + message.content + "\n")

if __name__ == "__main__":
    print("🔧 Testing SchedulingAgent...")
    test_schema = {
        "company_name": "Mario’s Pizza",
        "opening_hours": {day: {"open": "11:00", "close": "23:00"} for day in ["Monday", "Tuesday"]},
        "shift_structure": [
            {"name": "Day", "hours": 7},
            {"name": "Night", "hours": 6}
        ],
        "employees": [
            {"name": "Anna", "employment_type": "full-time", "work_percentage": 100, "roles_primary": ["Baker"], "availability": {"unavailable_days": [], "unavailable_times": []}},
            {"name": "James", "employment_type": "part-time", "work_percentage": 50, "roles_primary": ["Driver"], "availability": {"unavailable_days": [], "unavailable_times": []}},
            {"name": "Sophia", "employment_type": "part-time", "work_percentage": 75, "roles_primary": ["Cashier"], "availability": {"unavailable_days": [], "unavailable_times": []}}
        ],
        "days": ["Monday", "Tuesday"]
    }
    agent = SchedulingAgent()
    agent.initialize_with_schema(test_schema)
    print("Running `create optimized` command internally...\n")
    result = tool_functions["build_optimized_schedule_cp"](agent.schema_data)
    if "error" in result:
        print("❌ Optimized schedule failed:", result["error"])
    else:
        print("✅ Optimized schedule:\n")
        print(format_schedule_by_shift(result))

