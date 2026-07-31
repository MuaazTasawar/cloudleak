# CloudLeak

> Real-time AWS cost anomaly detection that finds and kills the forgotten resources actually burning your budget.

---

## Table of Contents

- [Overview](#overview)
- [The Problem This Solves](#the-problem-this-solves)
- [How CloudLeak Works — Full Architecture](#how-cloudleak-works--full-architecture)
- [The Anomaly Detection Algorithm, Explained](#the-anomaly-detection-algorithm-explained)
- [The Idle Resource Detection Algorithm, Explained](#the-idle-resource-detection-algorithm-explained)
- [The Remediation Safety Model](#the-remediation-safety-model)
- [Alerting Flow](#alerting-flow)
- [Tech Stack](#tech-stack)
- [Features](#features)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [Infrastructure as Code — What Terraform Actually Creates](#infrastructure-as-code--what-terraform-actually-creates)
- [Cost of Running CloudLeak Itself](#cost-of-running-cloudleak-itself)
- [Phase Build History](#phase-build-history)
- [Known Limitations](#known-limitations)
- [Future Improvements](#future-improvements)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

CloudLeak is a FinOps (Financial Operations) tool that continuously watches AWS spend, detects statistically anomalous cost spikes before they become a surprise bill, and finds EC2 instances that are running but doing nothing useful — the classic "forgot to turn it off" scenario that quietly drains a budget over weeks. It was built specifically for the reality of students, solo developers, and small teams on AWS free tier: no dedicated cloud cost team, no enterprise FinOps tooling budget, but the exact same risk of a forgotten `t3.medium` turning a $0 month into a $40 one.

Unlike AWS's built-in Cost Anomaly Detection (which is a black box with roughly a 24-hour detection lag and no remediation path), CloudLeak is fully transparent about its math — every flagged anomaly comes with the exact z-score and baseline numbers that triggered it — and closes the loop by letting you act on what it finds directly from the dashboard, safely, with a mandatory preview step before anything destructive happens.

## The Problem This Solves

Picture the realistic failure mode this project targets: you spin up an EC2 instance to test something at 11pm, it works, you move on with your life, and the instance keeps running. Nobody notices for two weeks. On AWS free tier this might silently eat your monthly free hours; outside free tier, it's a real, avoidable charge. Cost Explorer *technically* shows this in your billing dashboard, but only if you go looking for it, days after the fact, with no indication of *which* resource caused the increase.

CloudLeak closes that gap in two ways simultaneously:
1. **On the spend side** — it watches your daily AWS bill and flags any day that deviates significantly from your normal spending pattern, so a spike surfaces within the collector's next run (every 15 minutes) instead of whenever you happen to check billing.
2. **On the resource side** — independent of billing data entirely, it directly polls CloudWatch for EC2 CPU and network utilization, so it can catch "this specific instance has been sitting idle" even *before* that idle time shows up as a cost anomaly, because a single small idle instance often isn't statistically loud enough to trip the spend-level detector on its own.

## How CloudLeak Works — Full Architecture

CloudLeak has three moving parts that operate independently but share the same data store:

**1. The Lambda Collector (`lambda/collector/handler.py`)**
This is the heartbeat of the system. An EventBridge rule triggers it every 15 minutes (configurable via `collector_schedule_expression` in Terraform). Each run does two unrelated jobs back to back:
- Pulls the last ~14 days of daily spend from the Cost Explorer API, stores each day in DynamoDB, and runs the anomaly detection algorithm (see below) against today's number.
- Lists every currently-running EC2 instance, pulls its CPU/network utilization from CloudWatch over the configured lookback window, and runs the idleness heuristic against each one.

Both jobs write their findings to DynamoDB and fire a Slack alert on anything new. This Lambda is deliberately self-contained — it doesn't import the FastAPI backend code, and only depends on `boto3`, which ships with the Lambda Python runtime by default. That keeps the deployment zip tiny and keeps the scheduled job's blast radius small: it can only ever read AWS data and write to CloudLeak's own three DynamoDB tables, nothing else.

**2. The FastAPI Backend (`backend/app/`)**
This is what the dashboard actually talks to. It never touches AWS billing or compute APIs directly for *reading* dashboard data — instead it reads whatever the Lambda collector already wrote to DynamoDB, which keeps the dashboard fast and avoids re-hitting rate-limited/costed APIs like Cost Explorer on every page load. The one place the backend *does* call AWS directly is remediation — when you click Stop or Terminate on a flagged instance, that request goes straight to the EC2 API in real time, because remediation is a live, user-initiated action, not something that should wait for the next collector cycle.

**3. The Next.js Dashboard (`frontend/`)**
A single-page dashboard that polls the backend every 30 seconds and renders three views: a spend trend line chart with a baseline reference line, a feed of detected anomalies, and a table of currently flagged idle resources with inline remediation controls.

Data flows in one direction for detection (`AWS → Lambda → DynamoDB → Backend → Frontend`) and in the reverse direction for action (`Frontend → Backend → AWS`, with DynamoDB updated afterward to reflect the new state).

## The Anomaly Detection Algorithm, Explained

CloudLeak uses a **rolling z-score model** — a standard statistical outlier detection technique, chosen deliberately over a machine learning model because it's fully explainable. In an interview, you can draw this on a whiteboard from memory; a trained model's threshold, by contrast, is much harder to defend on the spot.

Here's exactly what happens on every collector run:

1. **Build the baseline.** Take the last `COST_BASELINE_DAYS` (default 7) days of spend, *excluding* today (today's number is usually partial/incomplete since the day isn't over). Compute the mean (μ) and standard deviation (σ) of that window.
2. **Compute today's z-score.** For today's actual spend `x`, the z-score is:

   ```
   z = (x − μ) / σ
   ```

   This tells you how many standard deviations today's spend is from the recent normal. A z-score of 0 means spend is exactly average; a z-score of 3 means today is 3 standard deviations above normal — a large, statistically rare deviation if your spend has historically been stable.

3. **Flag if it exceeds the threshold.** If `|z| >= ANOMALY_ZSCORE_THRESHOLD` (default 2.5), it's flagged as an anomaly. Direction matters too — a positive z-score is a spend *spike*, a negative one is a spend *drop* (which can also matter — e.g. a service silently failing to run at all).

4. **Classify risk.** A high z-score on a baseline of $0.10/day isn't very interesting in absolute terms. So risk classification folds in the dollar amount too:
   - **High risk**: z-score ≥ 1.5× the threshold *and* the dollar increase over baseline exceeds $5
   - **Medium risk**: z-score meets the threshold, but the dollar swing is smaller
   - **Low risk**: below threshold entirely (not flagged as an anomaly at all in this case)

5. **Edge case — zero variance.** If your spend has been perfectly flat for the whole baseline window (σ = 0), any deviation at all is treated as a very large z-score (capped at 999) rather than causing a divide-by-zero crash — a flat baseline means *any* change is notable.

One deliberate simplicity here: this is a **univariate** model (it only looks at total daily spend), not a per-service breakdown. The `get_spend_by_service()` function in `cost_explorer.py` exists specifically to let you drill into *which* AWS service caused a flagged anomaly after the fact, but it isn't part of the detection trigger itself — a natural v2 improvement (see Future Improvements).

## The Idle Resource Detection Algorithm, Explained

Independent of the spend anomaly logic, CloudLeak separately scans every currently-running EC2 instance for signs it's doing nothing useful:

1. **List running instances** via `ec2:DescribeInstances`, filtered to `instance-state-name = running`.
2. **Pull utilization** for each instance from CloudWatch: average CPU utilization (%) and average network bytes (NetworkIn + NetworkOut combined) over the `IDLE_HOURS_THRESHOLD` window (default 6 hours), bucketed hourly.
3. **Apply the idle test.** An instance is flagged as idle only if **both** conditions hold:
   - Average CPU < `IDLE_CPU_THRESHOLD_PERCENT` (default 5%)
   - Average network < `IDLE_NETWORK_THRESHOLD_BYTES` (default 1MB)

   Both conditions must be true together deliberately — an instance with low CPU but high network traffic might be doing legitimate I/O-bound work (e.g. acting as a proxy or file server) and shouldn't be flagged just because it isn't CPU-bound.
4. **Estimate cost impact.** Rather than calling the (slower, region-inconsistent) AWS Pricing API, CloudLeak keeps a small lookup table of approximate on-demand hourly rates for common free-tier-adjacent instance types (`t2.micro`, `t3.micro`, `t3.small`, etc.) and projects a monthly cost estimate: `hourly_rate × 24 × 30`.
5. **Classify risk** based on estimated monthly waste and how long it's been idle — an instance idle for 24+ hours *or* projected to cost more than $20/month is High risk; anything meeting the base idle threshold is Medium.
6. **Track first-seen vs. last-checked.** DynamoDB stores both `first_flagged_at` and `last_checked_at` per resource, so re-scanning an already-flagged instance updates its current stats without losing track of how long it's actually been a problem.

## The Remediation Safety Model

Every remediation action — stopping or terminating an EC2 instance — is built around one rule: **the system defaults to doing nothing, and requires an explicit second confirmation before it does anything irreversible.**

Concretely:
- Every remediation request carries a `dry_run` flag, defaulting to `true`.
- On `dry_run=true`, the backend computes and returns exactly what *would* happen (which instance, which action) without calling any AWS mutating API at all.
- The frontend enforces a two-click flow: the first click (Stop/Terminate) always fires a dry-run preview and shows the resulting message inline; only a second, explicit "Confirm stop/terminate" click fires the real `dry_run=false` request that actually calls `ec2:StopInstances` or `ec2:TerminateInstances`.
- Every remediation attempt — successful or failed, dry-run or real — is logged and sent to Slack, so there's an audit trail even for accidental double-clicks.
- The scheduled Lambda collector **never** has remediation permissions at all (see its IAM policy in `infra/iam.tf` — it's read-only on AWS, write-only on CloudLeak's own DynamoDB tables). Destructive actions are only reachable through the backend API, which only fires in response to an explicit, authenticated human action from the dashboard. A scheduled job automatically terminating your infrastructure is exactly the kind of failure mode this architecture is designed to make structurally impossible, not just discouraged.

## Alerting Flow

Slack is the primary alert channel, wired via a simple Incoming Webhook (deliberately not the full Slack SDK, to keep the Lambda package small). Three distinct events trigger a Slack message:
1. A new cost anomaly is detected (includes risk level, z-score, and dollar description)
2. A new idle resource is flagged for the first time (re-flagging an already-known resource does not re-alert, to avoid spamming the channel every 15 minutes)
3. A remediation action completes (success or failure, dry-run or real)

An SNS topic exists as a secondary/backup channel — currently wired into the Lambda's environment variables but not yet actively published to (see Known Limitations) — with an optional email subscription for anyone who wants alerts outside Slack.

## Tech Stack

| Layer          | Technology                                          | Why |
|----------------|------------------------------------------------------|-----|
| Backend API    | Python, FastAPI, boto3, Pydantic                      | Fast to build, strong typing via Pydantic models shared across every endpoint, boto3 is the standard AWS SDK |
| Scheduled Job  | AWS Lambda (Python 3.12), EventBridge                 | Serverless, pay-per-invocation, no server to manage or forget about — fitting for a cost-optimization tool |
| Database       | DynamoDB (on-demand billing)                           | No provisioned capacity to forget about; scales to zero when idle |
| Frontend       | Next.js 14, React, TypeScript, Tailwind CSS, Recharts  | Fast dashboard iteration, typed API contracts via shared `types/index.ts` |
| Infrastructure | Terraform                                              | Reproducible, disposable infra — spin up before a demo, tear down after |
| Alerting       | Slack Incoming Webhooks, SNS (backup channel)          | Zero-dependency HTTP POST for Slack; SNS for a channel-agnostic backup |
| Cloud          | AWS (Cost Explorer, CloudWatch, EC2, IAM, DynamoDB)    | Target platform |

## Features

- Rolling-baseline z-score anomaly detection on daily AWS spend — fully explainable, not a black box
- Automatic idle EC2 instance detection via combined CPU + network utilization heuristics
- Risk classification (low / medium / high) combining statistical significance with actual dollar impact
- Live dashboard: spend trend chart with baseline overlay, anomaly feed, flagged resource table
- Two-step, dry-run-safe remediation (preview → explicit confirm) for stopping/terminating idle instances
- Slack alerts on new anomalies, newly flagged resources, and remediation actions — with de-duplication so already-known idle resources don't re-alert every cycle
- Fully defined infrastructure as code — the entire backend infrastructure (Lambda, DynamoDB, EventBridge, IAM, SNS) can be created and destroyed on demand with `terraform apply` / `terraform destroy`

## Project Structure

```
cloudleak/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                 # FastAPI app entrypoint, CORS, global error handler, startup config check
│   │   ├── config.py                # Centralized settings loaded from .env
│   │   ├── db.py                    # DynamoDB access layer — every query the backend makes goes through here
│   │   ├── models.py                # Pydantic models — API contracts and DynamoDB item shapes
│   │   ├── routers/
│   │   │   ├── spend.py             # /api/spend/* — trend chart data, anomaly list, acknowledge
│   │   │   └── resources.py         # /api/resources/* — flagged resources, remediation, dismiss
│   │   ├── services/
│   │   │   ├── cost_explorer.py     # AWS Cost Explorer API wrapper
│   │   │   ├── cloudwatch.py        # AWS CloudWatch metrics wrapper
│   │   │   ├── anomaly.py           # The z-score baseline detection algorithm
│   │   │   ├── idleness.py          # The idle EC2 detection heuristic
│   │   │   └── remediation.py       # Dry-run-safe stop/terminate logic
│   │   └── alerts/
│   │       └── slack.py             # Slack webhook alert sender
│   ├── requirements.txt
│   └── .env.example
├── lambda/
│   └── collector/
│       ├── handler.py               # Self-contained scheduled collector (spend + idleness in one run)
│       └── requirements.txt
├── infra/                           # Terraform: all AWS resources this project provisions
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   ├── dynamodb.tf
│   ├── lambda.tf
│   ├── eventbridge.tf
│   ├── iam.tf
│   └── sns.tf
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx             # Main dashboard — fetches spend/anomalies/resources, wires actions
│   │   │   └── globals.css
│   │   ├── components/
│   │   │   ├── SpendChart.tsx       # Recharts line chart with baseline reference line + anomaly dots
│   │   │   ├── AnomalyCard.tsx      # Individual anomaly display + acknowledge action
│   │   │   ├── ResourceTable.tsx    # Flagged resources table with two-step remediation UI
│   │   │   └── Navbar.tsx
│   │   ├── lib/
│   │   │   └── api.ts               # Typed fetch wrapper for every backend endpoint
│   │   └── types/
│   │       └── index.ts             # Shared TypeScript types matching the backend's Pydantic models
│   ├── package.json
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   ├── next.config.js
│   └── .env.local.example
├── .gitignore
└── README.md
```

## Getting Started

### Prerequisites

- Python 3.11+ (3.12 recommended — matches the Lambda runtime)
- Node.js 18+ and npm
- An AWS account with an IAM user scoped for this project (never use root keys)
- [Terraform](https://developer.hashicorp.com/terraform/install) 1.5+ (to deploy the Lambda/DynamoDB/EventBridge infra)
- [AWS CLI](https://aws.amazon.com/cli/) (used by Terraform's provider and for manually invoking the Lambda)
- A Slack workspace where you can create an Incoming Webhook (optional — alerts are skipped, not broken, without it)

### Clone the Repo

```bash
git clone https://github.com/MuaazTasawar/cloudleak.git
cd cloudleak
```

### Installation

**Backend:**
```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt --break-system-packages
copy .env.example .env
# Fill in .env with real AWS keys, table names, and Slack webhook
```

**Frontend:**
```powershell
cd frontend
npm install
copy .env.local.example .env.local
```

**Infrastructure:**
```powershell
cd infra
# create terraform.tfvars with slack_webhook_url, alert_email, aws_region first
terraform init
terraform plan
terraform apply
```

### Running the App

```powershell
# Terminal 1 — backend
cd backend
.\venv\Scripts\Activate.ps1
uvicorn app.main:app --reload

# Terminal 2 — frontend
cd frontend
npm run dev
```

Backend: `http://localhost:8000` (interactive API docs at `/docs`). Frontend: `http://localhost:3000`.

To seed data immediately instead of waiting for the first 15-minute EventBridge trigger:
```powershell
aws lambda invoke --function-name cloudleak-collector --region eu-north-1 out.json
```

## Environment Variables

### `backend/.env`

| Variable | Description |
|----------|-------------|
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | IAM user credentials, scoped to Cost Explorer read, CloudWatch read, EC2 describe/stop/terminate |
| `AWS_REGION` | Region your resources live in |
| `DYNAMODB_TABLE_SPEND` / `DYNAMODB_TABLE_ANOMALIES` / `DYNAMODB_TABLE_RESOURCES` | Must match the table names created by `infra/dynamodb.tf` |
| `SLACK_WEBHOOK_URL` | Slack Incoming Webhook URL |
| `ANOMALY_ZSCORE_THRESHOLD` | Z-score cutoff for flagging a day as anomalous (default `2.5`) |
| `COST_BASELINE_DAYS` | Rolling window size for the baseline mean/std-dev (default `7`) |
| `IDLE_CPU_THRESHOLD_PERCENT` / `IDLE_NETWORK_THRESHOLD_BYTES` | Utilization cutoffs for the idle test |
| `IDLE_HOURS_THRESHOLD` | How many hours of sustained idle before flagging |
| `CORS_ORIGINS` | Allowed frontend origins |

### `frontend/.env.local`

| Variable | Description |
|----------|-------------|
| `NEXT_PUBLIC_API_BASE_URL` | Backend API URL |

### `infra/terraform.tfvars`

| Variable | Description |
|----------|-------------|
| `slack_webhook_url` | Same webhook, used by the Lambda collector directly |
| `alert_email` | Optional SNS backup email subscription |
| `aws_region` | Deployment region |

## Infrastructure as Code — What Terraform Actually Creates

Running `terraform apply` provisions exactly 9 resources, all tagged `Project = cloudleak` for easy identification/cleanup:
1. **3× DynamoDB tables** (`spend-baseline`, `anomalies`, `flagged-resources`) — all on-demand (`PAY_PER_REQUEST`) billing, so there's zero idle capacity cost
2. **1× Lambda function** — the scheduled collector, packaged automatically from `lambda/collector/` at plan time via the `archive_file` data source (no manual zip step)
3. **1× EventBridge rule + target** — triggers the Lambda every 15 minutes
4. **1× IAM role + inline policy** — scoped tightly: read-only on Cost Explorer/CloudWatch/EC2-describe, write-only on CloudLeak's own 3 tables, publish-only on the SNS topic, plus standard Lambda logging permissions. No `StopInstances`/`TerminateInstances` here — remediation only ever happens through the backend, triggered by a human.
5. **1× CloudWatch Log Group** — the Lambda's logs, retained 14 days
6. **1× SNS topic + optional email subscription** — backup alert channel

The whole stack is disposable by design — `terraform destroy` tears down all 9 resources (and their DynamoDB data) in dependency-aware order.

## Cost of Running CloudLeak Itself

Worth being explicit about this, since it's a cost-optimization tool: running CloudLeak isn't free, though it's very cheap at small scale.
- **DynamoDB on-demand**: effectively $0 at this data volume (a handful of small items written every 15 minutes)
- **Lambda**: well within the always-free tier (1M free requests/month; this uses ~2,880 invocations/month)
- **EventBridge**: free for this rule volume
- **Cost Explorer API**: **not** in the AWS free tier — each `GetCostAndUsage` call costs $0.01. At one call per 15-minute collector run, that's roughly $0.01 × 4 × 24 × 30 ≈ **$28.80/month** if left running continuously. This is the main reason the recommended workflow is to `terraform apply` before a demo and `terraform destroy` right after, rather than leaving it running 24/7.
- **CloudWatch GetMetricStatistics**: free tier covers the first 1M requests/month, comfortably enough for this usage pattern

## Phase Build History

| Phase | Name | What Was Built |
|-------|------|-----------------|
| 0 | Project Init & Config | `.gitignore`, backend/frontend base config, dependency manifests |
| 1 | Core Backend Structure | FastAPI app skeleton, DynamoDB access layer, Pydantic models |
| 2 | AWS Data Collection Services | Cost Explorer and CloudWatch integrations |
| 3 | Anomaly & Idleness Detection Engine | Rolling z-score baseline model, idle EC2 heuristics |
| 4 | Remediation & Alerts | Dry-run-safe EC2 remediation, Slack webhook alerting |
| 5 | API Routers | Spend and resources endpoints wired into FastAPI |
| 6 | Lambda Collector | Self-contained scheduled collector for anomaly + idleness detection |
| 7 | Infrastructure as Code | Terraform for Lambda, DynamoDB, EventBridge, IAM, SNS |
| 8 | Frontend Dashboard | Next.js dashboard, spend chart, anomaly cards, resource table |
| 9 | Polish & Finalize | Global error handling, startup config validation, Tailwind/PostCSS setup |

## Known Limitations

- **SNS publish isn't wired in yet.** The SNS topic ARN is passed into the Lambda's environment variables, but the collector doesn't call `sns.publish()` — Slack is the only active alert channel today. A one-line addition (`boto3.client("sns").publish(...)`) would close this.
- **Anomaly detection needs history.** With fewer than 4 days of spend data, the baseline can't be computed and detection is silently skipped — expected behavior on a fresh deployment, not a bug.
- **Cost estimates for idle instances use a static lookup table**, not the live AWS Pricing API — accurate for common free-tier-adjacent instance types, approximate for anything else.
- **Only EC2 instances are covered** for idleness detection and remediation. EBS volumes, NAT Gateways, and Elastic IPs are modeled in the data schema (`ResourceType` enum) but not yet actively scanned.
- **The spend anomaly model is univariate** — it detects that total spend changed, not automatically *which* service caused it (though `get_spend_by_service()` exists to manually drill in).

## Future Improvements

- Wire in the SNS publish call as a genuine backup channel to Slack
- Extend idle-resource scanning to EBS volumes, NAT Gateways, and Elastic IPs
- Per-service anomaly detection (flag "EC2 spend specifically spiked" rather than just "total spend spiked")
- Replace the static instance-cost lookup table with a live AWS Pricing API call, cached to avoid rate limits
- Add authentication to the dashboard/API before ever considering a non-local deployment
- A "resilience" style dry-run simulation mode that shows a week of historical data replayed through the detector, to demo detection behavior without needing live anomalous data

## Contributing

This is a personal portfolio project, but issues and suggestions are welcome via GitHub Issues.

## License

MIT