# JKR Calling - Lead Generation & CRM Auto-Dialer

An intelligent outbound auto-dialer for dental clinics, hospitals, and sales teams to automatically call leads imported from CSV files, Meta Lead Ads, or CRM exports.

---

## Features

- **Automated Phone Normalization**: Automatically converts 10-digit, 11-digit (with leading `0`), and local Indian mobile numbers to standard E.164 (`+91XXXXXXXXXX`). Skips invalid formats.
- **Coin Wallet Protection**: Verifies workspace coin balance before dialing batch starts. Prevents mid-campaign disruptions.
- **Rate Limiting & Throttling**: Configurable delay between calls (`--delay 2.0`) to avoid carrier spam flags and comply with calling standards.
- **Dry-Run Simulation**: `--dry-run` flag allows teams to validate contact lists without spending coins or placing real calls.
- **Audit Results CSV**: Outputs a full status report with dispatch statuses, session IDs, and timestamps.

---

## Usage

### 1. Dry Run (Test phone numbers without dialing)
```bash
python packages/leadgen-automation/autodialer.py --input sample_leads.csv --dry-run
```

### 2. Live Calling
```bash
python packages/leadgen-automation/autodialer.py \
  --input sample_leads.csv \
  --output dialer_results.csv \
  --agent-id "<YOUR_AGENT_UUID>" \
  --delay 3.0
```
