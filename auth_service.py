"""
AWS Cognito Authentication Service for PySide6 App.

Provides secure authentication using boto3 cognito-idp client.
Tokens are stored securely using the keyring library.
"""

import boto3
from botocore.exceptions import ClientError
from typing import Optional, Dict, Tuple, Any
import keyring
from datetime import datetime, timedelta, timezone

try:
    import config
except ImportError:
    raise ImportError("config.py is required with Cognito settings")


class AuthenticationError(Exception):
    """Custom exception for authentication failures."""
    pass


class NewPasswordRequiredError(Exception):
    """Exception raised when user needs to set a new password."""
    def __init__(self, message: str, session: str, username: str):
        super().__init__(message)
        self.session = session
        self.username = username


class SessionExpiredError(Exception):
    """Exception raised when the session has expired."""
    pass


class AccessRevokedError(Exception):
    """Exception raised when user access has been revoked."""
    pass


class InvalidPasswordError(Exception):
    """Exception raised when password doesn't meet policy requirements."""
    pass


class CognitoAuthService:
    """
    AWS Cognito Authentication Service.
    
    Handles user authentication, session validation, and token refresh.
    """
    
    def __init__(self):
        self.user_pool_id = config.COGNITO_USER_POOL_ID
        self.client_id = config.COGNITO_CLIENT_ID
        self.region = config.COGNITO_REGION
        self.keyring_service = getattr(config, 'KEYRING_SERVICE_NAME', 'EcommCrawler')
        
        # Initialize Cognito client
        self.client = boto3.client(
            'cognito-idp',
            region_name=self.region
        )
        
        # Current tokens (in-memory)
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._id_token: Optional[str] = None
        self._username: Optional[str] = None
        
        # DynamoDB credentials cache (from Cognito Identity Pool)
        self._aws_credentials: Optional[Dict[str, Any]] = None
        self._aws_credentials_expiration: Optional[datetime] = None
    
    def authenticate(self, username: str, password: str) -> Dict[str, str]:
        """
        Authenticate user with username and password.
        
        Args:
            username: The user's username or email
            password: The user's password
            
        Returns:
            Dict containing AccessToken, RefreshToken, IdToken, and ExpiresIn
            
        Raises:
            AuthenticationError: If authentication fails
        """
        try:
            response = self.client.initiate_auth(
                ClientId=self.client_id,
                AuthFlow='USER_PASSWORD_AUTH',
                AuthParameters={
                    'USERNAME': username,
                    'PASSWORD': password
                }
            )
            
            # Check if authentication requires a challenge (e.g., MFA, new password)
            if 'ChallengeName' in response:
                challenge = response['ChallengeName']
                if challenge == 'NEW_PASSWORD_REQUIRED':
                    # Return the session for password change flow
                    session = response.get('Session', '')
                    raise NewPasswordRequiredError(
                        "需要设置新密码",
                        session=session,
                        username=username
                    )
                else:
                    raise AuthenticationError(f"需要额外验证: {challenge}")
            
            # Extract tokens from successful authentication
            auth_result = response.get('AuthenticationResult', {})
            
            self._access_token = auth_result.get('AccessToken')
            self._refresh_token = auth_result.get('RefreshToken')
            self._id_token = auth_result.get('IdToken')
            self._username = username
            
            # Store refresh token securely in keyring
            if self._refresh_token:
                self._store_refresh_token(username, self._refresh_token)
            
            return {
                'AccessToken': self._access_token,
                'RefreshToken': self._refresh_token,
                'IdToken': self._id_token,
                'ExpiresIn': auth_result.get('ExpiresIn', 3600)
            }
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            
            if error_code == 'NotAuthorizedException':
                raise AuthenticationError("用户名或密码错误")
            elif error_code == 'UserNotConfirmedException':
                raise AuthenticationError("用户尚未确认。请检查邮箱。")
            elif error_code == 'UserNotFoundException':
                raise AuthenticationError("用户不存在")
            elif error_code == 'PasswordResetRequiredException':
                raise AuthenticationError("需要重置密码")
            else:
                raise AuthenticationError(f"认证失败: {error_message}")
    
    def complete_password_change(self, username: str, new_password: str, session: str) -> Dict[str, str]:
        """
        Complete the NEW_PASSWORD_REQUIRED challenge by setting a new password.
        
        Args:
            username: The user's username
            new_password: The new password to set
            session: The session string from the initial auth challenge
            
        Returns:
            Dict containing AccessToken, RefreshToken, IdToken, and ExpiresIn
            
        Raises:
            InvalidPasswordError: If the password doesn't meet policy requirements
            AuthenticationError: If the challenge response fails
        """
        try:
            response = self.client.respond_to_auth_challenge(
                ClientId=self.client_id,
                ChallengeName='NEW_PASSWORD_REQUIRED',
                Session=session,
                ChallengeResponses={
                    'USERNAME': username,
                    'NEW_PASSWORD': new_password
                }
            )
            
            # Check if there's another challenge
            if 'ChallengeName' in response:
                raise AuthenticationError(f"需要额外验证: {response['ChallengeName']}")
            
            # Extract tokens from successful password change
            auth_result = response.get('AuthenticationResult', {})
            
            self._access_token = auth_result.get('AccessToken')
            self._refresh_token = auth_result.get('RefreshToken')
            self._id_token = auth_result.get('IdToken')
            self._username = username
            
            # Store refresh token securely in keyring
            if self._refresh_token:
                self._store_refresh_token(username, self._refresh_token)
            
            return {
                'AccessToken': self._access_token,
                'RefreshToken': self._refresh_token,
                'IdToken': self._id_token,
                'ExpiresIn': auth_result.get('ExpiresIn', 3600)
            }
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            
            if error_code == 'InvalidPasswordException':
                # Parse the password policy error message
                raise InvalidPasswordError(f"密码不符合要求: {error_message}")
            elif error_code == 'InvalidParameterException':
                raise InvalidPasswordError(f"密码格式无效: {error_message}")
            elif error_code == 'CodeMismatchException':
                raise AuthenticationError("会话已过期，请重新登录")
            elif error_code == 'ExpiredCodeException':
                raise AuthenticationError("会话已过期，请重新登录")
            else:
                raise AuthenticationError(f"设置密码失败: {error_message}")
    
    def validate_session(self, access_token: Optional[str] = None) -> bool:
        """
        Validate the current session by calling get_user().
        
        Args:
            access_token: Optional access token to validate. Uses stored token if not provided.
            
        Returns:
            True if session is valid, False otherwise
            
        Raises:
            AccessRevokedError: If the user has been disabled/revoked
        """
        token = access_token or self._access_token
        
        if not token:
            return False
        
        try:
            # Call get_user to validate the token
            response = self.client.get_user(AccessToken=token)
            
            # If we get here, the token is valid
            return True
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            
            if error_code == 'NotAuthorizedException':
                # Token is invalid or user is disabled
                # Check if it's specifically because user was disabled
                error_message = e.response.get('Error', {}).get('Message', '').lower()
                if 'disabled' in error_message or 'revoked' in error_message:
                    raise AccessRevokedError("您的访问权限已被撤销")
                # Otherwise, token might just be expired
                return False
            elif error_code == 'UserNotFoundException':
                raise AccessRevokedError("用户已被删除")
            else:
                # Other errors - treat as invalid session
                return False
        except Exception:
            return False
    
    def refresh_tokens(self, refresh_token: Optional[str] = None) -> Dict[str, str]:
        """
        Refresh access tokens using the refresh token.
        
        Args:
            refresh_token: Optional refresh token. Uses stored token if not provided.
            
        Returns:
            Dict containing new AccessToken and IdToken
            
        Raises:
            SessionExpiredError: If refresh token is invalid or expired
            AccessRevokedError: If user access has been revoked
        """
        token = refresh_token or self._refresh_token
        
        if not token:
            # Try to load from keyring
            if self._username:
                token = self._load_refresh_token(self._username)
        
        if not token:
            raise SessionExpiredError("没有可用的刷新令牌。请重新登录。")
        
        try:
            response = self.client.initiate_auth(
                ClientId=self.client_id,
                AuthFlow='REFRESH_TOKEN_AUTH',
                AuthParameters={
                    'REFRESH_TOKEN': token
                }
            )
            
            auth_result = response.get('AuthenticationResult', {})
            
            # Update stored tokens
            self._access_token = auth_result.get('AccessToken')
            self._id_token = auth_result.get('IdToken')
            # Note: Refresh token is not returned on refresh, keep the existing one
            
            return {
                'AccessToken': self._access_token,
                'IdToken': self._id_token,
                'ExpiresIn': auth_result.get('ExpiresIn', 3600)
            }
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            error_message = e.response.get('Error', {}).get('Message', '').lower()
            
            if error_code == 'NotAuthorizedException':
                if 'disabled' in error_message or 'revoked' in error_message:
                    raise AccessRevokedError("您的访问权限已被撤销")
                raise SessionExpiredError("会话已过期。请重新登录。")
            else:
                raise SessionExpiredError(f"刷新令牌失败: {e}")
    
    def logout(self):
        """
        Log out the current user and clear stored tokens.
        """
        # Clear refresh token from keyring
        if self._username:
            self._clear_refresh_token(self._username)
        
        # Clear in-memory tokens
        self._access_token = None
        self._refresh_token = None
        self._id_token = None
        self._username = None
        
        # Clear DynamoDB credentials
        self.clear_dynamodb_credentials()
    
    def get_access_token(self) -> Optional[str]:
        """Get the current access token."""
        return self._access_token
    
    def get_id_token(self) -> Optional[str]:
        """Get the current ID token."""
        return self._id_token
    
    def get_username(self) -> Optional[str]:
        """Get the current username."""
        return self._username
    
    def is_authenticated(self) -> bool:
        """Check if user is currently authenticated."""
        return self._access_token is not None
    
    def try_restore_session(self, username: str) -> bool:
        """
        Try to restore a session using stored refresh token.
        
        Args:
            username: The username to restore session for
            
        Returns:
            True if session was restored successfully
        """
        self._username = username
        refresh_token = self._load_refresh_token(username)
        
        if not refresh_token:
            return False
        
        try:
            self._refresh_token = refresh_token
            self.refresh_tokens()
            return True
        except (SessionExpiredError, AccessRevokedError):
            self._clear_refresh_token(username)
            return False
    
    # --- Private methods for keyring storage ---
    
    def _store_refresh_token(self, username: str, token: str):
        """Store refresh token securely in keyring."""
        try:
            keyring.set_password(self.keyring_service, username, token)
        except Exception as e:
            print(f"Warning: Failed to store token in keyring: {e}")
    
    def _load_refresh_token(self, username: str) -> Optional[str]:
        """Load refresh token from keyring."""
        try:
            return keyring.get_password(self.keyring_service, username)
        except Exception:
            return None
    
    def _clear_refresh_token(self, username: str):
        """Clear refresh token from keyring."""
        try:
            keyring.delete_password(self.keyring_service, username)
        except Exception:
            pass  # Ignore errors when clearing
    
    # --- DynamoDB Credentials (Cognito Identity Pool) ---
    
    def get_dynamodb_credentials(self) -> Optional[Dict[str, Any]]:
        """
        Get temporary AWS credentials for DynamoDB using Cognito Identity Pool.
        
        Uses cached credentials if still valid, otherwise fetches new ones.
        Credentials are cached until expiration (typically 1 hour, but can be up to 12 hours
        depending on Identity Pool configuration).
        
        Returns:
            Dict with 'AccessKeyId', 'SecretAccessKey', 'SessionToken', 'Expiration',
            or None if not authenticated or Identity Pool not configured.
        """
        # Check if Identity Pool is configured
        identity_pool_id = getattr(config, 'COGNITO_IDENTITY_POOL_ID', None)
        if not identity_pool_id:
            return None
        
        # Check if user is authenticated
        id_token = self.get_id_token()
        if not id_token:
            return None
        
        # Check if cached credentials are still valid (with 5 minute buffer)
        now = datetime.now(timezone.utc)
        if (self._aws_credentials and self._aws_credentials_expiration and
            now < self._aws_credentials_expiration - timedelta(minutes=5)):
            return self._aws_credentials
        
        # Get new credentials from Cognito Identity Pool
        try:
            identity_client = boto3.client('cognito-identity', region_name=self.region)
            
            # Get identity ID using the ID token
            login_key = f'cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}'
            identity_response = identity_client.get_id(
                IdentityPoolId=identity_pool_id,
                Logins={login_key: id_token}
            )
            identity_id = identity_response['IdentityId']
            
            # Get credentials for the identity
            credentials_response = identity_client.get_credentials_for_identity(
                IdentityId=identity_id,
                Logins={login_key: id_token}
            )
            
            credentials = credentials_response['Credentials']
            
            # Parse expiration datetime
            expiration = credentials.get('Expiration')
            if expiration:
                if isinstance(expiration, datetime):
                    # Ensure it's timezone-aware
                    if expiration.tzinfo is None:
                        expiration_dt = expiration.replace(tzinfo=timezone.utc)
                    else:
                        expiration_dt = expiration
                else:
                    # If it's a timestamp string or number, try to parse it
                    # AWS returns datetime objects, but handle edge cases
                    expiration_dt = now + timedelta(hours=1)  # Fallback
                self._aws_credentials_expiration = expiration_dt
            else:
                # Default to 1 hour if not provided (though AWS typically provides it)
                self._aws_credentials_expiration = now + timedelta(hours=1)
            
            # Cache credentials
            # Note: AWS Cognito Identity Pool returns 'SecretKey', but we map it to 'SecretAccessKey'
            # for consistency with boto3 parameter names
            self._aws_credentials = {
                'AccessKeyId': credentials['AccessKeyId'],
                'SecretAccessKey': credentials['SecretKey'],
                'SessionToken': credentials['SessionToken'],
                'Expiration': expiration
            }
            
            return self._aws_credentials
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            print(f"Warning: Failed to get AWS credentials from Identity Pool ({error_code}): {error_message}")
            return None
        except Exception as e:
            print(f"Warning: Failed to get AWS credentials: {e}")
            return None
    
    def clear_dynamodb_credentials(self):
        """Clear cached DynamoDB credentials (e.g., on logout)."""
        self._aws_credentials = None
        self._aws_credentials_expiration = None


