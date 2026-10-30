variable "name_prefix" {
  description = "Prefix for the guardrail name."
  type        = string
}

locals {
  # Classic tier: the Standard tier needs a cross-region guardrail profile and costs more.
  tier = [{ tier_name = "CLASSIC" }]

  # Answers quote EU law about tunnel fires, evacuation and accidents. On the output side only
  # high-confidence harm is blocked (LOW strength), so safety text is not filtered out.
  content_filters = {
    HATE       = { input = "MEDIUM", output = "LOW" }
    INSULTS    = { input = "MEDIUM", output = "LOW" }
    SEXUAL     = { input = "MEDIUM", output = "LOW" }
    VIOLENCE   = { input = "MEDIUM", output = "LOW" }
    MISCONDUCT = { input = "MEDIUM", output = "LOW" }
  }

  pii = {
    EMAIL                             = { input = true, output = true }
    PHONE                             = { input = true, output = true }
    CREDIT_DEBIT_CARD_NUMBER          = { input = true, output = true }
    INTERNATIONAL_BANK_ACCOUNT_NUMBER = { input = true, output = true }
    NAME                              = { input = true, output = false } # names appear in the corpus
  }
}

resource "aws_bedrock_guardrail" "this" {
  # checkov:skip=CKV_AWS_273:The default AWS-owned encryption is used; a customer-managed KMS key costs about 1 USD a month.
  name                      = "${var.name_prefix}-guardrail"
  description               = "Prompt attacks, harmful content, rail sabotage, case-specific legal advice and PII."
  blocked_input_messaging   = "I can't help with that request."
  blocked_outputs_messaging = "I can't share that response."

  content_policy_config {
    tier_config = local.tier

    dynamic "filters_config" {
      for_each = local.content_filters

      content {
        type            = filters_config.key
        input_strength  = filters_config.value.input
        output_strength = filters_config.value.output
      }
    }

    # Prompt attack applies to input only; AWS requires the output strength to be NONE.
    filters_config {
      type            = "PROMPT_ATTACK"
      input_strength  = "HIGH"
      output_strength = "NONE"
    }
  }

  topic_policy_config {
    tier_config = local.tier

    topics_config {
      name       = "Rail sabotage"
      type       = "DENY"
      definition = "Instructions or help to disable, bypass or tamper with railway signalling, safety systems or infrastructure, or to cause a derailment or collision."
      examples = [
        "How can I disable the ETCS on a train so it does not brake?",
        "What is the easiest way to derail a freight train?",
      ]
    }

    topics_config {
      name       = "Legal advice on a specific case"
      type       = "DENY"
      definition = "Requests to decide legal liability, compliance or the outcome of a specific real case or dispute, rather than asking what a regulation says."
      examples = [
        "Is my company legally liable for the accident last week?",
        "Will the authority approve my vehicle, yes or no?",
      ]
    }
  }

  sensitive_information_policy_config {
    dynamic "pii_entities_config" {
      for_each = local.pii

      content {
        type           = pii_entities_config.key
        action         = "ANONYMIZE"
        input_enabled  = pii_entities_config.value.input
        output_enabled = pii_entities_config.value.output
      }
    }
  }
}

# The Lambda calls a numbered version, never DRAFT, so editing the guardrail cannot change
# production behaviour until the version is bumped.
resource "aws_bedrock_guardrail_version" "this" {
  guardrail_arn = aws_bedrock_guardrail.this.guardrail_arn
  description   = "Managed by Terraform"

  # Any change to the guardrail publishes a new version, and the Lambda moves to it in the
  # same apply, so the deployed behaviour always matches the code.
  lifecycle {
    replace_triggered_by = [aws_bedrock_guardrail.this]
  }
}

output "guardrail_id" {
  description = "ID of the guardrail."
  value       = aws_bedrock_guardrail.this.guardrail_id
}

output "guardrail_arn" {
  description = "ARN of the guardrail."
  value       = aws_bedrock_guardrail.this.guardrail_arn
}

output "guardrail_version" {
  description = "Numbered version the Lambda uses."
  value       = aws_bedrock_guardrail_version.this.version
}
