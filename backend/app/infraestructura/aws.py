"""Los clientes de boto3 que comparten la API y el procesador."""

from __future__ import annotations

import os

import boto3
from botocore.config import Config as BotoConfig


def cliente_s3(region: str):
    # En local, MinIO solo entiende el estilo de ruta (http://minio:9000/<bucket>/<key>).
    local = os.environ.get("AWS_ENDPOINT_URL_S3") or os.environ.get("AWS_ENDPOINT_URL")
    return boto3.client(
        "s3",
        region_name=region,
        config=BotoConfig(connect_timeout=5, read_timeout=15, retries={"max_attempts": 2},
                          signature_version="s3v4",
                          s3={"addressing_style": "path" if local else "auto"}),
    )


def cliente_cognito(region: str):
    """Las llamadas admin al user pool: los grupos de una cuenta al elegir su tipo. Pocas y cortas."""
    return boto3.client("cognito-idp", region_name=region,
                        config=BotoConfig(connect_timeout=5, read_timeout=10, retries={"max_attempts": 2}))


def cliente_sqs(region: str, espera_s: int = 0):
    """`espera_s`: el long polling más largo que se va a pedir; el timeout de lectura lo supera."""
    return boto3.client("sqs", region_name=region,
                        config=BotoConfig(connect_timeout=5, read_timeout=espera_s + 10,
                                          retries={"max_attempts": 3}))
