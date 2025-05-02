# tools.py



from typing import Dict, Any, List

"""Scheduling backend
====================
This module now exposes a *single public tool* for the agent:

    build_schedule(schema, *, method="cp"|"greedy", fairness=True, ...)

* **method="cp" (default)** – OR‑Tools CP‑SAT solver.
  * `fairness=True` adds a soft objective that balances daily head‑count.
  * `fairness=False` asks only for a feasible schedule.
* **method="greedy"** – fast heuristic; ignores role coverage and fairness.

Older helper functions remain for backward compatibility but are *not* exposed
as tools.  Partial‑schedule helpers are minimally tested.
"""

# ------------------
# Core Scheduling Functions
# ------------------

import random
from collections import defaultdict

def build_basic_schedule(schema: dict):
    """
    Simple greedy scheduling:
    - Assign employees to shifts respecting availability.
    - Try to match work percentage.
    - Try to balance load.
    """
    employees = schema["employees"]
    shift_structure = schema["shift_structure"]
    days = schema.get("days", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])

    # Build employee state
    employee_info = {}
    for e in employees:
        name = e["name"]
        target_percentage = e.get("work_percentage", 100)
        special_flags = e.get("special_flags", [])
        unavailable_days = set(e.get("availability", {}).get("unavailable_days", []))
        unavailable_times = set(e.get("availability", {}).get("unavailable_times", []))
        preferred_shifts = set(e.get("availability", {}).get("preferred_shifts", []))

        employee_info[name] = {
            "assigned_shifts": [],
            "work_percentage": target_percentage,
            "unavailable_days": unavailable_days,
            "unavailable_times": unavailable_times,
            "preferred_shifts": preferred_shifts,
            "special_flags": special_flags,
            "assigned_hours": 0
        }

    # Calculate total required hours dynamically
    total_required_hours = 0
    for day in days:
        for shift in shift_structure:
            total_required_hours += shift["hours"]

    # Calculate each employee's target hours
    target_hours = {}
    for name, info in employee_info.items():
        target_hours[name] = (info["work_percentage"] / 100) * total_required_hours

    # Build shifts to assign
    shifts_to_assign = []
    for day in days:
        for shift in shift_structure:
            shifts_to_assign.append((day, shift["name"], shift["hours"]))

    random.shuffle(shifts_to_assign)

    # quick lookup for min_staff per shift name
    min_staff_map = {s["name"]: s.get("min_staff", 1) for s in shift_structure}

    schedule = defaultdict(list)

    for day, shift_name, shift_hours in shifts_to_assign:
        min_staff = min_staff_map[shift_name]

        # filter available workers
        candidates = [
            n for n, info in employee_info.items()
            if day not in info["unavailable_days"]
            and shift_name not in info["unavailable_times"]
            and info["assigned_hours"] < target_hours[n]            # stop when full
        ]

        if not candidates:
            schedule[day].append({"shift": shift_name, "employee": None})
            continue

        # pick the least‑loaded candidates up to min_staff
        for _ in range(min_staff):
            if not candidates:
                schedule[day].append({"shift": shift_name, "employee": None})
                break
            chosen = min(candidates, key=lambda n: employee_info[n]["assigned_hours"])
            schedule[day].append({"shift": shift_name, "employee": chosen})
            employee_info[chosen]["assigned_hours"] += shift_hours
            candidates.remove(chosen)

    return dict(schedule)

from ortools.sat.python import cp_model

# ------------------
# Unified entry‑point
# ------------------

def _filter_employees(schema: dict, wp_threshold: int | None = None, exp_threshold: int | None = None):
    """Return a deep‑copied schema filtered by optional work‑% or experience thresholds."""
    import json  # local to keep original imports unchanged
    employees = schema.get("employees", [])
    if wp_threshold is not None:
        employees = [e for e in employees if e.get("work_percentage", 100) > wp_threshold]
    if exp_threshold is not None:
        employees = [e for e in employees if e.get("experience_years", 0) > exp_threshold]
    new_schema = json.loads(json.dumps(schema))  # deep‑copy safe for OR‑Tools
    new_schema["employees"] = employees
    return new_schema

