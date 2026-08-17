export default async function handler(req, res) {
  const match = req.query.match || '';
  
  // Constrói a URL de destino direta no HF Space
  const targetUrl = new URL(`https://alehcrim-anime-pipeline.hf.space/api/${match}`);

  // Repassa todas as query params (exceto match)
  Object.keys(req.query).forEach(key => {
    if (key !== 'match') {
      targetUrl.searchParams.set(key, req.query[key]);
    }
  });

  const headers = {};
  if (req.headers['content-type']) headers['content-type'] = req.headers['content-type'];
  if (req.headers['x-session-token']) headers['x-session-token'] = req.headers['x-session-token'];
  if (req.headers['accept']) headers['accept'] = req.headers['accept'];
  
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
