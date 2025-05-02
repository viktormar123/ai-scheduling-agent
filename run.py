# run.py

from agent import SchedulingAgent
import os
import json

def load_existing_schema(filepath: str) -> dict:
    try:
        with open(filepath, "r") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("Invalid schema format.")
            return data
    except (json.JSONDecodeError, ValueError, TypeError):
        print("⚠️ Schema file is invalid or corrupted.")
        return None
    
def save_schema(schema: dict, filepath: str):
    with open(filepath, "w") as f:
        json.dump(schema, f, indent=2)

if __name__ == "__main__":
    schema_path = "data/current_schema.json"

    if os.path.exists(schema_path) and "--reset" in os.sys.argv:
        os.remove(schema_path)
        print("🗑️ Existing schema deleted.")
        print("A new schema will be created.")
        

    agent = SchedulingAgent()

    print("👋 Welcome to the Scheduling Assistant!")
    print("I'll help you build work shift schedules for your team.\n")
    print("Type 'create basic' or 'create optimized' to generate a schedule.")
    print("Type 'edit' to modify your current schema.")
    print("Type 'exit' to quit the assistant.")
    print("Type 'help' at any time to see these options again.\n")
    print("Type 'reset' to delete the current schema and start over.\n")
    print("Type 'schema' to view the current schema.\n")
    print("Type 'validate' to validate the current schema to check if it can be used for scheduling.\n")
    #print("Type 'load' to load an existing schema.\n")
    

    # Check if schema already exists
    if os.path.exists(schema_path):
        schema_data = load_existing_schema(schema_path)
        if schema_data is not None:
            print(f"✅ Loaded schema for company: {schema_data.get('company_name', 'Unnamed')}")
            agent.initialize_with_schema(schema_data)
        else:
            print("⚠️ Could not load existing schema. Starting fresh.\n")
            answers = agent.collect_initial_inputs()
            agent.initialize_from_text(answers)
            save_schema(agent.schema_data, schema_path)
            print(f"\n✅ Schema saved to {schema_path}")
    else:
        print("🔵 No existing schema found.")
        print("Please answer a few questions to create your company profile.\n")
        answers = agent.collect_initial_inputs()
        agent.initialize_from_text(answers)

        # Save newly created schema
        save_schema(agent.schema_data, schema_path)
        print(f"\n✅ Schema saved to {schema_path}")

    # Main loop
    agent.run()