import json
import boto3
import os

bedrock = boto3.client("bedrock-runtime")

# --- NEW: Forbidden Word List ---
FORBIDDEN_RETURN_WORD = ["prompt", "assistant", "json"]

# --- Function to read the prompt from the file ---
def load_system_prompt():
    """Reads the SYSTEM_PROMPT content from the local file."""
    file_path = os.path.join(os.path.dirname(__file__), 'system_prompt.txt')
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except Exception as e:
        print(f"Error loading system prompt: {e}")
        return "You are a helpful assistant." 

SYSTEM_PROMPT = load_system_prompt()
# ----------------------------------------------------


TEMPLATE = """产品标题：
{title}

产品要点：
{title}
{bullet_point}

产品描述：
{title}
{description}

亚马逊平均价格：
{amazon_avg_price}

亚马逊最低价格：
{amazon_min_price}

亚马逊最低价格产品：
{amazon_min_price_product}

亚马逊最低价格产品链接：
{amazon_min_price_product_url}

速卖通建议价格：
{ali_express_rec_price}
"""

# --- NEW: Forbidden Word Check Function ---
def check_forbidden_words(structured_data, forbidden_list):
    """
    Checks if any word in the forbidden list exists in the title, bullet_point, or description fields.
    Returns the first forbidden word found, or None if clean.
    """
    fields_to_check = [
        structured_data.get("title", ""),
        structured_data.get("bullet_point", ""),
        structured_data.get("description", "")
    ]

    # Combine all text and split into words for a case-insensitive check
    full_text = " ".join(fields_to_check).lower()
    
    for word in forbidden_list:
        # Check if the forbidden word exists as a whole word or substring
        # Using 'in' is simpler and covers most common scenarios like "assistant's" or "json-like"
        if word.lower() in full_text:
            return word

    return None
# ----------------------------------------------------


def lambda_handler(event, context):
    if event.get('httpMethod') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'POST, OPTIONS'
            },
            'body': ''
        }

    try:
        body = json.loads(event.get("body", "{}"))
        user_input = body.get("input_text", "").strip()
    except Exception:
        return {"statusCode": 400, "body": json.dumps({"error": "Invalid body"})}

    if not user_input:
        return {"statusCode": 400, "body": json.dumps({"error": "input_text is required"})}

    messages = [
    {"role": "user", "content": [{"type": "text", "text": SYSTEM_PROMPT + "\n" + user_input}]}
    ]

    response = bedrock.invoke_model(
        modelId="arn:aws:bedrock:us-west-2:443042673085:inference-profile/global.anthropic.claude-haiku-4-5-20251001-v1:0",
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "messages": messages,
            "max_tokens": 2000
            })
        )

    model_output = json.loads(response["body"].read())
    output_text = model_output.get("content", [{}])[0].get("text", "")

    if output_text.startswith("```"):
        output_text = "\n".join(output_text.split("\n")[1:-1])

    try:
        structured = json.loads(output_text)
    except json.JSONDecodeError:
        return {"statusCode": 500, "body": json.dumps({"error": "LLM did not return valid JSON", "raw_output": output_text})}


    # --- NEW: Forbidden Word Check Execution ---
    forbidden_word_found = check_forbidden_words(structured, FORBIDDEN_RETURN_WORD)
    if forbidden_word_found:
        return {
            "statusCode": 500,
            "headers": {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'POST, OPTIONS'
            },
            "body": json.dumps({
                "error": "LLM output contained a forbidden word.",
                "forbidden_word": forbidden_word_found
            })
        }
    # ---------------------------------------------


    # 使用模板填充
    final_text = TEMPLATE.format(
        title=structured.get("title", ""),
        bullet_point=structured.get("bullet_point", ""),
        description=structured.get("description", ""),
        amazon_avg_price=structured.get("amazon_avg_price", "N/A"),
        amazon_min_price=structured.get("amazon_min_price", "N/A"),
        amazon_min_price_product=structured.get("amazon_min_price_product", "N/A"),
        amazon_min_price_product_url=structured.get("amazon_min_price_product_url", "N/A"),
        ali_express_rec_price=structured.get("ali_express_rec_price", "N/A")
        )

    # 在最后返回时确保包含这些头
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "POST, OPTIONS"
        },
        "body": json.dumps({
            "result": final_text,
            "result_structured": structured
        })
    }