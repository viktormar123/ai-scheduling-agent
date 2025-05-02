# Scheduling Agent — Code Documentation

This documentation provides an overview of the code and file structure for the `scheduling_agent` repository.  
The focus is on explaining how the Python modules interact, how the agent works internally, and how the project is organized.

The Scheduling Agent allows users to interactively describe their company and employee information, build a JSON schema, and generate employee work schedules using constraint programming and AI-assisted interactions.

---

## Repository Structure

scheduling_agent/
│
├── agent.py         # SchedulingAgent class (conversation + schema handling)
├── tools.py         # Scheduling functions (basic, optimized, partial schedules)
│
├── data/
│   ├── current_schema.json    # Last used company schema (generated at runtime)
│   ├── examples/              # Examples of text descriptions to give the agent
│
├── run.py              # Entry point script to start the agent
├── requirements.txt    # Project dependencies
├── documentation.md    # This documentation file
│
└── (additional folders planned for outputs, configs, etc.)

---

## File Descriptions

### 1. `run.py`

The main executable script.  
It initializes the SchedulingAgent and handles the following:

- Checks if a saved schema (`data/current_schema.json`) exists.
- If yes, loads the existing company schema.
- If no, asks the user structured questions to build a new schema.
- Starts the main user interaction loop by calling `agent.run()`.

**Key functions:**
- `load_existing_schema(filepath)`: Load saved schema.
- `save_schema(schema, filepath)`: Save new schema.
- Running `agent.run()` launches either schema editing or schedule building modes.

---

### 2. `agent.py`

This file defines the core **`SchedulingAgent`** class.  
It handles:

- User conversation and input parsing.
- Communication with the language model (OpenAI Chat API).
- Schema creation and updating.
- Calling scheduling functions from `tools.py` based on user commands.

**Main attributes:**
- `message_history`: Chat history.
- `schema_data`: Current company schema (dictionary format).
- `schedule_output`: Last schedule generated.
- `mode`: Current mode ("schema_building" or "schedule_building").

**Important methods:**
- `collect_initial_inputs()`: Structured initial questions to create a schema.
- `initialize_from_text(user_text)`: Turn user input into a structured JSON schema via AI.
- `initialize_with_schema(schema_data)`: Load an existing schema directly.
- `run()`: Main interaction loop (process user commands).
- `_chat_completion(messages)`: Communicates with the language model API.
- `_run_tool(tool_name, tool_args)`: Calls registered scheduling functions dynamically.

---

### 3. `tools.py`

This file contains the scheduling logic:  
multiple strategies for building schedules from a schema.

**Key scheduling functions:**
- `build_basic_schedule(schema)`: A simple greedy scheduling algorithm.
- `build_optimized_schedule_cp(schema, relax_flags...)`: Full constraint programming optimization using Google OR-Tools CP-SAT solver.
- `build_partial_schedule_high_percentage(schema, threshold)`: Generate schedules focusing on high-percentage workers.
- `build_partial_schedule_experience_threshold(schema, threshold)`: Focus scheduling on employees with more experience.

**Other contents:**
- `AVAILABLE_TOOLS`: A registry that describes which tools are available for the agent to call.
- `tool_functions`: A dictionary mapping tool names to function references.

---

## How the Files Work Together

The flow between the main files is as follows:

1. `run.py` starts the system and loads or builds a company schema.
2. `agent.py` manages the conversation:
   - Collects initial inputs
   - Builds or edits the schema
   - Decides which scheduling tool to use
   - Validates the schema internally
3. `tools.py` provides the backend functions:
   - Actual schedule building based on different methods

All data is organized around the **JSON schema** concept, making it easier to save, reload, and modify company configurations.

---

## JSON Schema Definition

The system builds a structured schema in JSON format to represent each company’s scheduling problem. The schema includes:

### Company Information
- `company_name`: string
- `location`: string (optional)
- `opening_hours`: object mapping weekdays to open/close times

### Shift Structure
- A list of shifts (name, start, end, duration, optional notes)

### Employees
- Name, employment type, percentage
- Roles, experience, availability, special flags (e.g., student)
- Contact (optional)

### Constraints
- Per-shift (e.g., “at least 1 cashier per shift”)
- Per-schedule (e.g., “balance weekends”)
- Employee relations (e.g., prefer/avoid same shifts)

### Scheduling Period
- `weekly`, `biweekly`, or `monthly`

---

## Future Enhancements

Some ideas are noted inside the code but not yet implemented, including:

- Exporting schedules to Excel or Google Calendar.
- Optimizing schedules further for fairness, minimum rest periods, etc.
- More advanced schema editing and error handling.
- User interfaces beyond the command-line (e.g., web-based frontends).

---

## Requirements

- Python 3.10+
- `openai` library
- `ortools` library
- (optionally) `pydantic` for future schema enforcement

Install dependencies with:

`pip install -r requirements.txt`

---

# 📢 Notes
- This documentation focuses on code structure and interactions.
- Broader project motivation, limitations, and future goals are discussed separately in the final project report.

---