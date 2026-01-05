"""Image Processing Module for E-Commerce Crawler.

This module handles:
- Resizing and padding images to 1600x1600
- Background removal using rembg
- Uploading processed images to S3
- Returning CloudFront CDN URLs
"""
import os
import io
import uuid
import hashlib
from typing import List, Dict, Optional, Tuple
from PIL import Image
import boto3
from botocore.exceptions import ClientError

# Try to import rembg for background removal
# Note: rembg has complex dependencies (numba/llvmlite) that may fail to install on some systems
# Background removal will be skipped if not available
REMBG_AVAILABLE = False
try:
    from rembg import remove as remove_background
    REMBG_AVAILABLE = True
    print("✅ rembg is available for background removal")
except ImportError as e:
    print(f"⚠️ rembg not available ({e}). Background removal will be skipped.")
    print("   To enable: pip install rembg (requires LLVM 20)")
except Exception as e:
    print(f"⚠️ rembg import error ({e}). Background removal will be skipped.")

# Configuration
try:
    import config
    AWS_REGION = getattr(config, 'AWS_REGION', 'us-west-2')
except ImportError:
    AWS_REGION = 'us-west-2'

# S3 and CloudFront configuration
S3_BUCKET = "test-image-bucket-1839fks"
CLOUDFRONT_DOMAIN = "d1in9ft2a0tkm0.cloudfront.net"
TARGET_SIZE = (1600, 1600)


