/* The same viewer runs in the editor and in the downloaded HTML. */
function runViewer(scenes, startId) {
  const canvas = document.querySelector("canvas");
  const links = document.querySelector("#links");
  const status = document.querySelector("#status");
  const select = document.querySelector("select");
  const gl = canvas.getContext("webgl");
  if (!gl) {
    status.textContent = "Activa WebGL para ver el tour 360°.";
    return;
  }

  const program = gl.createProgram();
  const shaders = [
    [gl.VERTEX_SHADER, `
      attribute vec2 vertex;
      varying vec2 screen;
      void main() { screen = vertex; gl_Position = vec4(vertex, 0., 1.); }
    `],
    [gl.FRAGMENT_SHADER, `
      precision highp float;
      uniform sampler2D panorama;
      uniform vec2 scale;
      uniform vec3 forward, right, up;
      varying vec2 screen;
      void main() {
        vec3 ray = normalize(forward + screen.x * scale.x * right + screen.y * scale.y * up);
        vec2 uv = vec2(fract(.5 + atan(ray.x, ray.z) / 6.2831853), .5 - asin(ray.y) / 3.14159265);
        gl_FragColor = texture2D(panorama, uv);
      }
    `],
  ];
  for (const [type, source] of shaders) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    gl.attachShader(program, shader);
  }
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    status.textContent = "El navegador no pudo iniciar el visor 360°.";
    return;
  }
  gl.useProgram(program);
  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
  const vertex = gl.getAttribLocation(program, "vertex");
  gl.enableVertexAttribArray(vertex);
  gl.vertexAttribPointer(vertex, 2, gl.FLOAT, false, 0, 0);
  gl.bindTexture(gl.TEXTURE_2D, gl.createTexture());
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.NONE);
  const uniforms = Object.fromEntries(
    ["scale", "forward", "right", "up"].map(name => [name, gl.getUniformLocation(program, name)])
  );

  const radians = Math.PI / 180;
  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
  const direction = (yaw, pitch) => [
    Math.sin(yaw) * Math.cos(pitch), Math.sin(pitch), Math.cos(yaw) * Math.cos(pitch),
  ];
  const dot = (a, b) => a.reduce((sum, value, i) => sum + value * b[i], 0);
  const byId = new Map(scenes.map(scene => [scene.id, scene]));
  let activeImage;
  let hotspots = [];
  let ready = false;
  let yaw = 0;
  let pitch = 0;
  let zoom = 0.8;
  let pointer;

  function draw() {
    if (!ready) return;
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    if (!width || !height) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    if (canvas.width !== width * dpr || canvas.height !== height * dpr) {
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
    }
    gl.viewport(0, 0, canvas.width, canvas.height);
    const forward = direction(yaw, pitch);
    const right = [Math.cos(yaw), 0, -Math.sin(yaw)];
    const up = direction(yaw, pitch + Math.PI / 2);
    const scaleX = zoom * Math.min(1, width / height);
    const scaleY = zoom * Math.min(1, height / width);
    gl.uniform2f(uniforms.scale, scaleX, scaleY);
    gl.uniform3fv(uniforms.forward, forward);
    gl.uniform3fv(uniforms.right, right);
    gl.uniform3fv(uniforms.up, up);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);

    for (const { button, ray } of hotspots) {
      const depth = dot(ray, forward);
      const x = dot(ray, right) / (depth * scaleX);
      const y = dot(ray, up) / (depth * scaleY);
      button.hidden = depth <= 0 || Math.abs(x) > 0.95 || Math.abs(y) > 0.9;
      button.style.left = (x + 1) * 50 + "%";
      button.style.top = (1 - y) * 50 + "%";
    }
  }

  function show(id) {
    const scene = byId.get(id);
    if (!scene) return;
    select.value = id;
    ready = false;
    links.replaceChildren();
    status.textContent = "Cargando panorama…";
    yaw = (scene.yaw || 0) * radians;
    pitch = 0;
    zoom = 0.8;
    const image = new Image();
    activeImage = image;
    image.onload = () => {
      if (image !== activeImage) return;
      const limit = gl.getParameter(gl.MAX_TEXTURE_SIZE);
      let texture = image;
      if (image.width > limit || image.height > limit) {
        texture = document.createElement("canvas");
        const ratio = limit / Math.max(image.width, image.height);
        texture.width = Math.round(image.width * ratio);
        texture.height = Math.round(image.height * ratio);
        texture.getContext("2d").drawImage(image, 0, 0, texture.width, texture.height);
      }
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, texture);
      hotspots = scene.links.filter(link => byId.has(link.target)).map(link => {
        const button = document.createElement("button");
        button.textContent = "↗ " + byId.get(link.target).name;
        button.onclick = () => show(link.target);
        links.append(button);
        return { button, ray: direction(link.yaw * radians, link.pitch * radians) };
      });
      ready = true;
      status.textContent = "";
      draw();
    };
    image.onerror = () => {
      if (image === activeImage) status.textContent = "No se pudo cargar el panorama.";
    };
    image.src = scene.url;
  }

  for (const scene of scenes) select.add(new Option(scene.name, scene.id));
  select.onchange = () => show(select.value);
  canvas.addEventListener("pointerdown", event => {
    canvas.setPointerCapture(event.pointerId);
    pointer = { id: event.pointerId, x: event.clientX, y: event.clientY };
  });
  canvas.addEventListener("pointermove", event => {
    if (pointer?.id !== event.pointerId) return;
    yaw -= (event.clientX - pointer.x) * 0.004;
    pitch = clamp(pitch + (event.clientY - pointer.y) * 0.004, -1.5, 1.5);
    pointer = { id: event.pointerId, x: event.clientX, y: event.clientY };
    draw();
  });
  canvas.addEventListener("lostpointercapture", () => { pointer = null; });
  canvas.addEventListener("wheel", event => {
    event.preventDefault();
    zoom = clamp(zoom + event.deltaY * 0.001, 0.25, 1.35);
    draw();
  }, { passive: false });
  canvas.addEventListener("keydown", event => {
    const steps = { ArrowLeft: [-0.12, 0], ArrowRight: [0.12, 0], ArrowUp: [0, 0.12], ArrowDown: [0, -0.12] };
    const step = steps[event.key];
    if (!step) return;
    event.preventDefault();
    yaw += step[0];
    pitch = clamp(pitch + step[1], -1.5, 1.5);
    draw();
  });
  new ResizeObserver(draw).observe(canvas);
  show(startId);
}

