"""
players/midfielder/handler.py
Lambda — boto3 + Bedrock directly. No extra deps.
"""
import json, logging, os, re, boto3

logger = logging.getLogger(__name__)
REGION = os.environ.get("AWS_REGION_NAME", "us-east-1")
MODEL  = "amazon.nova-micro-v1:0"
bedrock = boto3.client("bedrock-runtime", region_name=REGION)

SYSTEM = """You are MID_01, MIDFIELDER — engine of the team.
Priority: 1.PASS(to STR_01 if clear path) 2.PRESS_BALL(opponent with ball nearby) 3.INTERCEPT(ball in midfield) 4.DRIBBLE(space ahead) 5.PASS(backward to DEF) 6.MOVE_TO 7.IDLE
Do NOT always choose PASS. Vary commands. PRESS_BALL and INTERCEPT are high value.
Respond ONLY with valid JSON: {"type":"MOVE_TO","target_position":{"x":0,"y":0},"target_player_id":null,"rationale":"one line"}
type must be one of: MOVE_TO, PASS, PRESS_BALL, DRIBBLE, INTERCEPT, IDLE"""

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
        logger.info("MID_01 → %s | %s", cmd["type"], cmd.get("rationale",""))
        return cmd
    except Exception as e:
        logger.error("MID_01 error: %s", e)
        return {"type":"IDLE","target_player_id":None,"target_position":None,"rationale":"MID error"}
