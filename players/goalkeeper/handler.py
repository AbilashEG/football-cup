"""
players/goalkeeper/handler.py
Lambda — uses boto3 + Bedrock directly. No strands-agents needed.
Tiny zip, no layer required.
"""
import json, logging, os, re, boto3

logger = logging.getLogger(__name__)
REGION = os.environ.get("AWS_REGION_NAME", "us-east-1")
MODEL  = "amazon.nova-micro-v1:0"
bedrock = boto3.client("bedrock-runtime", region_name=REGION)

SYSTEM = """You are GK_01, the GOALKEEPER. Protect the left goal (x=-29,y=0).
Priority: 1.GOALKEEPER_DIVE(shot incoming) 2.CLEAR(ball in box) 3.PASS(you have ball) 4.MOVE_TO(reposition) 5.IDLE
NEVER go past x=-12. NEVER SHOOT.
Respond ONLY with valid JSON: {"type":"MOVE_TO","target_position":{"x":-27,"y":0},"target_player_id":null,"rationale":"one line"}
type must be one of: GOALKEEPER_DIVE, CLEAR, PASS, MOVE_TO, IDLE"""

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
        if "type" not in cmd:
            raise ValueError("no type")
        logger.info("GK_01 → %s | %s", cmd["type"], cmd.get("rationale",""))
        return cmd
    except Exception as e:
        logger.error("GK_01 error: %s", e)
        return {"type":"IDLE","target_player_id":None,"target_position":None,"rationale":"GK error"}
