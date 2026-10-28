data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  account = data.aws_caller_identity.current.account_id
  region  = data.aws_region.current.region
  repo    = "repo:${var.github_repository}"
  p       = var.name_prefix

  state_bucket_arn = "arn:aws:s3:::${var.state_bucket_name}"
  lambda_role_name = "${var.name_prefix}-ask-role" # the only role the deploy role may touch
}

# GitHub's OIDC issuer. AWS validates its certificate itself, so no thumbprint is pinned here.
resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

data "aws_iam_policy_document" "trust_plan" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # Pull requests inside this repository and pushes to main. Forked PRs get no OIDC token.
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["${local.repo}:pull_request", "${local.repo}:ref:refs/heads/main"]
    }
  }
}

data "aws_iam_policy_document" "trust_deploy" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # Only jobs that run in the protected environment, which needs a human approval.
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["${local.repo}:environment:${var.deploy_environment}"]
    }
  }
}

# --- Plan role: read everything Terraform refreshes, lock state, no data-plane reads ----------

resource "aws_iam_role" "plan" {
  name                 = "${local.p}-ci-plan"
  assume_role_policy   = data.aws_iam_policy_document.trust_plan.json
  max_session_duration = 3600
}

resource "aws_iam_role_policy_attachment" "plan_read" {
  role       = aws_iam_role.plan.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

data "aws_iam_policy_document" "state" {
  statement {
    sid       = "ListState"
    actions   = ["s3:ListBucket"]
    resources = [local.state_bucket_arn]
  }

  statement {
    sid       = "ReadWriteAndLockDevState"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${local.state_bucket_arn}/${var.state_key_prefix}*"]
  }
}

# Both roles get ReadOnlyAccess for Terraform's refresh. That policy also reads data, and the
# bootstrap state (which holds the budget email). Neither is needed, so both are denied.
data "aws_iam_policy_document" "limits" {
  statement {
    sid    = "NoDataPlaneReads"
    effect = "Deny"
    actions = [
      "dynamodb:GetItem", "dynamodb:BatchGetItem", "dynamodb:Query", "dynamodb:Scan",
      "logs:GetLogEvents", "logs:FilterLogEvents", "logs:StartQuery", "logs:GetQueryResults",
      "bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream", "bedrock:ApplyGuardrail",
    ]
    resources = ["*"]
  }

  statement {
    sid       = "NoBootstrapState"
    effect    = "Deny"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${local.state_bucket_arn}/bootstrap/*"]
  }
}

data "aws_iam_policy_document" "plan_extra" {
  source_policy_documents = [
    data.aws_iam_policy_document.state.json,
    data.aws_iam_policy_document.limits.json,
  ]
}

resource "aws_iam_role_policy" "plan_extra" {
  name   = "state-and-limits"
  role   = aws_iam_role.plan.id
  policy = data.aws_iam_policy_document.plan_extra.json
}

# --- Deploy role: plan role's reads plus writes scoped to this project's resources -----------

resource "aws_iam_role" "deploy" {
  name                 = "${local.p}-ci-deploy"
  assume_role_policy   = data.aws_iam_policy_document.trust_deploy.json
  max_session_duration = 3600
}

resource "aws_iam_role_policy_attachment" "deploy_read" {
  role       = aws_iam_role.deploy.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

data "aws_iam_policy_document" "deploy" {
  source_policy_documents = [
    data.aws_iam_policy_document.state.json,
    data.aws_iam_policy_document.limits.json,
  ]

  statement {
    sid     = "DataBucket"
    actions = ["s3:*"]
    resources = [
      "arn:aws:s3:::${local.p}-data-${local.account}",
      "arn:aws:s3:::${local.p}-data-${local.account}/*",
    ]
  }

  statement {
    sid       = "QuotaTable"
    actions   = ["dynamodb:*"]
    resources = ["arn:aws:dynamodb:${local.region}:${local.account}:table/${local.p}-*"]
  }

  statement {
    sid       = "Function"
    actions   = ["lambda:*"]
    resources = ["arn:aws:lambda:${local.region}:${local.account}:function:${local.p}-*"]
  }

  # Only the Lambda's own role, never the CI roles: no way to grant itself more.
  statement {
    sid = "LambdaRole"
    actions = [
      "iam:CreateRole", "iam:DeleteRole", "iam:GetRole", "iam:UpdateRole",
      "iam:UpdateAssumeRolePolicy", "iam:TagRole", "iam:UntagRole",
      "iam:PutRolePolicy", "iam:DeleteRolePolicy", "iam:GetRolePolicy",
      "iam:ListRolePolicies", "iam:ListAttachedRolePolicies", "iam:ListInstanceProfilesForRole",
    ]
    resources = ["arn:aws:iam::${local.account}:role/${local.lambda_role_name}"]
  }

  statement {
    sid       = "PassRoleToLambdaOnly"
    actions   = ["iam:PassRole"]
    resources = ["arn:aws:iam::${local.account}:role/${local.lambda_role_name}"]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["lambda.amazonaws.com"]
    }
  }

  statement {
    sid     = "HttpApi"
    actions = ["apigateway:GET", "apigateway:POST", "apigateway:PUT", "apigateway:PATCH", "apigateway:DELETE", "apigateway:TagResource", "apigateway:UntagResource"]
    resources = [
      "arn:aws:apigateway:${local.region}::/apis",
      "arn:aws:apigateway:${local.region}::/apis/*",
      "arn:aws:apigateway:${local.region}::/tags/*",
    ]
  }

  statement {
    sid = "LogGroups"
    actions = [
      "logs:CreateLogGroup", "logs:DeleteLogGroup", "logs:PutRetentionPolicy",
      "logs:DeleteRetentionPolicy", "logs:TagResource", "logs:UntagResource", "logs:TagLogGroup",
      "logs:UntagLogGroup", "logs:ListTagsForResource", "logs:ListTagsLogGroup",
    ]
    resources = [
      "arn:aws:logs:${local.region}:${local.account}:log-group:/aws/lambda/${local.p}-*",
      "arn:aws:logs:${local.region}:${local.account}:log-group:/aws/apigateway/${local.p}-*",
    ]
  }

  # API Gateway access logs are set up through log deliveries, which have no resource ARN.
  statement {
    sid = "AccessLogDelivery"
    actions = [
      "logs:CreateLogDelivery", "logs:GetLogDelivery", "logs:UpdateLogDelivery",
      "logs:DeleteLogDelivery", "logs:ListLogDeliveries", "logs:PutResourcePolicy",
      "logs:DescribeResourcePolicies", "logs:DescribeLogGroups",
    ]
    resources = ["*"]
  }

  statement {
    sid     = "DashboardAndAlarm"
    actions = ["cloudwatch:PutDashboard", "cloudwatch:DeleteDashboards", "cloudwatch:PutMetricAlarm", "cloudwatch:DeleteAlarms", "cloudwatch:TagResource", "cloudwatch:UntagResource"]
    resources = [
      "arn:aws:cloudwatch::${local.account}:dashboard/${local.p}-*",
      "arn:aws:cloudwatch:${local.region}:${local.account}:alarm:${local.p}-*",
    ]
  }

  statement {
    sid       = "AlertTopic"
    actions   = ["sns:CreateTopic", "sns:DeleteTopic", "sns:SetTopicAttributes", "sns:Subscribe", "sns:Unsubscribe", "sns:TagResource", "sns:UntagResource"]
    resources = ["arn:aws:sns:${local.region}:${local.account}:${local.p}-*"]
  }

  statement {
    sid       = "Guardrail"
    actions   = ["bedrock:CreateGuardrail", "bedrock:UpdateGuardrail", "bedrock:DeleteGuardrail", "bedrock:CreateGuardrailVersion", "bedrock:TagResource", "bedrock:UntagResource"]
    resources = ["arn:aws:bedrock:${local.region}:${local.account}:guardrail/*"]
  }
}

resource "aws_iam_role_policy" "deploy" {
  name   = "deploy-this-project"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy.json
}

output "plan_role_arn" {
  description = "Role for pull request checks: terraform plan."
  value       = aws_iam_role.plan.arn
}

output "deploy_role_arn" {
  description = "Role for the manual deploy workflow: apply and destroy."
  value       = aws_iam_role.deploy.arn
}
