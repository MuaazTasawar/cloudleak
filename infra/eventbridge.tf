resource "aws_cloudwatch_event_rule" "collector_schedule" {
  name                = "${var.project_name}-collector-schedule"
  description         = "Triggers the CloudLeak collector Lambda on a fixed interval."
  schedule_expression = var.collector_schedule_expression
}

resource "aws_cloudwatch_event_target" "collector_target" {
  rule      = aws_cloudwatch_event_rule.collector_schedule.name
  target_id = "${var.project_name}-collector"
  arn       = aws_lambda_function.collector.arn
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.collector.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.collector_schedule.arn
}
