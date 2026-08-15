export default async function handler(req, res) {
  const { path } = req.query;
  const targetPath = Array.isArray(path) ? path.join('/') : (path || '');
  const url = new URL(`https://alehcrim-anime-pipeline.hf.space/api/${targetPath}`);

  // Forward query params
  Object.keys(req.query).forEach(key => {
    if (key !== 'path') {
      url.searchParams.append(key, req.query[key]);
    }
  });

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

    const response = await fetch(url.toString(), fetchOptions);
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
