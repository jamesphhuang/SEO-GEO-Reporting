"""Minimal MCP stdio client: run a server, list tools, and invoke tool calls."""
import asyncio, json, os, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    spec = json.load(open(sys.argv[1]))
    env = dict(os.environ); env.update(spec.get("env", {}))
    params = StdioServerParameters(command=spec["command"], args=spec.get("args", []), env=env)
    out = {"tools": [], "results": []}
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools()
            out["tools"] = [{"name": t.name, "desc": (t.description or "")[:160],
                             "params": list((t.inputSchema or {}).get("properties", {}).keys())} for t in tools.tools]
            for call in spec.get("calls", []):
                try:
                    res = await s.call_tool(call["name"], call.get("args", {}))
                    texts = [c.text for c in res.content if getattr(c, "text", None)]
                    out["results"].append({"call": call, "isError": res.isError, "text": texts})
                except Exception as e:
                    out["results"].append({"call": call, "error": f"{type(e).__name__}: {e}"})
    json.dump(out, open(sys.argv[2], "w"), ensure_ascii=False, indent=1)
    print("tools:", [t["name"] for t in out["tools"]])
    for r in out["results"]:
        print("---", r["call"]["name"], "err" if r.get("error") or r.get("isError") else "ok")
        print((r.get("error") or "\n".join(r.get("text", []))[:1200]))

asyncio.run(main())
