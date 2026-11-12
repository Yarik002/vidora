#!/bin/sh
# One-shot MinIO bootstrap: private buckets and a least-privilege user for the app.
# Root credentials are used only here; api and worker get the restricted user.
set -eu

# The Bitnami image restarts MinIO once during its first boot, so retry for a while.
i=0
until mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null 2>&1; do
  i=$((i + 1))
  [ "$i" -ge 30 ] && { echo "minio-init: MinIO is not reachable" >&2; exit 1; }
  sleep 2
done

for bucket in "$BUCKET_RAW" "$BUCKET_MEDIA"; do
  mc mb --ignore-existing "local/$bucket" >/dev/null
  mc anonymous set none "local/$bucket" >/dev/null
done


cat > /tmp/vidora-app-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject",
                 "s3:AbortMultipartUpload", "s3:ListMultipartUploadParts"],
      "Resource": ["arn:aws:s3:::$BUCKET_RAW/*", "arn:aws:s3:::$BUCKET_MEDIA/*"]
    },
    {
      "Effect": "Allow",
      "Action": ["s3:ListBucket", "s3:ListBucketMultipartUploads"],
      "Resource": ["arn:aws:s3:::$BUCKET_RAW", "arn:aws:s3:::$BUCKET_MEDIA"]
    }
  ]
}
EOF

mc admin user add local "$S3_ACCESS_KEY" "$S3_SECRET_KEY" >/dev/null
mc admin policy create local vidora-app /tmp/vidora-app-policy.json >/dev/null 2>&1 || true
mc admin policy attach local vidora-app --user "$S3_ACCESS_KEY" >/dev/null 2>&1 || true
echo "minio-init: buckets and app user are ready"
