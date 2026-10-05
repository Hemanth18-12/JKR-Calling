# JKR Calling Official Python SDK

A native, zero-dependency Python client library to programmatically interact with JKR Calling voice AI platform.

---

## Installation

```bash
pip install ./packages/jkr-python-sdk
```

---

## Quickstart

```python
from jkr import JKRClient

# Initialize client (uses JKR_API_KEY and JKR_API_BASE environment variables if omitted)
client = JKRClient(
    api_key="your_api_key",
    base_url="https://jkr-calling-api.onrender.com"
)

# 1. List configured voice AI agents
agents = client.agents.list()
print("Agents:", [a["name"] for a in agents])

# 2. Check coin wallet balance
wallet = client.wallet.get_balance()
print(f"Current Coin Balance: {wallet['balance_coins']} coins")

# 3. Dispatch an outbound AI call to a customer
call = client.calls.dispatch(
    agent_id=agents[0]["id"],
    to_phone_e164="+919876543210",
    customer_name="Ravi Kumar",
)
print("Call Dispatched:", call["session_id"])

# 4. Interact with the Website Voice & Chat Widget programmatically
session = client.widget.start_session(
    agent_id=agents[0]["id"],
    visitor_name="Website Visitor",
    language="te-IN"
)
reply = client.widget.send_message(
    session_id=session["session_id"],
    message="నాకు రేపు అపాయింట్‌మెంట్ కావాలి"
)
print("AI Spoken Reply:", reply["reply_text"])
print("Audio URL:", reply["audio_url"])
```