class ImageProcessor:
    """Processes images for e-commerce listings."""
    
    def __init__(self, silent_mode: bool = False):
        """Initialize the image processor.
        
        Args:
            silent_mode: If True, suppress most output messages.
        """
        self.silent_mode = silent_mode
        self.s3_client = None
        self._init_s3()
    
    def _init_s3(self):
        """Initialize S3 client using Cognito Identity Pool credentials if available."""
        try:
            # Try to use Cognito Identity Pool credentials if authenticated
            from auth_service import get_aws_client
            self.s3_client = get_aws_client('s3')
            
            if not self.s3_client:
                # Fallback to default credential chain
                self.s3_client = boto3.client('s3', region_name=AWS_REGION)
            
            # Test connection
            self.s3_client.head_bucket(Bucket=S3_BUCKET)
            if not self.silent_mode:
                print(f"✅ S3 connected to bucket: {S3_BUCKET}")
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code == '404':
                print(f"❌ S3 bucket not found: {S3_BUCKET}")
            elif error_code == '403':
                print(f"❌ S3 access denied to bucket: {S3_BUCKET} (check IAM role permissions)")
            else:
                print(f"❌ S3 error: {e}")
            self.s3_client = None
        except Exception as e:
            print(f"❌ Failed to initialize S3: {e}")
            self.s3_client = None
    
    def _log(self, message: str):
        """Print message if not in silent mode."""
        if not self.silent_mode:
            print(message)
    
    def resize_and_pad(self, img: Image.Image, target_size: Tuple[int, int] = TARGET_SIZE, 
                        padding_percent: float = 0.05) -> Image.Image:
        """Resize image to fit within target size with padding and pad to exact dimensions.
        
        The image is resized to fill the usable area (after 5% padding on each side),
        then centered on the final canvas.
        
        Args:
            img: PIL Image to process.
            target_size: Target dimensions (width, height).
            padding_percent: Padding as a percentage of target size (default 5% = 0.05).
            
        Returns:
            Processed PIL Image with exact target dimensions.
        """
        target_w, target_h = target_size
        
        # Calculate the usable area after padding (5% on each side = 10% total reduction)
        padding_w = int(target_w * padding_percent)
        padding_h = int(target_h * padding_percent)
        usable_w = target_w - (2 * padding_w)
        usable_h = target_h - (2 * padding_h)
        
        # Convert to RGBA if not already (to handle transparency)
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        
        # Calculate scaling factor to fit within usable area
        orig_w, orig_h = img.size
        scale = min(usable_w / orig_w, usable_h / orig_h)
        
        # Always resize to fill the usable area (scale up or down as needed)
        new_w = int(orig_w * scale)
        new_h = int(orig_h * scale)
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        # Create white background canvas
        canvas = Image.new('RGBA', target_size, (255, 255, 255, 255))
        
        # Calculate position to center the image
        x = (target_w - new_w) // 2
        y = (target_h - new_h) // 2
        
        # Paste image onto canvas
        canvas.paste(img, (x, y), img if img.mode == 'RGBA' else None)
        
        # Convert to RGB for JPEG output
        return canvas.convert('RGB')
    
    def remove_bg(self, img: Image.Image) -> Image.Image:
        """Remove background from image using rembg.
        
        Args:
            img: PIL Image to process.
            
        Returns:
            PIL Image with background removed (RGBA with transparency).
        """
        if not REMBG_AVAILABLE:
            return img
        
        try:
            # Convert to bytes for rembg
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='PNG')
            img_bytes.seek(0)
            
            # Remove background
            output_bytes = remove_background(img_bytes.getvalue())
            
            # Convert back to PIL Image
            result = Image.open(io.BytesIO(output_bytes))
            return result
        except Exception as e:
            self._log(f"   [!] Background removal failed: {e}")
            return img
    
    def process_image(self, image_path_or_url: str, remove_background: bool = True) -> Optional[Image.Image]:
        """Process a single image: load, remove background, resize and pad.
        
        Args:
            image_path_or_url: Local path or URL to the image.
            remove_background: Whether to attempt background removal.
            
        Returns:
            Processed PIL Image, or None if processing failed.
        """
        try:
            # Load image
            if image_path_or_url.startswith(('http://', 'https://')):
                import requests
                response = requests.get(image_path_or_url, timeout=30, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0"
                })
                if response.status_code != 200:
                    self._log(f"   [!] Failed to download image: {response.status_code}")
                    return None
                img = Image.open(io.BytesIO(response.content))
            else:
                if not os.path.exists(image_path_or_url):
                    self._log(f"   [!] Image not found: {image_path_or_url}")
                    return None
                img = Image.open(image_path_or_url)
            
            # Remove background if requested and available
            if remove_background and REMBG_AVAILABLE:
                img = self.remove_bg(img)
            
            # Resize and pad
            img = self.resize_and_pad(img)
            
            return img
        except Exception as e:
            self._log(f"   [!] Image processing error: {e}")
            return None
    
    def upload_to_s3(self, img: Image.Image, key: str) -> Optional[str]:
        """Upload processed image to S3 and return CloudFront URL.
        
        Args:
            img: PIL Image to upload.
            key: S3 object key (path within bucket).
            
        Returns:
            CloudFront URL of the uploaded image, or None if upload failed.
        """
        if not self.s3_client:
            self._log("   [!] S3 client not available")
            return None
        
        try:
            # Convert image to bytes
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='JPEG', quality=90)
            img_bytes.seek(0)
            
            # Upload to S3
            self.s3_client.upload_fileobj(
                img_bytes,
                S3_BUCKET,
                key,
                ExtraArgs={
                    'ContentType': 'image/jpeg',
                    'CacheControl': 'max-age=31536000'  # 1 year cache
                }
            )
            
            # Return CloudFront URL
            cloudfront_url = f"https://{CLOUDFRONT_DOMAIN}/{key}"
            return cloudfront_url
        except Exception as e:
            self._log(f"   [!] S3 upload error: {e}")
            return None
    
    def process_and_upload(self, image_path_or_url: str, product_id: str, 
                           image_type: str, index: int,
                           remove_bg: bool = True) -> Optional[str]:
        """Process an image and upload to S3.
        
        Args:
            image_path_or_url: Local path or URL to the image.
            product_id: Product ID for organizing in S3.
            image_type: Type of image ('gallery', 'description', 'sku').
            index: Index of the image in its category.
            remove_bg: Whether to remove background.
            
        Returns:
            CloudFront URL of the processed image, or None if failed.
        """
        # Process image
        processed = self.process_image(image_path_or_url, remove_background=remove_bg)
        if processed is None:
            return None
        
        # Generate S3 key
        # Use hash of original URL/path for uniqueness
        url_hash = hashlib.md5(image_path_or_url.encode()).hexdigest()[:8]
        key = f"products/{product_id}/{image_type}/{image_type}_{index}_{url_hash}.jpg"
        
        # Upload and return URL
        return self.upload_to_s3(processed, key)
    
    def process_product_images(self, product_data: Dict, 
                               remove_bg_gallery: bool = True,
                               remove_bg_description: bool = False) -> Dict:
        """Process all images for a product and add recommended URLs.
        
        Args:
            product_data: Product data dictionary containing image URLs.
            remove_bg_gallery: Whether to remove background from gallery images.
            remove_bg_description: Whether to remove background from description images.
            
        Returns:
            Updated product data with *_recommended fields added.
        """
        product_id = product_data.get('product_id', str(uuid.uuid4()))
        
        self._log(f"\n📸 Processing images for product: {product_id}")
        
        # Process gallery images
        gallery_recommended = []
        gallery_sources = product_data.get('gallery_images_remote', product_data.get('gallery_images', []))
        
        if gallery_sources:
            self._log(f"   Processing {len(gallery_sources)} gallery images...")
            for idx, img_url in enumerate(gallery_sources):
                if not img_url:
                    continue
                self._log(f"   [{idx + 1}/{len(gallery_sources)}] Processing gallery image...")
                result = self.process_and_upload(
                    img_url, product_id, 'gallery', idx, remove_bg=remove_bg_gallery
                )
                if result:
                    gallery_recommended.append(result)
                    self._log(f"      ✓ Uploaded: {result}")
                else:
                    self._log(f"      ✗ Failed")
        
        product_data['gallery_images_recommended'] = gallery_recommended
        
        # Process description images
        desc_recommended = []
        desc_sources = product_data.get('description_images_remote', product_data.get('description_images', []))
        
        if desc_sources:
            self._log(f"   Processing {len(desc_sources)} description images...")
            for idx, img_url in enumerate(desc_sources):
                if not img_url:
                    continue
                self._log(f"   [{idx + 1}/{len(desc_sources)}] Processing description image...")
                result = self.process_and_upload(
                    img_url, product_id, 'description', idx, remove_bg=remove_bg_description
                )
                if result:
                    desc_recommended.append(result)
                    self._log(f"      ✓ Uploaded: {result}")
                else:
                    self._log(f"      ✗ Failed")
        
        product_data['description_images_recommended'] = desc_recommended
        
        # Process SKU images
        skus = product_data.get('skus', [])
        if skus:
            self._log(f"   Processing {len(skus)} SKU images...")
            for idx, sku in enumerate(skus):
                img_url = sku.get('image_url_remote', sku.get('image_url', ''))
                if not img_url:
                    continue
                self._log(f"   [{idx + 1}/{len(skus)}] Processing SKU image: {sku.get('name', 'unknown')}")
                result = self.process_and_upload(
                    img_url, product_id, 'sku', idx, remove_bg=remove_bg_gallery
                )
                if result:
                    sku['image_url_recommended'] = result
                    self._log(f"      ✓ Uploaded: {result}")
                else:
                    self._log(f"      ✗ Failed")
        
        self._log(f"✅ Image processing complete for {product_id}")
        self._log(f"   Gallery: {len(gallery_recommended)} processed")
        self._log(f"   Description: {len(desc_recommended)} processed")
        
        return product_data


