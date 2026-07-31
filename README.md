# CloudLeak

> Real-time AWS cost anomaly detection that finds and kills the forgotten resources actually burning your budget.

## Overview

CloudLeak is a FinOps tool that watches your AWS spend continuously, flags statistically anomalous cost spikes using a rolling z-score baseline, and traces idle EC2 instances to their exact cost impact — all before a surprise bill shows up. A scheduled Lambda collector pulls Cost Explorer and CloudWatch data every 15 minutes, a FastAPI backend serves a live dashboard, and every remediation action (stop/terminate) is dry-run-by-default so nothing destructive happens without explicit confirmation. Built for students and small teams running on AWS free tier who don't have a dedicated FinOps function, but want the same cost governance discipline larger teams pay for.

## Tech Stack

| Layer         | Technology                              |
|---------------|------------------------------------------|
| Backend API   | Python, FastAPI, boto3                   |
| Scheduled Job | AWS Lambda (Python 3.12), EventBridge    |
| Database      | DynamoDB (on-demand billing)             |
| Frontend      | Next.js 14, React, TypeScript, Tailwind CSS, Recharts |
| Infrastructure| Terraform                                |
| Alerting      | Slack Incoming Webhooks, SNS (backup channel) |
| Cloud         | AWS (Cost Explorer, CloudWatch, EC2, IAM) |

## Features

- Rolling-baseline z-score anomaly detection on daily AWS spend (explainable, not a black box)
- Automatic idle EC2 instance detection via CPU + network utilization heuristics
- Risk classification (low / medium / high) combining statistical significance and dollar impact
- Live dashboard: spend trend chart, anomaly feed, flagged resource table
- Two-step, dry-run-safe remediation (preview → confirm) for stopping/terminating idle instances
- Slack alerts on new anomalies, newly flagged resources, and remediation actions
- Fully defined infrastructure as code (Terraform) — Lambda, DynamoDB, EventBridge, IAM, SNS

## Project Structure

```
cloudleak/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── models.py
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── spend.py
│   │   │   └── resources.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── cost_explorer.py
│   │   │   ├── cloudwatch.py
│   │   │   ├── anomaly.py
│   │   │   ├── idleness.py
│   │   │   └── remediation.py
│   │   └── alerts/
│   │       ├── __init__.py
│   │       └── slack.py
│   ├── requirements.txt
│   └── .env.example
├── lambda/
│   └── collector/
│       ├── handler.py
│       └── requirements.txt
├── infra/
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
│   │   │   ├── page.tsx
│   │   │   └── globals.css
│   │   ├── components/
│   │   │   ├── SpendChart.tsx
│   │   │   ├── AnomalyCard.tsx
│   │   │   ├── ResourceTable.tsx
│   │   │   └── Navbar.tsx
│   │   ├── lib/
│   │   │   └── api.ts
│   │   └── types/
│   │       └── index.ts
│   ├── package.json
│   ├── tsconfig.json
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   ├── next.config.js
│   └── .env.local.example
├── .gitignore
└── README.md
```

## Getting Started

### Prerequisites

- Python 3.11+ (3.12 recommended, matches the Lambda runtime)
- Node.js 18+ and npm
- An AWS account with an IAM user (see credentials section below — never use root keys)
- [Terraform](https://developer.hashicorp.com/terraform/install) 1.5+ (only needed to deploy the Lambda/DynamoDB/EventBridge infra — not required to run the backend/frontend locally against real AWS data, as long as the DynamoDB tables already exist)
- A Slack workspace where you can create an Incoming Webhook (optional — alerts are skipped, not broken, if omitted)

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
# Fill in .env with real values — see credentials guide below
```

**Frontend:**
```powershell
cd frontend
npm install
copy .env.local.example .env.local
```

**Infrastructure (creates the DynamoDB tables, Lambda, EventBridge schedule, IAM role, SNS topic):**
```powershell
cd infra
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

Backend runs at `http://localhost:8000` (docs at `/docs`). Frontend runs at `http://localhost:3000`.

## Environment Variables

### `backend/.env`

| Variable | Description | Where to get it |
|----------|-------------|------------------|
| `AWS_ACCESS_KEY_ID` | IAM user access key | AWS Console → IAM → Users |
| `AWS_SECRET_ACCESS_KEY` | IAM user secret key | Shown once at key creation |
| `AWS_REGION` | Region your resources live in | e.g. `eu-north-1` |
| `DYNAMODB_TABLE_SPEND` | Spend baseline table name | Must match `infra/dynamodb.tf` |
| `DYNAMODB_TABLE_ANOMALIES` | Anomalies table name | Must match `infra/dynamodb.tf` |
| `DYNAMODB_TABLE_RESOURCES` | Flagged resources table name | Must match `infra/dynamodb.tf` |
| `SLACK_WEBHOOK_URL` | Slack Incoming Webhook URL | Slack workspace → Apps → Incoming Webhooks |
| `ANOMALY_ZSCORE_THRESHOLD` | Z-score cutoff for flagging | Tunable, default `2.5` |
| `COST_BASELINE_DAYS` | Rolling baseline window | Tunable, default `7` |
| `IDLE_CPU_THRESHOLD_PERCENT` | CPU % below which idle | Tunable, default `5.0` |
| `IDLE_NETWORK_THRESHOLD_BYTES` | Network bytes below which idle | Tunable, default `1000000` |
| `IDLE_HOURS_THRESHOLD` | Hours of sustained idle before flagging | Tunable, default `6` |
| `CORS_ORIGINS` | Allowed frontend origins | `http://localhost:3000` for local dev |

### `frontend/.env.local`

| Variable | Description |
|----------|-------------|
| `NEXT_PUBLIC_API_BASE_URL` | Backend API URL, e.g. `http://localhost:8000` |

### `infra/terraform.tfvars` (gitignored — create manually)

| Variable | Description |
|----------|-------------|
| `slack_webhook_url` | Same Slack webhook, used by the Lambda collector |
| `alert_email` | Optional backup SNS email subscription |
| `aws_region` | Deployment region |

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

## Contributing

This is a personal portfolio project, but issues and suggestions are welcome via GitHub Issues.

## License

MIT