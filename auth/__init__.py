"""
Authentication module for E-Commerce Crawler.

Provides AWS Cognito authentication services.
"""

from auth.service import (
    CognitoAuthService,
    AuthenticationError,
    NewPasswordRequiredError,
    SessionExpiredError,
    AccessRevokedError,
    InvalidPasswordError,
    get_auth_service,
    get_aws_client,
    get_dynamodb_resource,
)

__all__ = [
    'CognitoAuthService',
    'AuthenticationError',
    'NewPasswordRequiredError',
    'SessionExpiredError',
    'AccessRevokedError',
    'InvalidPasswordError',
    'get_auth_service',
    'get_aws_client',
    'get_dynamodb_resource',
]

