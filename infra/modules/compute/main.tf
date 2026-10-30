data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  function_name = "${var.name_prefix}-ask"
  zip_hash      = filebase64sha256(var.lambda_zip_path)

  # Cross-region inference: IAM needs the inference profile and the foundation model in each
  # EU region the profile may route to.
  base_model_id         = trimprefix(var.model_id, "eu.")
  inference_profile_arn = "arn:aws:bedrock:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:inference-profile/${var.model_id}"
  foundation_model_arn  = "arn:aws:bedrock:eu-*::foundation-model/${local.base_model_id}"
}

# The package lives in the data bucket: direct uploads are capped at 50 MB, S3 deploys at 250 MB.
resource "aws_s3_object" "package" {
  bucket = var.data_bucket_name
  key    = "lambda/${substr(sha256(local.zip_hash), 0, 12)}.zip"
  source = var.lambda_zip_path
  # Not `etag`: a 113 MB upload is multipart, and its ETag never equals the file's MD5,
  # which would re-upload the zip on every apply.
  source_hash = filemd5(var.lambda_zip_path)
}

resource "aws_cloudwatch_log_group" "lambda" {
  # checkov:skip=CKV_AWS_338:Seven days of logs keep the cost at zero; the README documents it.
  # checkov:skip=CKV_AWS_158:The default CloudWatch encryption is used; a KMS key costs about 1 USD a month.
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = var.log_retention_days
}

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${local.function_name}-role"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

data "aws_iam_policy_document" "permissions" {
  statement {
    sid       = "WriteOwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.lambda.arn}:*"]
  }

  statement {
    sid       = "ReadTheIndex"
    actions   = ["s3:GetObject"]
    resources = ["${var.data_bucket_arn}/${trimsuffix(var.index_prefix, "/")}/*"]
  }

  statement {
    sid       = "InvokeThroughTheProfile"
    actions   = ["bedrock:InvokeModel"]
    resources = [local.inference_profile_arn]
  }

  # The foundation model in each EU region, but only when the call comes through the profile.
  statement {
    sid       = "ModelOnlyViaTheProfile"
    actions   = ["bedrock:InvokeModel"]
    resources = [local.foundation_model_arn]

    condition {
      test     = "StringLike"
      variable = "bedrock:InferenceProfileArn"
      values   = [local.inference_profile_arn]
    }
  }

  statement {
    sid       = "ApplyTheGuardrail"
    actions   = ["bedrock:ApplyGuardrail"]
    resources = [var.guardrail_arn]
  }

  statement {
    sid       = "CountRequests"
    actions   = ["dynamodb:UpdateItem"]
    resources = [var.quota_table_arn]
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "permissions"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.permissions.json
}

resource "aws_lambda_function" "ask" {
  # checkov:skip=CKV_AWS_50:X-Ray tracing adds cost and a second place to look; CloudWatch has the measurements.
  # checkov:skip=CKV_AWS_115:Reserved concurrency cannot be set: the account limit is 10 and AWS keeps 10 unreserved. API throttling and the daily cap bound the load instead.
  # checkov:skip=CKV_AWS_116:Requests are synchronous behind API Gateway; a dead-letter queue applies to async invokes.
  # checkov:skip=CKV_AWS_117:A VPC needs a NAT gateway to reach Bedrock, which costs about 30 USD a month.
  # checkov:skip=CKV_AWS_173:Environment variables hold names and limits, no secrets, so the default encryption is enough.
  # checkov:skip=CKV_AWS_272:Code signing needs a signing profile and a pipeline this project does not have.
  function_name = local.function_name
  role          = aws_iam_role.lambda.arn
  runtime       = "python3.12"
  architectures = ["arm64"]
  handler       = "rail_aws_rag.handler.handler"
  memory_size   = var.memory_mb
  timeout       = var.timeout_seconds

  s3_bucket        = aws_s3_object.package.bucket
  s3_key           = aws_s3_object.package.key
  source_code_hash = local.zip_hash

  reserved_concurrent_executions = var.reserved_concurrency

  environment {
    variables = {
      INDEX_BUCKET         = var.data_bucket_name
      INDEX_PREFIX         = var.index_prefix
      MODEL_ID             = var.model_id
      GUARDRAIL_ID         = var.guardrail_id
      GUARDRAIL_VERSION    = var.guardrail_version
      TABLE_NAME           = var.quota_table_name
      DAILY_LIMIT          = tostring(var.daily_limit)
      FASTEMBED_CACHE_PATH = "/var/task/models"
      HF_HUB_OFFLINE       = "1"
    }
  }

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.lambda.name
  }

  depends_on = [aws_iam_role_policy.lambda]
}
