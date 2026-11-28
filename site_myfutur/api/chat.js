// Relais vers DeepSeek : la clé reste sur le serveur (variable DEEPSEEK_API_KEY dans Vercel).
module.exports = async (req, res) => {
  if (req.method !== "POST") { res.status(405).json({ error: "method" }); return; }
  const key = process.env.DEEPSEEK_API_KEY;
  if (!key) { res.status(503).json({ error: "no_key" }); return; }
  const host = req.headers.host || "";
  const origin = req.headers.origin || req.headers.referer || "";
  if (origin && !origin.includes(host)) { res.status(403).json({ error: "origin" }); return; }
  let body = req.body;
  if (typeof body === "string") { try { body = JSON.parse(body); } catch (e) { body = null; } }
  const msgs = body && Array.isArray(body.messages) ? body.messages : null;
  if (!msgs || !msgs.length || msgs.length > 40) { res.status(400).json({ error: "messages" }); return; }
  if (JSON.stringify(msgs).length > 120000) { res.status(413).json({ error: "too_large" }); return; }
  const payload = { model: "deepseek-chat", messages: msgs, max_tokens: 2000, temperature: 0.7 };
  if (Array.isArray(body.tools) && body.tools.length) payload.tools = body.tools.slice(0, 20);
  try {
    const r = await fetch("https://api.deepseek.com/chat/completions", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + key },
      body: JSON.stringify(payload),
    });
    if (!r.ok) { res.status(r.status === 429 ? 429 : r.status === 400 ? 400 : 502).json({ error: "upstream_" + r.status }); return; }
    const d = await r.json();
    res.status(200).json({ message: (d.choices && d.choices[0] && d.choices[0].message) || {} });
  } catch (e) { res.status(502).json({ error: "network" }); }
};
