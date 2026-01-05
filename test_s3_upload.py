#!/usr/bin/env python3
"""
Test script to verify S3 upload authentication with Cognito Identity Pool credentials.
"""
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from auth_service import get_auth_service
from image_processor import ImageProcessor
from PIL import Image
import io

def test_s3_authentication():
    """Test S3 authentication and upload."""
    print("=" * 60)
    print("Testing S3 Authentication with Cognito Identity Pool")
    print("=" * 60)
    
    # Check authentication
    auth_service = get_auth_service()
    if not auth_service.is_authenticated():
        print("❌ Not authenticated. Please log in first.")
        print("\nTo test:")
        print("1. Run the application")
        print("2. Log in with username: test, password: Deng0902!")
        print("3. Then run this test script again")
        return False
    
    print(f"✅ Authenticated as: {auth_service.get_username()}")
    
    # Check if we can get credentials
    credentials = auth_service.get_dynamodb_credentials()
    if not credentials:
        print("❌ Failed to get AWS credentials from Cognito Identity Pool")
        return False
    
    print("✅ Got AWS credentials from Cognito Identity Pool")
    print(f"   Access Key ID: {credentials['AccessKeyId'][:10]}...")
    print(f"   Credentials expire at: {credentials.get('Expiration', 'Unknown')}")
    
    # Test S3 client initialization
    print("\n" + "=" * 60)
    print("Testing S3 Client Initialization")
    print("=" * 60)
    
    try:
        from auth_service import get_aws_client
        s3_client = get_aws_client('s3')
        
        if not s3_client:
            print("❌ Failed to create S3 client")
            return False
        
        print("✅ S3 client created successfully")
        
        # Test bucket access
        from image_processor import S3_BUCKET
        print(f"\nTesting access to bucket: {S3_BUCKET}")
        try:
            s3_client.head_bucket(Bucket=S3_BUCKET)
            print(f"✅ Successfully accessed bucket: {S3_BUCKET}")
        except Exception as e:
            error_code = e.response.get('Error', {}).get('Code', '') if hasattr(e, 'response') else ''
            if error_code == '403':
                print(f"❌ Access denied to bucket: {S3_BUCKET}")
                print("   This means the IAM role attached to your Cognito Identity Pool")
                print("   doesn't have S3 permissions for this bucket.")
                print("   Check IAM role permissions.")
            elif error_code == '404':
                print(f"❌ Bucket not found: {S3_BUCKET}")
            else:
                print(f"❌ Error accessing bucket: {e}")
            return False
        
        # Test image processor
        print("\n" + "=" * 60)
        print("Testing Image Processor S3 Upload")
        print("=" * 60)
        
        processor = ImageProcessor(silent_mode=False)
        
        if not processor.s3_client:
            print("❌ Image processor failed to initialize S3 client")
            return False
        
        print("✅ Image processor initialized with S3 client")
        
        # Create a test image
        print("\nCreating test image...")
        test_image = Image.new('RGB', (100, 100), color='red')
        test_key = "test/authentication_test.jpg"
        
        print(f"Uploading test image to: s3://{S3_BUCKET}/{test_key}")
        cloudfront_url = processor.upload_to_s3(test_image, test_key)
        
        if cloudfront_url:
            print(f"✅ Successfully uploaded test image!")
            print(f"   CloudFront URL: {cloudfront_url}")
            
            # Clean up - delete test file
            try:
                s3_client.delete_object(Bucket=S3_BUCKET, Key=test_key)
                print(f"   ✓ Cleaned up test file")
            except Exception as e:
                print(f"   ⚠️  Could not clean up test file: {e}")
            
            return True
        else:
            print("❌ Failed to upload test image")
            return False
            
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_s3_authentication()
    sys.exit(0 if success else 1)

