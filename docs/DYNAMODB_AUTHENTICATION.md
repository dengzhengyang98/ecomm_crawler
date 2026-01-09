# DynamoDB Authentication Guide

## How Authentication Works

This project uses **boto3's default credential chain** to authenticate with AWS DynamoDB. The code does **NOT** hardcode AWS credentials anywhere.

### Authentication Mechanism

When the code creates a DynamoDB resource:

```python
dynamodb = boto3.resource('dynamodb', region_name=config.AWS_REGION)
table = dynamodb.Table(config.DYNAMODB_TABLE)
```

boto3 automatically searches for credentials in the following order:

1. **Environment Variables**
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
   - `AWS_SESSION_TOKEN` (if using temporary credentials)

2. **AWS Credentials File** (`~/.aws/credentials`)
   ```ini
   [default]12
   aws_access_key_id = YOUR_ACCESS_KEY
   aws_secret_access_key = YOUR_SECRET_KEY
   ```

3. **AWS Config File** (`~/.aws/config`)
   ```ini
   [default]
   region = us-west-2
   ```

4. **IAM Roles** (if running on EC2/ECS/Lambda)

5. **Other credential sources** (container credentials, etc.)

### Code Location

The DynamoDB client initialization can be found in:

- `scraper_firefox.py` (line 289)
- `scraper_amazon.py` (line 160)
- `ui/main_window.py` (line 515)

All use the same pattern:
```python
dynamodb = boto3.resource('dynamodb', region_name=config.AWS_REGION)
```

### Error Handling

The code gracefully handles missing credentials by catching `NoCredentialsError`:

```python
except (BotoCoreError, NoCredentialsError) as exc:
    return None, f"DynamoDB unavailable ({exc})."
```

If credentials are missing, the application will run in **local-only mode** (data saved to local cache only, not DynamoDB).

## Will It Work on Another Laptop?

**Short answer: Only if AWS credentials are configured on that laptop.**

### Requirements for Another Laptop

To use DynamoDB functionality on a different laptop, you need to:

1. **Install AWS CLI** (recommended):
   ```bash
   pip install awscli
   ```

2. **Configure AWS credentials** using one of these methods:

   **Option A: Using AWS CLI (Recommended)**
   ```bash
   aws configure
   ```
   This will prompt for:
   - AWS Access Key ID
   - AWS Secret Access Key
   - Default region (use: `us-west-2`)
   - Default output format (can leave as default)

   **Option B: Environment Variables**
   ```bash
   export AWS_ACCESS_KEY_ID=your_access_key
   export AWS_SECRET_ACCESS_KEY=your_secret_key
   export AWS_DEFAULT_REGION=us-west-2
   ```

   **Option C: Manual Credentials File**
   Create `~/.aws/credentials`:
   ```ini
   [default]
   aws_access_key_id = YOUR_ACCESS_KEY
   aws_secret_access_key = YOUR_SECRET_KEY
   ```
   
   Create `~/.aws/config`:
   ```ini
   [default]
   region = us-west-2
   ```

3. **Ensure IAM permissions**: The credentials must have permissions to:
   - `dynamodb:PutItem`
   - `dynamodb:GetItem`
   - `dynamodb:UpdateItem`
   - `dynamodb:DeleteItem`
   - `dynamodb:Query`
   - `dynamodb:Scan`

### What Happens Without Credentials?

If credentials are **not configured**, the application will:
- ✅ Still run and function normally
- ✅ Save data locally to the `cache/products/` directory
- ❌ **NOT** save/load data from DynamoDB
- ⚠️ Show warnings like: `"⚠️ Warning: DynamoDB connection failed. Running in local-only mode."`

### Testing Credentials

You can verify your AWS credentials are working by running:

```bash
aws dynamodb list-tables --region us-west-2
```

If this works, the application should be able to connect to DynamoDB.

## Security Notes

1. **Never commit credentials** to version control
2. **Never hardcode credentials** in `config.py` or source code
3. Use **IAM roles** when running on AWS infrastructure (EC2, ECS, Lambda)
4. Use **temporary credentials** (STS) for better security
5. Regularly **rotate access keys**
6. Use **least privilege** IAM policies (only grant necessary DynamoDB permissions)

## Configuration Files

The `config.py` file contains:
- ✅ `AWS_REGION = "us-west-2"` (public, safe to commit)
- ✅ `DYNAMODB_TABLE = "AliExpressProducts"` (public, safe to commit)
- ❌ **NO credentials** (correctly excluded)

## Troubleshooting

### "NoCredentialsError" or "Unable to locate credentials"

**Solution**: Configure AWS credentials using one of the methods above.

### "AccessDeniedException" or permission errors

**Solution**: Ensure the IAM user/role has the required DynamoDB permissions.

### "ResourceNotFoundException"

**Solution**: Verify the table name in `config.py` matches your actual DynamoDB table name.

### Works on one laptop but not another

**Solution**: The credentials are machine-specific. You need to configure them on each machine where you want to use DynamoDB.

