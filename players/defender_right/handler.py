"""
players/defender_right/handler.py
Lambda — boto3 + Bedrock directly. No extra deps.
"""
import json, logging, os, re, boto3

logger = logging.getLogger(__name__)
REGION = os.environ.get("AWS_REGION_NAME", "us-east-1")
MODEL  = "amazon.nova-micro-v1:0"
bedrock = boto3.client("bedrock-runtime", region_name=REGION)

SYSTEM = """You are DEF_R, RIGHT DEFENDER. Protect your goal.
Priority: 1.TACKLE(opponent with ball <2.5 units) 2.INTERCEPT(ball toward goal) 3.MARK(opponent STR_01 in your half) 4.CLEAR(ball in box) 5.PASS(to MID_01 if open) 6.MOVE_TO 7.IDLE
NEVER push past x=+5. NEVER SHOOT. Cover the RIGHT flank.
Respond ONLY with valid JSON: {"type":"MOVE_TO","target_position":{"x":-10,"y":5},"target_player_id":null,"rationale":"one line"}
type must be one of: MOVE_TO, PASS, MARK, INTERCEPT, TACKLE, CLEAR, IDLE"""

def handler(event, context):
    try:
        gs = json.dumps(event.get("game_state", event))
        resp = bedrock.invoke_model(
            modelId=MODEL,
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "messages": [{"role": "user", "content": f"Game state:\n{gs}\n\nIssue ONE command JSON now."}],
                "system": [{"text": SYSTEM}],
                "inferenceConfig": {"maxTokens": 150, "temperature": 0.1}
            })
        )
        text = json.loads(resp["body"].read())["output"]["message"]["content"][0]["text"]
        m = re.search(r'\{.*\}', text, re.DOTALL)
        cmd = json.loads(m.group()) if m else {}
        if "type" not in cmd: raise ValueError("no type")
        logger.info("DEF_R → %s | %s", cmd["type"], cmd.get("rationale",""))
        return cmd
    except Exception as e:
        logger.error("DEF_R error: %s", e)
        return {"type":"IDLE","target_player_id":None,"target_position":None,"rationale":"DEF_R error"}
