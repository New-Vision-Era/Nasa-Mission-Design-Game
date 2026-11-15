three.js r187 (MIT, see three/LICENSE), from github.com/mrdoob/three.js tag r187: build/three.module.js,
build/three.core.js and the addons GLTFLoader, OrbitControls, RoomEnvironment, BufferGeometryUtils,
SkeletonUtils. Loaded through the import map in index.html; no build step.

pyodide/: Pyodide 0.29.5 (MPL-2.0, github.com/pyodide/pyodide release 0.29.5) — only the runtime and
the packages the backend needs (pydantic, pydantic-core, sqlite3, typing-extensions, annotated-types,
typing-inspection). Used by js/engine-worker.js to run the backend in the browser.
