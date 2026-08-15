export default async function handler(req, res) {
  // Extrai o caminho relativo e query params recebidos na Vercel (ex: "/api/douyin/session/verify?session=xyz")
  const rawUrl = req.url || '';
  
  // Remove o prefixo "/api/" para montar o caminho de destino no HF Space
  const cleanRelative = rawUrl.startsWith('/api/') ? rawUrl.slice(5) : rawUrl.replace(/^\/api\/?/, '');
  const targetUrl = new URL(`https://alehcrim-anime-pipeline.hf.space/api/${cleanRelative}`);

  const headers = { ...req.headers };
  delete headers.host;

  const hfToken = process.env.HF_TOKEN;
  if (hfToken) {
    headers['Authorization'] = `Bearer ${hfToken}`;
  }


  try {
    const fetchOptions = {
      method: req.method,
      headers
    };

    if (req.method !== 'GET' && req.method !== 'HEAD' && req.body) {
      fetchOptions.body = typeof req.body === 'string' ? req.body : JSON.stringify(req.body);
    }

    const response = await fetch(targetUrl.toString(), fetchOptions);
    const contentType = response.headers.get('content-type') || 'application/json';

    res.status(response.status);
    res.setHeader('Content-Type', contentType);
    res.setHeader('Access-Control-Allow-Origin', '*');

    if (contentType.includes('application/json')) {
      const data = await response.json();
      return res.json(data);
    } else {
      const text = await response.text();
      return res.send(text);
    }
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
}