def build_schedule(schema: dict, *, method: str = "cp", fairness: bool = True,
                   rest_constraint: bool = True, seniority: bool = False,
                   fairness_weight: int = 1,
                   work_percentage_threshold: int | None = None,
                   experience_threshold: int | None = None,
                   relax_work_percentage: bool = False,
                   relax_coverage: bool = False,
                   relax_availability: bool = False):
    """General scheduling wrapper.

    Parameters
    ----------
    method : "cp" | "greedy"
        "cp" → CP‑SAT optimiser (default), "greedy" → fast heuristic.
    fairness : bool, default True
        Only applies to CP method – minimise daily head‑count deviation.
    rest_constraint : bool, default True
        Forbid assigning an employee to back‑to‑back shifts in sequence.
    seniority : bool, default False
        Enforce ≥1 senior/3‑yr‑experienced employee on shifts where min_staff > 1.
    fairness_weight : int, default 1
        Multiplier on the fairness objective (higher → stronger balancing).
    work_percentage_threshold : int, optional
        If given, only employees with percentage > threshold are considered.
    experience_threshold : int, optional
        If given, only employees with experience_years > threshold are considered.
    relax_* : bool
        Forwarded to CP optimiser.
    """
    import json  # local to keep original imports unchanged

    # --- optional employee filtering --------------------------------------
    filtered_schema = _filter_employees(
        schema,
        wp_threshold=work_percentage_threshold,
        exp_threshold=experience_threshold,
    )

    if method == "greedy":
        return build_basic_schedule(filtered_schema)

    if method == "cp":
        return build_optimized_schedule_cp(
            filtered_schema,
            relax_work_percentage=relax_work_percentage,
            relax_coverage=relax_coverage,
            relax_availability=relax_availability,
            fairness=fairness,
            fairness_weight=fairness_weight,
            rest_constraint=rest_constraint,
            seniority=seniority,
        )

    return {"error": f"Unknown method '{method}'"}

