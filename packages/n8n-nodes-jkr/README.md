# n8n-nodes-jkr-calling

This is an n8n community node package that lets you integrate [JKR Calling](https://jkrcalling.com) into your n8n automation workflows.

---

## Operations Supported

### JKR Calling (Action Node)
- **Call**:
  - `Dispatch Call`: Triggers an AI voice phone call to any customer number with Dograh & Sarvam.
  - `Get Transcript`: Retrieves turn-by-turn spoken conversation transcripts.
- **Agent**:
  - `List Agents`: Lists configured AI agents and version metadata.
- **Wallet**:
  - `Check Balance`: Reads real-time coin wallet balance and recharge status.

### JKR Calling Trigger (Webhook Node)
- Triggers on:
  - `call.completed`: When a live phone call concludes.
  - `appointment.booked`: When the AI agent successfully confirms an appointment.
  - `widget.session_ended`: When a website visitor finishes a widget session.

---

## Installation

In your n8n instance:
1. Go to **Settings > Community Nodes**.
2. Select **Install**.
3. Enter `n8n-nodes-jkr-calling` in the **npm package name** field.
4. Agree to the risks of community nodes and click **Install**.