# Global auth service instance
_auth_service: Optional[CognitoAuthService] = None


def get_auth_service() -> CognitoAuthService:
    """Get the global auth service instance."""
    global _auth_service
    if _auth_service is None:
        _auth_service = CognitoAuthService()
    return _auth_service


def get_aws_client(service_name: str):
    """
    Get an AWS service client using Cognito Identity Pool credentials.
    
    If the user is authenticated via Cognito, uses temporary credentials from
    Cognito Identity Pool. Otherwise, falls back to default credential chain.
    
    Args:
        service_name: AWS service name (e.g., 's3', 'dynamodb', 'sts')
    
    Returns:
        boto3 client for the specified service, or None if boto3 is not available
    """
    try:
        import boto3
    except ImportError:
        return None
    
    auth_service = get_auth_service()
    credentials = auth_service.get_dynamodb_credentials()
    
    if credentials:
        # Use temporary credentials from Cognito Identity Pool
        try:
            return boto3.client(
                service_name,
                region_name=config.AWS_REGION,
                aws_access_key_id=credentials['AccessKeyId'],
                aws_secret_access_key=credentials['SecretAccessKey'],
                aws_session_token=credentials['SessionToken']
            )
        except Exception as e:
            print(f"Warning: Failed to create {service_name} client with Identity Pool credentials: {e}")
            # Fall back to default credential chain
            pass
    
    # Fall back to default credential chain (environment variables, ~/.aws/credentials, IAM roles, etc.)
    try:
        return boto3.client(service_name, region_name=config.AWS_REGION)
    except Exception as e:
        print(f"Warning: Failed to create {service_name} client: {e}")
        return None