def build_optimized_schedule_cp(schema: dict, *, relax_work_percentage=False, relax_coverage=False,
                                 relax_availability=False, fairness=True, fairness_weight=1,
                                 rest_constraint=True, seniority=False):
    """
    Optimised schedule generator using Google OR‑Tools CP‑SAT.

    Parameters
    ----------
    schema : dict
        Valid company/employee/shift schema.
    relax_* : bool
        Flags that relax hard constraints into soft ones.
    fairness : bool
        Whether to minimise the daily head‑count spread (max‑min).
    fairness_weight : int
        Linear weight for the fairness objective.
    rest_constraint : bool
        Enforce "no back‑to‑back shifts" rule.
    seniority : bool
        Require ≥1 senior/experienced employee on larger shifts.

    Returns
    -------
    dict
        • On success: `{ day → [ { "shift": str, "employee": str } ] }`  
        • On infeasible model: `{ "error": str }`
    """
    model = cp_model.CpModel()

    # TODO: Future constraints to implement:
    # - Max number of shifts per employee
    # - Minimum rest hours between shifts
    # - Require ≥1 experienced employee per shift
    # - Avoid assigning students to weekday mornings
    # - Fairness balancing (number of shifts per employee)
    employees = schema["employees"]
    shift_structure = schema["shift_structure"]
    days = schema.get("days", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])

    # if the user didn’t specify min_staff, assume 1 so the model is feasible
    for sh in shift_structure:
        sh.setdefault("min_staff", 1)

    # Build variables: X[e,d,s] = 1 if employee e works shift s on day d
    X = {}
    for e_idx, employee in enumerate(employees):
        for d_idx, day in enumerate(days):
            for s_idx, shift in enumerate(shift_structure):
                var = model.NewBoolVar(f"x_{e_idx}_{d_idx}_{s_idx}")
                X[(e_idx, d_idx, s_idx)] = var

    # 1. Shift coverage constraint
    for d_idx, day in enumerate(days):
        for s_idx, shift in enumerate(shift_structure):
            if relax_coverage:
                # Later: add as soft constraint with penalty
                continue
            min_staff = shift.get("min_staff", 1) # Minimum staff required for this shift
            model.Add(sum(X[(e_idx, d_idx, s_idx)] for e_idx, _ in enumerate(employees)) >= min_staff)

    # 2. Employee availability constraint
    if not relax_availability:
        for e_idx, employee in enumerate(employees):
            unavailable_days = set(employee.get("availability", {}).get("unavailable_days", []))
            unavailable_times = set(employee.get("availability", {}).get("unavailable_times", []))

            for d_idx, day in enumerate(days):
                for s_idx, shift in enumerate(shift_structure):
                    shift_name = shift["name"]

                    if (day in unavailable_days) or (shift_name in unavailable_times):
                        model.Add(X[(e_idx, d_idx, s_idx)] == 0)

    # 2b. Role‑coverage per shift (based on roles_primary)
    for d_idx, day in enumerate(days):
        for s_idx, shift in enumerate(shift_structure):
            required = shift.get("required_roles", {})
            for role, min_count in required.items():
                model.Add(
                    sum(
                        X[(e_idx, d_idx, s_idx)]
                        for e_idx, emp in enumerate(employees)
                        if role in emp.get("roles_primary", [])
                    ) >= min_count
                )

    # 2c. Rest‑period constraint: forbid an employee taking *adjacent* shifts
    #     in the daily sequence, including last shift of day d followed by
    #     first shift of day d+1 (e.g. 16‑24 → 00‑08).
    if rest_constraint and len(shift_structure) > 1:
        n_shifts = len(shift_structure)
        for e_idx in range(len(employees)):
            for d_idx in range(len(days)):
                for s_idx in range(n_shifts):
                    nxt_day  = d_idx if s_idx < n_shifts - 1 else (d_idx + 1)
                    nxt_shift= (s_idx + 1) % n_shifts
                    if nxt_day >= len(days):
                        continue  # no next day
                    model.Add(
                        X[(e_idx, d_idx, s_idx)] + X[(e_idx, nxt_day, nxt_shift)] <= 1
                    )

    # 2d. Seniority constraint (optional)
    if seniority:
        for d_idx, day in enumerate(days):
            for s_idx, shift in enumerate(shift_structure):
                # only when shift needs more than 2 staff
                if shift.get("min_staff",1) <= 2:
                    continue
                model.Add(
                    sum(
                        X[(e_idx, d_idx, s_idx)]
                        for e_idx, emp in enumerate(employees)
                        if emp.get("senior", False) or emp.get("experience_years",0) >= 3
                    ) >= 1
                )

    # 3. Work percentage constraint
    # total hours the schedule actually requires
    total_schedule_hours = len(days) * sum(s["hours"] for s in shift_structure)

    for e_idx, employee in enumerate(employees):
        target_hours = int((employee.get("work_percentage", 100) / 100) * total_schedule_hours)
        weekly_cap = 40  # hours; realistic full‑time cap
        target_hours = min(target_hours, weekly_cap)

        assigned_hours = []
        for d_idx, day in enumerate(days):
            for s_idx, shift in enumerate(shift_structure):
                assigned_hours.append(X[(e_idx, d_idx, s_idx)] * shift["hours"])

        total_assigned_hours = sum(assigned_hours)

        if relax_work_percentage:
            model.Add(total_assigned_hours >= 0.95 * target_hours)
            model.Add(total_assigned_hours <= 1.05 * target_hours)
        else:
            model.Add(total_assigned_hours == target_hours)

    # -- Objective: minimise daily staffing spread (max_staff - min_staff) --
    if fairness:
        staff_per_day = []
        max_poss = len(employees) * len(shift_structure)
        for d in range(len(days)):
            staff_d = model.NewIntVar(0, max_poss, f"staff_{d}")
            model.Add(staff_d == sum(
                X[(e, d, s)]
                for e in range(len(employees))
                for s in range(len(shift_structure))
            ))
            staff_per_day.append(staff_d)

        max_staff = model.NewIntVar(0, max_poss, "max_staff")
        min_staff = model.NewIntVar(0, max_poss, "min_staff")
        for staff_d in staff_per_day:
            model.Add(staff_d <= max_staff)
            model.Add(staff_d >= min_staff)

        spread = model.NewIntVar(0, max_poss, "spread")
        model.Add(spread == max_staff - min_staff)
        model.Minimize(spread * fairness_weight)

    # Define solver and solve
    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        # Build output
        schedule = defaultdict(list)
        for d_idx, day in enumerate(days):
            for s_idx, shift in enumerate(shift_structure):
                for e_idx, employee in enumerate(employees):
                    if solver.Value(X[(e_idx, d_idx, s_idx)]) == 1:
                        schedule[day].append({"shift": shift["name"], "employee": employee["name"]})
        return dict(schedule)
    else:
        return {"error": "No feasible schedule found with current constraints."}


