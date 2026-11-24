// Landmarks in the registered poses, measured as fractions of each frame.
// Each entry is center X/Y, movement X/Y, falloff X/Y, and an optional rigid core.
const poseLandmarks = {
  schedule: [
    [.43, .25, .066, .049, .33, .23],
    [.534, .406, .062, .065, .30, .23],
    [.669, .668, .008, -.026, .20, .17],
    [.759, .752, -.035, -.068, .115, .14],
  ],
  inspection: [
    [.45, .083, .063, .057, .32, .19],
    [.552, .215, .037, .112, .29, .24],
    [.40, .369, .042, .051, .26, .18],
    [.437, .484, .026, .048, .23, .20],
    [.65, .475, .017, .015, .13, .14],
  ],
  review: [
    [.49, .17, .008, .035, .31, .20],
    [.646, .327, -.002, .047, .26, .21],
    [.626, .620, .044, .108, .25, .19],
    [.728, .762, .016, .101, .16, .185],
  ],
  summary: [
    [.59, .25, .059, .002, .29, .25],
    [.61, .41, .075, .001, .27, .23],
    [.445, .664, .107, .022, .25, .22],
    [.61, .675, .125, .007, .39, .19, .19],
  ],
  reports: [
    [.546, .711, -.10, .085, .32, .239],
    [.79, .638, .021, .134, .26, .261],
    [.72, .825, .034, .058, .27, .223],
  ],
};

const vertexSource = `
  precision mediump float;
  attribute vec2 rest;
  attribute vec2 action;
  uniform float progress;
  varying vec2 restUv;
  varying vec2 actionUv;
  void main() {
    restUv = rest;
    actionUv = action;
    vec2 p = mix(rest, action, progress);
    gl_Position = vec4(2.0 * p.x - 1.0, 1.0 - 2.0 * p.y, 0.0, 1.0);
  }
`;

const fragmentSource = `
  precision mediump float;
  uniform sampler2D restImage;
  uniform sampler2D actionImage;
  uniform sampler2D middleImage;
  uniform bool hasMiddle;
  uniform float progress;
  varying vec2 restUv;
  varying vec2 actionUv;
  void main() {
    if (hasMiddle) {
      vec4 middle = texture2D(middleImage, mix(restUv, actionUv, 0.5));
      if (progress < 0.5) {
        gl_FragColor = mix(texture2D(restImage, restUv), middle, smoothstep(0.18, 0.82, progress * 2.0));
      } else {
        gl_FragColor = mix(middle, texture2D(actionImage, actionUv), smoothstep(0.18, 0.82, progress * 2.0 - 1.0));
      }
      return;
    }
    float blend = smoothstep(0.18, 0.82, progress);
    gl_FragColor = mix(texture2D(restImage, restUv), texture2D(actionImage, actionUv), blend);
  }
`;

function makeMesh(landmarks) {
  const divisions = 24;
  const stride = divisions + 1;
  const positions = [];
  const indices = [];

  for (let row = 0; row <= divisions; row += 1) {
    for (let column = 0; column <= divisions; column += 1) {
      const x = column / divisions;
      const y = row / divisions;
      let dx = 0;
      let dy = 0;
      let total = 0;

      for (const [centerX, centerY, moveX, moveY, rangeX, rangeY, core = 0] of landmarks) {
        const distance = ((x - centerX) / rangeX) ** 2 + ((y - centerY) / rangeY) ** 2;
        const falloff = Math.max(0, distance - core) / (1 - core);
        const weight = Math.max(0, 1 - falloff) ** 2;
        dx += moveX * weight;
        dy += moveY * weight;
        total += weight;
      }

      const fixedEdge = Math.min(1, x * 18, (1 - x) * 18, y * 24, (1 - y) * 24);
      const scale = fixedEdge / Math.max(1, total);
      positions.push(x, y, x + dx * scale, y + dy * scale);

      if (row < divisions && column < divisions) {
        const at = row * stride + column;
        indices.push(at, at + 1, at + stride, at + 1, at + stride + 1, at + stride);
      }
    }
  }

  return { positions: new Float32Array(positions), indices: new Uint16Array(indices) };
}

export function createClerkMotion(canvas, images, page) {
  canvas.width = images[0].naturalWidth;
  canvas.height = images[0].naturalHeight;
  const gl = canvas.getContext('webgl', { premultipliedAlpha: true });
  if (!gl) return null;

  const program = gl.createProgram();
  const shaders = [[gl.VERTEX_SHADER, vertexSource], [gl.FRAGMENT_SHADER, fragmentSource]]
    .map(([type, source]) => {
      const shader = gl.createShader(type);
      gl.shaderSource(shader, source);
      gl.compileShader(shader);
      gl.attachShader(program, shader);
      return shader;
    });
  gl.linkProgram(program);
  shaders.forEach((shader) => gl.deleteShader(shader));
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    gl.deleteProgram(program);
    return null;
  }

  const { positions, indices } = makeMesh(poseLandmarks[page]);
  const vertices = gl.createBuffer();
  const triangles = gl.createBuffer();
  gl.useProgram(program);
  gl.bindBuffer(gl.ARRAY_BUFFER, vertices);
  gl.bufferData(gl.ARRAY_BUFFER, positions, gl.STATIC_DRAW);
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, triangles);
  gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, indices, gl.STATIC_DRAW);

  ['rest', 'action'].forEach((name, index) => {
    const attribute = gl.getAttribLocation(program, name);
    gl.enableVertexAttribArray(attribute);
    gl.vertexAttribPointer(attribute, 2, gl.FLOAT, false, 16, index * 8);
  });

  gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, true);
  const samplers = ['restImage', 'actionImage', 'middleImage'];
  const textures = images.map((image, index) => {
    const texture = gl.createTexture();
    gl.activeTexture(gl.TEXTURE0 + index);
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, image);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.uniform1i(gl.getUniformLocation(program, samplers[index]), index);
    return texture;
  });

  gl.uniform1i(gl.getUniformLocation(program, 'hasMiddle'), Number(images.length === 3));
  const progressUniform = gl.getUniformLocation(program, 'progress');
  gl.viewport(0, 0, canvas.width, canvas.height);

  return {
    draw(progress) {
      if (gl.isContextLost()) return false;
      gl.uniform1f(progressUniform, progress);
      gl.drawElements(gl.TRIANGLES, indices.length, gl.UNSIGNED_SHORT, 0);
      return true;
    },
    dispose() {
      textures.forEach((texture) => gl.deleteTexture(texture));
      gl.deleteBuffer(triangles);
      gl.deleteBuffer(vertices);
      gl.deleteProgram(program);
      if (!canvas.isConnected) gl.getExtension('WEBGL_lose_context')?.loseContext();
    },
  };
}
