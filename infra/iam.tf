# IAM role and policy for the collector Lambda. Scoped as tightly as
# reasonably possible: read-only on Cost Explorer/CloudWatch/EC2 describe,
# write-only on the three DynamoDB tables this project owns, and standard
# Lambda logging permissions. No StopInstances/TerminateInstances here -
# the scheduled collector only detects and flags; destructive remediation
# only ever happens through the backend API, triggered by an explicit
# human action from the dashboard.

data "aws_caller_identity" "current" {}

resource "aws_iam_role" "collector_lambda_role" {
  name = "${var.project_name}-collector-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "collector_lambda_policy" {
  name = "${var.project_name}-collector-lambda-policy"
  role = aws_iam_role.collector_lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "CostExplorerReadOnly"
        Effect = "Allow"
        Action = [
          "ce:GetCostAndUsage"
        ]
        Resource = "*"
      },
      {
        Sid    = "CloudWatchReadOnly"
        Effect = "Allow"
        Action = [
          "cloudwatch:GetMetricStatistics"
        ]
        Resource = "*"
      },
      {
        Sid    = "EC2DescribeOnly"
        Effect = "Allow"
        Action = [
          "ec2:DescribeInstances"
        ]
        Resource = "*"
      },
      {
        Sid    = "DynamoDBReadWrite"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:Scan",
          "dynamodb:Query"
        ]
        Resource = [
          aws_dynamodb_table.spend_baseline.arn,
          aws_dynamodb_table.anomalies.arn,
          aws_dynamodb_table.flagged_resources.arn
        ]
      },
      {
        Sid    = "SNSPublish"
        Effect = "Allow"
        Action = [
          "sns:Publish"
        ]
        Resource = aws_sns_topic.alerts.arn
      },
      {
        Sid    = "LambdaLogging"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*"
      }
    ]
  })
}