def build_partial_schedule_high_percentage(schema_data: Dict[str, Any], threshold: int = 50) -> Dict[str, Any]:
    """
    Build a schedule using only employees with work_percentage > threshold.
    """
    employees = schema_data.get("employees", [])
    selected_employees = [e for e in employees if e.get("work_percentage", 100) > threshold]
    
    return {"status": "success", "message": f"Partial schedule created for employees with > {threshold}% work.", "selected_employees": selected_employees}

def build_partial_schedule_experience_threshold(schema_data: Dict[str, Any], threshold: int = 1) -> Dict[str, Any]:
    """
    Build a schedule using only employees with experience_years > threshold.
    """
    employees = schema_data.get("employees", [])
    selected_employees = [e for e in employees if e.get("experience_years", 0) > threshold]
    
    return {"status": "success", "message": f"Partial schedule created for employees with > {threshold} years experience.", "selected_employees": selected_employees}

# ------------------
# Helper Functions
# ------------------

def validate_schema(schema_data: Dict[str, Any], **kwargs) -> List[str]:
    """Lightweight sanity‑check; returns a list of human‑readable warnings (empty if OK)."""
    warnings = []
    
    if "company_name" not in schema_data:
        warnings.append("Missing company_name.")
    if "opening_hours" not in schema_data:
        warnings.append("Missing opening_hours.")
    if "employees" not in schema_data or not schema_data["employees"]:
        warnings.append("Missing or empty employees list.")
    if "shift_structure" not in schema_data:
        warnings.append("Missing shift_structure.")
    
    # Additional employee field checks
    for emp in schema_data.get("employees", []):
        if "name" not in emp:
            warnings.append("One employee missing name.")
        if "employment_type" not in emp:
            warnings.append(f"Employee {emp.get('name', 'Unknown')} missing employment_type.")
    
    return warnings

# ------------------
# Register Available Tools
# ------------------

FUNCTION_DEFINITIONS = [
    {
        "name": "build_schedule",
        "description": "General scheduling function supporting CP or greedy methods, optional fairness and employee filters.",
        "parameters": {
            "type": "object",
            "properties": {
                "method": {"type": "string", "enum": ["cp", "greedy"], "default": "cp"},
                "fairness": {"type": "boolean", "default": True},
                "fairness_weight": {"type": "integer", "default": 1},
                "work_percentage_threshold": {"type": "integer"},
                "experience_threshold": {"type": "integer"},
                "relax_work_percentage": {"type": "boolean"},
                "relax_coverage": {"type": "boolean"},
                "relax_availability": {"type": "boolean"},
                "rest_constraint": {"type": "boolean", "default": True},
                "seniority": {"type": "boolean", "default": False},
            },
            "required": []
        }
    },
    {
        "name": "validate_schema",
        "description": "Validate the input schema and return warnings if any required fields are missing.",
        "parameters": {"type": "object", "properties": {}, "required": []}
    }
]

AVAILABLE_TOOLS = [
    {"type": "function", "function": tool_def}
    for tool_def in FUNCTION_DEFINITIONS
]

def format_schedule_by_shift(schedule: dict) -> str:
    from collections import defaultdict
    lines = []
    for day, shifts in schedule.items():
        lines.append(f"{day}:")
        grouped = defaultdict(list)
        for entry in shifts:
            grouped[entry["shift"]].append(entry["employee"])
        for shift, employees in grouped.items():
            lines.append(f"  {shift}: {', '.join(employees)}")
        lines.append("")
    return "\n".join(lines)


