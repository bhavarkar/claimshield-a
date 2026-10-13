import os

# Tests must not inherit the demo pacing from a developer's .env (load_dotenv never overrides).
os.environ["CLAIMSHIELD_DEMO_PACE"] = "0"
