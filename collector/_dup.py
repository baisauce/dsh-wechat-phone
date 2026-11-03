import asyncio, json, os, time, websockets
HERE = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8-sig"))
tok = open(cfg["bridge_token_file"]).read().strip()
MSG = {"t":"inbound","kind":"group","group":"幂等测试群","sender":"测试员","text":"这是一条幂等测试消息","at":True,"msg_id":"dup-test-fixed-001","ts":int(time.time())}
async def main():
    async with websockets.connect(f"{cfg['bridge_ws']}?token={tok}") as ws:
        await ws.send(json.dumps(MSG, ensure_ascii=False)); print("第1次注入: 应被接受")
        await asyncio.sleep(1)
        await ws.send(json.dumps(MSG, ensure_ascii=False)); print("第2次注入: 应被去重")
        await asyncio.sleep(1)
asyncio.run(main())