def get_dynamodb_resource():
    """
    Get a DynamoDB resource using Cognito Identity Pool credentials.
    
    If the user is authenticated via Cognito, uses temporary credentials from
    Cognito Identity Pool. Otherwise, falls back to default credential chain.
    
    Returns:
        boto3 DynamoDB resource, or None if boto3 is not available
    """
    try:
        import boto3
    except ImportError:
        return None
    
    auth_service = get_auth_service()
    credentials = auth_service.get_dynamodb_credentials()
    
    if credentials:
        # Use temporary credentials from Cognito Identity Pool
        try:
            return boto3.resource(
                'dynamodb',
                region_name=config.AWS_REGION,
                aws_access_key_id=credentials['AccessKeyId'],
                aws_secret_access_key=credentials['SecretAccessKey'],
                aws_session_token=credentials['SessionToken']
            )
        except Exception as e:
            print(f"Warning: Failed to create DynamoDB resource with Identity Pool credentials: {e}")
            # Fall back to default credential chain
            pass
    
    # Fall back to default credential chain (environment variables, ~/.aws/credentials, IAM roles, etc.)
    try:
        return boto3.resource('dynamodb', region_name=config.AWS_REGION)
    except Exception as e:
        print(f"Warning: Failed to create DynamoDB resource: {e}")
        return None

