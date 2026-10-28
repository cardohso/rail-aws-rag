data "aws_caller_identity" "current" {}

# The retrieval index (passages, vectors, BM25 terms) that the Lambda loads at cold start.
resource "aws_s3_bucket" "data" {
  # checkov:skip=CKV_AWS_145:SSE-S3 is enough for public EU legal text; a customer-managed KMS key costs about 1 USD a month.
  # checkov:skip=CKV_AWS_144:Cross-region replication is not needed for an index that is rebuilt from the repo.
  # checkov:skip=CKV_AWS_18:Access logging needs a second bucket to hold the logs.
  # checkov:skip=CKV_AWS_21:Index versions live under a hash-named prefix, so object versioning adds nothing.
  # checkov:skip=CKV2_AWS_62:No consumer for event notifications.
  bucket        = "${var.name_prefix}-data-${data.aws_caller_identity.current.account_id}"
  force_destroy = var.force_destroy
}

resource "aws_s3_bucket_ownership_controls" "data" {
  bucket = aws_s3_bucket.data.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "data" {
  bucket = aws_s3_bucket.data.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  bucket = aws_s3_bucket.data.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "data" {
  bucket = aws_s3_bucket.data.id

  rule {
    id     = "abort-incomplete-uploads"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

data "aws_iam_policy_document" "tls_only" {
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.data.arn,
      "${aws_s3_bucket.data.arn}/*",
    ]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "data" {
  bucket = aws_s3_bucket.data.id
  policy = data.aws_iam_policy_document.tls_only.json

  depends_on = [aws_s3_bucket_public_access_block.data]
}
