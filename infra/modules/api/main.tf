variable "name_prefix" {
  description = "Prefix for resource names."
  type        = string
}

variable "function_name" {
  description = "Lambda function that serves every route."
  type        = string
}

variable "invoke_arn" {
  description = "Invoke ARN of the Lambda function."
  type        = string
}

variable "throttle_rate" {
  description = "Steady requests per second, across all routes."
  type        = number
  default     = 1
}

variable "throttle_burst" {
  description = "Burst size above the steady rate."
  type        = number
  default     = 2
}

variable "log_retention_days" {
  description = "Days to keep access logs."
  type        = number
  default     = 7
}

resource "aws_apigatewayv2_api" "this" {
  name          = "${var.name_prefix}-api"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.this.id
  integration_type       = "AWS_PROXY"
  integration_uri        = var.invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 29000
}

resource "aws_apigatewayv2_route" "ask" {
  # checkov:skip=CKV_AWS_309:A public demo endpoint. Throttling, a daily request cap and the budget alerts bound what anyone can spend.
  api_id    = aws_apigatewayv2_api.this.id
  route_key = "POST /ask"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_route" "health" {
  # checkov:skip=CKV_AWS_309:Health is public by design and makes no model call.
  api_id    = aws_apigatewayv2_api.this.id
  route_key = "GET /health"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_cloudwatch_log_group" "access" {
  # checkov:skip=CKV_AWS_338:Seven days of logs keep the cost at zero; the README documents it.
  # checkov:skip=CKV_AWS_158:The default CloudWatch encryption is used; a KMS key costs about 1 USD a month.
  name              = "/aws/apigateway/${var.name_prefix}-api"
  retention_in_days = var.log_retention_days
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.this.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_rate_limit  = var.throttle_rate
    throttling_burst_limit = var.throttle_burst
  }

  # No client address: it is personal data and nothing here needs it.
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.access.arn
    format = jsonencode({
      requestId        = "$context.requestId"
      routeKey         = "$context.routeKey"
      status           = "$context.status"
      responseLength   = "$context.responseLength"
      latencyMs        = "$context.responseLatency"
      integrationError = "$context.integrationErrorMessage"
    })
  }
}

resource "aws_lambda_permission" "api" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.this.execution_arn}/*/*"
}

output "api_id" {
  description = "ID of the HTTP API."
  value       = aws_apigatewayv2_api.this.id
}

output "invoke_url" {
  description = "Base URL of the API."
  value       = aws_apigatewayv2_api.this.api_endpoint
}
