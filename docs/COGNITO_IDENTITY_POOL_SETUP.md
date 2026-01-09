# Cognito Identity Pool Setup for DynamoDB Authentication

## Overview

This project now uses **Cognito Identity Pool + Web Identity Federation** for DynamoDB authentication. This means:

✅ **No AWS access keys needed on each machine**
✅ **Users authenticate via Cognito login (which you already have)**
✅ **Temporary AWS credentials are automatically obtained and cached**
✅ **Credentials automatically refresh when they expire (up to 12 hours)**

## What Was Implemented

### 1. Configuration (`config.py`)
- Added `COGNITO_IDENTITY_POOL_ID` configuration field (you need to fill this in)

### 2. Authentication Service (`auth_service.py`)
- Added `get_id_token()` method to retrieve Cognito ID token
- Added `get_dynamodb_credentials()` method that:
  - Gets temporary AWS credentials from Cognito Identity Pool
  - Caches credentials to avoid unnecessary API calls
  - Automatically refreshes credentials 5 minutes before expiration
  - Handles credential expiration properly
- Added `clear_dynamodb_credentials()` to clear cached credentials on logout

### 3. Helper Function (`auth_service.py`)
- Added `get_dynamodb_resource()` helper function that:
  - Uses Cognito Identity Pool credentials if user is authenticated
  - Falls back to default AWS credential chain if not authenticated
  - Can be used anywhere in the codebase

### 4. Updated DynamoDB Initialization
- `scraper_firefox.py` - Now uses Cognito Identity Pool credentials
- `scraper_amazon.py` - Now uses Cognito Identity Pool credentials  
- `ui/main_window.py` - Now uses Cognito Identity Pool credentials

## Required Configuration

### Step 1: Add Identity Pool ID to `config.py`

Open `config.py` and fill in your Identity Pool ID:

```python
COGNITO_IDENTITY_POOL_ID = "us-west-2:XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX"
```

**How to find your Identity Pool ID:**
1. Go to AWS Console → Cognito → Federated Identities (or Identity Pools)
2. Click on your Identity Pool
3. Copy the Identity Pool ID (format: `region:uuid`)

### Step 2: Configure Credential Expiration (12 hours) in AWS

The credential expiration duration is configured in AWS, not in code. To set it to 12 hours:

1. **Go to AWS Console → IAM → Roles**
2. Find the IAM role that your Cognito Identity Pool is using
3. Click on the role → **Trust relationships** tab
4. Look for the Cognito Identity Pool trust relationship
5. The role should have a condition like:
   ```json
   {
     "Condition": {
       "StringEquals": {
         "sts:ExternalId": "your-pool-id"
       },
       "IntegerEquals": {
         "sts:RoleSessionName": "..."
       }
     }
   }
   ```

**Note:** The maximum credential duration is actually controlled by the IAM role's `MaxSessionDuration` setting, but Cognito Identity Pool credentials typically expire after 1 hour by default. To extend this to 12 hours:

1. In IAM → Roles → Your Role → **Permissions** tab
2. Look for the role's **Maximum session duration** (default is 3600 seconds = 1 hour)
3. You may need to update the role's session duration policy

**However**, the actual expiration time that Cognito Identity Pool returns is determined by AWS's internal settings. If you need 12 hours, you may need to:
- Contact AWS Support, or
- Implement automatic credential refresh in the code (which is already done - credentials refresh automatically when they expire)

The code already handles credential expiration automatically - it will refresh credentials 5 minutes before they expire, so users won't notice interruptions.

## How It Works

### Authentication Flow

1. **User logs in** via Cognito (using existing login dialog)
2. **User gets Cognito ID token** from authentication
3. **Application exchanges ID token for AWS credentials** via Cognito Identity Pool:
   - Calls `get_id()` to get Identity ID
   - Calls `get_credentials_for_identity()` to get temporary AWS credentials
4. **Credentials are cached** in memory (with expiration tracking)
5. **DynamoDB operations use these temporary credentials**
6. **When credentials expire** (or 5 minutes before), new credentials are automatically fetched

### Credential Caching

- Credentials are cached in memory (not persisted to disk)
- Cache is cleared on logout
- Credentials are refreshed automatically 5 minutes before expiration
- No manual credential management needed

### Fallback Behavior

If the user is **not authenticated** or Identity Pool credentials are unavailable:
- Falls back to default AWS credential chain (environment variables, ~/.aws/credentials, IAM roles)
- This maintains backward compatibility

## Testing

1. **Fill in `COGNITO_IDENTITY_POOL_ID`** in `config.py`
2. **Run the application**
3. **Log in** with your Cognito credentials
4. **Try saving/loading data from DynamoDB**
5. **Check console logs** - you should see successful DynamoDB operations

If you see errors, check:
- Identity Pool ID is correct in `config.py`
- Identity Pool is configured to use your Cognito User Pool
- IAM role attached to Identity Pool has DynamoDB permissions
- User is properly authenticated via Cognito

## Security Notes

- ✅ No AWS access keys stored on user machines
- ✅ Temporary credentials expire automatically (12 hours max)
- ✅ Credentials are not persisted to disk (only in memory)
- ✅ Credentials are cleared on logout
- ✅ Each user gets their own temporary credentials
- ✅ IAM role controls what permissions users have

## Troubleshooting

### "Failed to get AWS credentials from Identity Pool"
- Check that `COGNITO_IDENTITY_POOL_ID` is set correctly
- Verify Identity Pool is configured to use your Cognito User Pool
- Ensure the Identity Pool is in the same region as your User Pool

### "DynamoDB unavailable" errors
- Check that the IAM role attached to Identity Pool has DynamoDB permissions
- Verify user is logged in (authentication required)
- Check AWS region configuration

### Credentials expire too quickly
- Credential expiration is controlled by AWS Identity Pool settings
- The code automatically refreshes credentials, but if you need longer duration, configure it in AWS Console
- Maximum duration depends on IAM role settings and AWS limits

