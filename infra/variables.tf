variable "aws_region" {
  description = "AWS region to deploy CloudLeak resources into (Lambda, DynamoDB, EventBridge, SNS)."
  type        = string
  default     = "eu-north-1"
}

variable "project_name" {
  description = "Prefix used for naming all CloudLeak AWS resources."
  type        = string
  default     = "cloudleak"
}

variable "slack_webhook_url" {
  description = "Slack Incoming Webhook URL for alerts. TODO: paste your webhook URL, or leave blank to disable Slack alerts."
  type        = string
  default     = ""
  sensitive   = true
}

variable "alert_email" {
  description = "Email address subscribed to the SNS alert topic as a backup channel to Slack. TODO: put your email here."
  type        = string
  default     = ""
}

variable "anomaly_zscore_threshold" {
  description = "Z-score threshold above which a day's spend is flagged as anomalous."
  type        = number
  default     = 2.5
}

variable "cost_baseline_days" {
  description = "Number of historical days used to compute the rolling spend baseline."
  type        = number
  default     = 7
}

variable "idle_cpu_threshold_percent" {
  description = "Average CPU utilization (%) below which an EC2 instance is considered idle."
  type        = number
  default     = 5.0
}

variable "idle_network_threshold_bytes" {
  description = "Average network in+out (bytes) below which an EC2 instance is considered idle."
  type        = number
  default     = 1000000
}

variable "idle_hours_threshold" {
  description = "Number of hours of sustained low CPU/network before an instance is flagged as idle."
  type        = number
  default     = 6
}

variable "collector_schedule_expression" {
  description = "EventBridge schedule expression for how often the collector Lambda runs."
  type        = string
  default     = "rate(15 minutes)"
}
