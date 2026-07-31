# SNS topic as a backup alert channel alongside Slack - useful if the
# webhook URL isn''t configured yet, or as a second channel for high-risk
# alerts. Email subscription requires manual confirmation via the link
# AWS sends after apply.

resource "aws_sns_topic" "alerts" {
  name = "${var.project_name}-alerts"

  tags = {
    Project = var.project_name
  }
}

resource "aws_sns_topic_subscription" "email_alerts" {
  count     = var.alert_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}