# Singleton instance for easy access
_processor_instance: Optional[ImageProcessor] = None


def get_processor(silent_mode: bool = False) -> ImageProcessor:
    """Get or create the singleton ImageProcessor instance."""
    global _processor_instance
    if _processor_instance is None:
        _processor_instance = ImageProcessor(silent_mode=silent_mode)
    return _processor_instance


def process_product_images(product_data: Dict, silent_mode: bool = False) -> Dict:
    """Convenience function to process product images.
    
    Args:
        product_data: Product data dictionary.
        silent_mode: Whether to suppress output.
        
    Returns:
        Updated product data with recommended image URLs.
    """
    processor = get_processor(silent_mode=silent_mode)
    return processor.process_product_images(product_data)


if __name__ == "__main__":
    # Test the image processor
    print("Testing Image Processor...")
    
    processor = ImageProcessor(silent_mode=False)
    
    # Test with a sample image URL
    test_data = {
        'product_id': 'test-product-123',
        'gallery_images_remote': [
            'https://ae-pic-a1.aliexpress-media.com/kf/S558371e2a1c84ccea0c5a942e395dc22k.png'
        ],
        'description_images_remote': [],
        'skus': []
    }
    
    result = processor.process_product_images(test_data)
    print(f"\nResult: {result.get('gallery_images_recommended', [])}")


