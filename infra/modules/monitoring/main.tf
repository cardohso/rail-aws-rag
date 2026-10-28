variable "name_prefix" {
  description = "Prefix for resource names."
  type        = string
}

variable "alert_email" {
  description = "Address that receives the error alarm."
  type        = string
  sensitive   = true # plans in public CI logs must not print it
}

variable "api_id" {
  description = "ID of the HTTP API."
  type        = string
}

variable "function_name" {
  description = "Name of the Lambda function."
  type        = string
}

variable "log_group_name" {
  description = "Log group of the Lambda function."
  type        = string
}

variable "model_id" {
  description = "Bedrock model or inference profile, as it appears in the AWS/Bedrock metrics."
  type        = string
}

data "aws_region" "current" {}

locals {
  region = data.aws_region.current.region

  # The handler prints one JSON object per request, so Logs Insights reads its fields directly.
  source = "SOURCE '${var.log_group_name}'"

  metric_widget = {
    requests = {
      title  = "API requests"
      period = 300
      stat   = "Sum"
      metrics = [
        ["AWS/ApiGateway", "Count", "ApiId", var.api_id, { label = "requests" }],
        ["AWS/ApiGateway", "4xx", "ApiId", var.api_id, { label = "4xx (bad input, daily cap)" }],
        ["AWS/ApiGateway", "5xx", "ApiId", var.api_id, { label = "5xx (errors)" }],
      ]
    }
    latency = {
      title  = "API latency (ms)"
      period = 300
      stat   = "p95"
      metrics = [
        ["AWS/ApiGateway", "Latency", "ApiId", var.api_id, { stat = "p50", label = "p50" }],
        ["AWS/ApiGateway", "Latency", "ApiId", var.api_id, { stat = "p95", label = "p95" }],
      ]
    }
    lambda = {
      title  = "Lambda duration (ms) and errors"
      period = 300
      stat   = "Average"
      metrics = [
        ["AWS/Lambda", "Duration", "FunctionName", var.function_name, { stat = "p50", label = "duration p50" }],
        ["AWS/Lambda", "Duration", "FunctionName", var.function_name, { stat = "p95", label = "duration p95" }],
        ["AWS/Lambda", "Errors", "FunctionName", var.function_name, { stat = "Sum", label = "errors", yAxis = "right" }],
      ]
    }
    bedrock = {
      title  = "Bedrock tokens"
      period = 300
      stat   = "Sum"
      metrics = [
        ["AWS/Bedrock", "InputTokenCount", "ModelId", var.model_id, { label = "input tokens" }],
        ["AWS/Bedrock", "OutputTokenCount", "ModelId", var.model_id, { label = "output tokens" }],
      ]
    }
  }

  logs_widget = {
    tokens = {
      title = "Tokens per hour (from request logs)"
      view  = "timeSeries"
      query = "${local.source} | filter event = 'ask' | stats sum(input_tokens) as input_tokens, sum(output_tokens) as output_tokens by bin(1h)"
    }
    refusals = {
      title = "Answers and refusals by reason"
      view  = "table"
      query = "${local.source} | filter event = 'ask' | stats count(*) as requests by refusal_reason | sort requests desc"
    }
    guardrail = {
      title = "What the guardrail caught"
      view  = "table"
      query = "${local.source} | filter event = 'ask' and (ispresent(guardrail_findings.input.0) or ispresent(guardrail_findings.output.0)) | fields @timestamp, refusal_reason, guardrail_findings.input.0, guardrail_findings.input.1, guardrail_findings.output.0 | sort @timestamp desc | limit 50"
    }
  }
}

resource "aws_cloudwatch_dashboard" "this" {
  dashboard_name = "${var.name_prefix}-overview"

  dashboard_body = jsonencode({
    widgets = concat(
      [
        for i, key in ["requests", "latency", "lambda", "bedrock"] : {
          type   = "metric"
          x      = (i % 2) * 12
          y      = floor(i / 2) * 6
          width  = 12
          height = 6
          properties = merge(local.metric_widget[key], {
            region = local.region
            view   = "timeSeries"
          })
        }
      ],
      [
        for i, key in ["tokens", "refusals", "guardrail"] : {
          type   = "log"
          x      = (i % 2) * 12
          y      = 12 + floor(i / 2) * 6
          width  = 12
          height = 6
          properties = {
            title  = local.logs_widget[key].title
            view   = local.logs_widget[key].view
            region = local.region
            query  = local.logs_widget[key].query
          }
        }
      ]
    )
  })
}

resource "aws_sns_topic" "alerts" {
  # checkov:skip=CKV_AWS_26:CloudWatch cannot publish to a topic encrypted with the AWS-managed SNS key, and a customer-managed key costs about 1 USD a month.
  name = "${var.name_prefix}-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# The handler answers errors with a 500 instead of raising, so Lambda's own Errors metric would
# stay at zero. API Gateway's 5xx counts them, and the 503 for a busy model too.
resource "aws_cloudwatch_metric_alarm" "errors" {
  alarm_name          = "${var.name_prefix}-5xx"
  alarm_description   = "The API returned a 5xx in the last 5 minutes."
  namespace           = "AWS/ApiGateway"
  metric_name         = "5xx"
  dimensions          = { ApiId = var.api_id }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

output "dashboard_name" {
  description = "Name of the CloudWatch dashboard."
  value       = aws_cloudwatch_dashboard.this.dashboard_name
}
