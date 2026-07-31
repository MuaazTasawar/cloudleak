# Three tables, all on-demand (PAY_PER_REQUEST) billing so there''s no
# provisioned capacity to forget about - fitting, for a cost-optimization
# tool, to not itself become a forgotten cost.

resource "aws_dynamodb_table" "spend_baseline" {
  name         = "${var.project_name}-spend-baseline"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "date"

  attribute {
    name = "date"
    type = "S"
  }

  tags = {
    Project = var.project_name
  }
}

resource "aws_dynamodb_table" "anomalies" {
  name         = "${var.project_name}-anomalies"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute {
    name = "id"
    type = "S"
  }

  tags = {
    Project = var.project_name
  }
}

resource "aws_dynamodb_table" "flagged_resources" {
  name         = "${var.project_name}-flagged-resources"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute {
    name = "id"
    type = "S"
  }

  tags = {
    Project = var.project_name
  }
}