# tools available to the agent
tool_functions = {
    "build_schedule": build_schedule,
    "validate_schema": validate_schema,
}
if __name__ == "__main__":
    from pprint import pprint
    from collections import defaultdict

    print("🔧 Testing scheduling tools...\n")

    # 1. Minimal test schema
    test_schema = {
        "company_name": "Mario’s Pizza",
        "opening_hours": {
            day: {"open": "11:00", "close": "23:00"}
            for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        },
        "shift_structure": [
            {"name": "Day",   "hours": 8, "min_staff": 2, "required_roles": {"Baker":1, "Cashier":1}},
            {"name": "Night", "hours": 8, "min_staff": 3, "required_roles": {"Baker":1, "Driver":1}}
        ],
        "employees": [
            {"name": "Anna",  "employment_type": "full-time",  "work_percentage": 100, "roles_primary": ["Baker"],  "senior": True},
            {"name": "James", "employment_type": "part-time",  "work_percentage": 80,  "roles_primary": ["Driver"], "experience_years": 4, "senior": True},
            {"name": "Sophia","employment_type": "part-time",  "work_percentage": 75,  "roles_primary": ["Cashier"],"availability": {"unavailable_times": ["Night"]}},
            {"name": "Liam",  "employment_type": "part-time",  "work_percentage": 60,  "roles_primary": ["Baker"]},
            {"name": "Maya",  "employment_type": "part-time",  "work_percentage": 60,  "roles_primary": ["Cashier"], "experience_years": 5, "senior": True},
            {"name": "Noah",  "employment_type": "part-time",  "work_percentage": 60,  "roles_primary": ["Driver"]},
            {"name": "Olivia","employment_type": "part-time",  "work_percentage": 70,  "roles_primary": ["Baker"],  "senior": True},
            {"name": "Ethan", "employment_type": "part-time",  "work_percentage": 70,  "roles_primary": ["Driver"]},
            {"name": "Ava",   "employment_type": "part-time",  "work_percentage": 70,  "roles_primary": ["Cashier"]},
            {"name": "Lucas", "employment_type": "part-time",  "work_percentage": 60,  "roles_primary": ["Baker"]},
            {"name": "Emma",  "employment_type": "part-time",  "work_percentage": 60,  "roles_primary": ["Driver"], "experience_years": 3, "senior": True},
            {"name": "Henry", "employment_type": "part-time",  "work_percentage": 50,  "roles_primary": ["Cashier"]}
        ],
        "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    }

    # 2. Schema validation
    print("🧪 Validating schema...")
    warnings = validate_schema(test_schema)
    if warnings:
        print("⚠️ Schema warnings:")
        for w in warnings:
            print("-", w)
    else:
        print("✅ Schema is valid.\n")

    # 3. Test basic schedule
    print("🧪 Running build_basic_schedule...")
    basic = build_basic_schedule(test_schema)
    pprint(basic)
    print("\n")

    # 4. Test optimized schedule
    print("🧪 Running build_optimized_schedule_cp...")
    optimized = build_optimized_schedule_cp(test_schema)
    if "error" in optimized:
        print("❌ Optimized schedule failed:", optimized["error"])
    else:
        print("✅ Optimized schedule:\n")
        print(format_schedule_by_shift(optimized))

    # 5. Partial schedule based on work percentage
    print("🧪 Testing partial schedule by work percentage (>60%)...")
    partial = build_partial_schedule_high_percentage(test_schema, threshold=60)
    pprint(partial)
    print()

    # 6. Partial schedule based on experience
    print("🧪 Testing partial schedule by experience (>1 year)...")
    partial_exp = build_partial_schedule_experience_threshold(test_schema, threshold=1)
    pprint(partial_exp)
    print()

    # 7. Unified build_schedule tests
    print("🧪 Unified build_schedule tests...")

    # Cases list: test CP, greedy, fairness, work percentage, experience, and seniority rules with the updated 12-employee schema.
    cases = [
        ("Default CP (fair)" , dict()),
        ("CP no fairness"    , dict(fairness=False)),
        ("CP weight5", dict(fairness_weight=5)),
        ("Greedy"            , dict(method="greedy")),
        ("CP WP>60"          , dict(work_percentage_threshold=60)),
        ("CP EXP>1"         , dict(experience_threshold=1)),
        ("CP rest+senior" , dict(rest_constraint=True, seniority=True)),
    ]

    for label, kwargs in cases:
        print(f"\n-- {label} --")
        res = build_schedule(test_schema, **kwargs)
        if isinstance(res, dict) and "error" in res:
            print("❌", res["error"])
        elif isinstance(res, dict) and all(isinstance(v, list) for v in res.values()):
            print(format_schedule_by_shift(res))
        else:
            print(res)
# ------------------
# Future Planned Functions (to implement later)
# ------------------

# def build_partial_schedule_low_percentage(...):
#     "Partial schedule for employees with < threshold %."

# def build_partial_schedule_custom_filter(...):
#     "Partial schedule based on custom filters (e.g., student flag)."

# def complete_partial_schedule(...):
#     "Complete a partial schedule by filling in missing slots."

# def optimize_shift_fairness(...):
#     "Balance shifts among employees for fairness."

# def optimize_minimum_rest_periods(...):
#     "Ensure minimum rest hours between employee shifts."

# def export_schedule_excel(...):
#     "Export final schedule to Excel."

# def export_schedule_pdf(...):
#     "Export final schedule to PDF."

# def connect_to_google_calendar(...):
#     "Push schedule events to Google Calendar."