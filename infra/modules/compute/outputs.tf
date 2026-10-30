output "function_name" {
  description = "Name of the Lambda function."
  value       = aws_lambda_function.ask.function_name
}

output "function_arn" {
  description = "ARN of the Lambda function."
  value       = aws_lambda_function.ask.arn
}

output "invoke_arn" {
  description = "Invoke ARN that API Gateway integrates with."
  value       = aws_lambda_function.ask.invoke_arn
}

output "log_group_name" {
  description = "Log group of the Lambda function."
  value       = aws_cloudwatch_log_group.lambda.name
}