export function tourDocument(scenes, startId) {
  // Encode HTML-sensitive characters before embedding editable names in a script.
  const configuration = JSON.stringify({ scenes, startId }).replace(/[<>&\u2028\u2029]/g, char =>
    "\\u" + char.charCodeAt(0).toString(16).padStart(4, "0")
  );
  return `<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tour virtual</title>
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data: blob:; script-src 'unsafe-inline'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<style>
*{box-sizing:border-box}body{margin:0;background:#090f19;color:white;font:16px system-ui;overflow:hidden}
canvas,#links{position:absolute;inset:0;width:100%;height:100%}
canvas{touch-action:none;cursor:grab}canvas:active{cursor:grabbing}
#links{pointer-events:none}button,#toolbar{position:absolute}
button,select{background:#101827;color:white;border:1px solid #87dbc0;border-radius:10px;padding:.65rem;font:inherit}
button{pointer-events:auto;cursor:pointer;transform:translate(-50%,-50%);max-width:42%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#toolbar{top:.7rem;left:.7rem;right:.7rem;display:flex;gap:.7rem;align-items:center;flex-wrap:wrap}
select{max-width:100%}#status{margin:0;background:#090f19}
</style></head><body>
<canvas tabindex="0" aria-label="Panorama 360°. Arrastra o usa las flechas para mirar alrededor."></canvas>
<div id="links"></div><div id="toolbar"><select aria-label="Escena"></select><p id="status" role="status"></p></div>
<script>
const config = ${configuration};
(${runViewer.toString()})(config.scenes, config.startId);
</script></body></html>`;
}
