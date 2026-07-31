output "lambda_function_name" {
  description = "Name of the deployed collector Lambda function."
  value       = aws_lambda_function.collector.function_name
}

output "lambda_function_arn" {
  description = "ARN of the deployed collector Lambda function."
  value       = aws_lambda_function.collector.arn
}

output "dynamodb_table_spend" {
  value = aws_dynamodb_table.spend_baseline.name
}

output "dynamodb_table_anomalies" {
  value = aws_dynamodb_table.anomalies.name
}

output "dynamodb_table_resources" {
  value = aws_dynamodb_table.flagged_resources.name
}

output "sns_topic_arn" {
  description = "SNS topic ARN used as a backup alert channel alongside Slack."
  value       = aws_sns_topic.alerts.arn
}

output "eventbridge_rule_name" {
  value = aws_cloudwatch_event_rule.collector_schedule.name
}
