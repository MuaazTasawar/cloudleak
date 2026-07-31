# Packages lambda/collector into a zip at plan/apply time so there''s no
# manual zip-and-upload step - just `terraform apply`.

data "archive_file" "collector_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/collector"
  output_path = "${path.module}/../lambda/collector/build/collector.zip"
  excludes    = ["requirements.txt"]
}

resource "aws_lambda_function" "collector" {
  function_name = "${var.project_name}-collector"
  role          = aws_iam_role.collector_lambda_role.arn
  handler       = "handler.handler"
  runtime       = "python3.12"
  timeout       = 60
  memory_size   = 256

  filename         = data.archive_file.collector_zip.output_path
  source_code_hash = data.archive_file.collector_zip.output_base64sha256

  environment {
    variables = {
      DYNAMODB_TABLE_SPEND         = aws_dynamodb_table.spend_baseline.name
      DYNAMODB_TABLE_ANOMALIES     = aws_dynamodb_table.anomalies.name
      DYNAMODB_TABLE_RESOURCES     = aws_dynamodb_table.flagged_resources.name
      SLACK_WEBHOOK_URL            = var.slack_webhook_url
      ANOMALY_ZSCORE_THRESHOLD     = tostring(var.anomaly_zscore_threshold)
      COST_BASELINE_DAYS           = tostring(var.cost_baseline_days)
      IDLE_CPU_THRESHOLD_PERCENT   = tostring(var.idle_cpu_threshold_percent)
      IDLE_NETWORK_THRESHOLD_BYTES = tostring(var.idle_network_threshold_bytes)
      IDLE_HOURS_THRESHOLD         = tostring(var.idle_hours_threshold)
      SNS_TOPIC_ARN                = aws_sns_topic.alerts.arn
    }
  }

  tags = {
    Project = var.project_name
  }
}

resource "aws_cloudwatch_log_group" "collector_logs" {
  name              = "/aws/lambda/${aws_lambda_function.collector.function_name}"
  retention_in_days = 14
}
