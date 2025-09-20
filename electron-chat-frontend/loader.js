// External loader for offline React fallback.
// Tries dev server if http(s), else loads vendor React UMD (./vendor/ or ../vendor/).
(function() {
  const isHttp = location.protocol === 'http:' || location.protocol === 'https:';
  if (isHttp) {
    const s = document.createElement('script');
    s.type = 'module';
    s.src = './src/main.jsx';
    s.onerror = () => console.error('[loader] Failed to load dev entry ./src/main.jsx');
    document.head.appendChild(s);
    return;
  }

  function showLoaderError(msg) {
    console.error(msg);
    const root = document.getElementById('root');
    if (root) {
      root.innerHTML = '<div style="padding:16px;font-family:monospace;color:#c00;">'+
        '<h3>启动失败 (React 资源缺失)</h3>'+
        '<p>'+msg+'</p>'+
        '<p>请执行: <code>npm run prepare</code> 以生成 <code>vendor/react*.js</code></p>'+
        '<p>调试: 查看控制台日志 [loader].* 了解尝试的路径。</p>'+
      '</div>';
    }
  }

  function loadRendererReact() {
    const s = document.createElement('script');
    s.src = './renderer-react.js';
    s.onerror = () => showLoaderError('[loader] Failed to load renderer-react.js');
    document.head.appendChild(s);
  }

  function attemptReact(basePath, triedSecond) {
    const reactPath = basePath + 'react.production.min.js';
    console.log('[loader] trying', reactPath);
    const r = document.createElement('script');
    r.src = reactPath;
    r.onload = () => {
      const rd = document.createElement('script');
      const rdPath = basePath + 'react-dom.production.min.js';
      console.log('[loader] trying', rdPath);
      rd.src = rdPath;
      rd.onload = () => loadRendererReact();
      rd.onerror = () => {
        if (!triedSecond && basePath === './vendor/') {
          console.warn('[loader] react-dom failed from', rdPath, 'retrying parent path');
          attemptReact('../vendor/', true);
        } else {
          showLoaderError('[loader] Failed to load react-dom from both paths');
        }
      };
      document.head.appendChild(rd);
    };
    r.onerror = () => {
      if (!triedSecond && basePath === './vendor/') {
        console.warn('[loader] react failed from', reactPath, 'retrying parent path');
        attemptReact('../vendor/', true);
      } else {
        showLoaderError('[loader] Failed to load react from both paths');
      }
    };
    document.head.appendChild(r);
  }

  attemptReact('./vendor/', false);
})();
