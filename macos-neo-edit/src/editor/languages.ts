const extensionToLanguage: Record<string, string> = {
  // JavaScript / TypeScript
  js: 'javascript',
  mjs: 'javascript',
  cjs: 'javascript',
  jsx: 'javascript',
  ts: 'typescript',
  tsx: 'typescript',
  mts: 'typescript',
  cts: 'typescript',
  // Python
  py: 'python',
  pyw: 'python',
  pyi: 'python',
  // Rust
  rs: 'rust',
  // Go
  go: 'go',
  // Java
  java: 'java',
  // C / C++
  c: 'c',
  h: 'c',
  cpp: 'cpp',
  cc: 'cpp',
  cxx: 'cpp',
  hpp: 'cpp',
  hh: 'cpp',
  hxx: 'cpp',
  // C#
  cs: 'csharp',
  // HTML
  html: 'html',
  htm: 'html',
  // CSS
  css: 'css',
  // SCSS / LESS
  scss: 'scss',
  less: 'less',
  // JSON
  json: 'json',
  jsonc: 'json',
  // Markdown
  md: 'markdown',
  mdx: 'markdown',
  // YAML
  yaml: 'yaml',
  yml: 'yaml',
  // XML
  xml: 'xml',
  svg: 'xml',
  plist: 'xml',
  // SQL
  sql: 'sql',
  // Shell
  sh: 'shell',
  bash: 'shell',
  zsh: 'shell',
  fish: 'shell',
  // PHP
  php: 'php',
  // Ruby
  rb: 'ruby',
  // Swift
  swift: 'swift',
  // Misc
  toml: 'ini',
  ini: 'ini',
  cfg: 'ini',
  conf: 'ini',
  log: 'plaintext',
  txt: 'plaintext',
  gitignore: 'plaintext',
  dockerfile: 'dockerfile',
  makefile: 'plaintext',
};

export function detectLanguage(filePath: string): string {
  const parts = filePath.split('/').pop() ?? '';
  const lower = parts.toLowerCase();

  // Special filenames
  if (lower === 'dockerfile') return 'dockerfile';
  if (lower === 'makefile' || lower === 'gnumakefile') return 'plaintext';
  if (lower === '.gitignore' || lower === '.dockerignore') return 'plaintext';

  const ext = lower.split('.').pop() ?? '';
  return extensionToLanguage[ext] ?? 'plaintext';
}

export const availableLanguages = [
  'plaintext',
  'javascript',
  'typescript',
  'python',
  'rust',
  'go',
  'java',
  'c',
  'cpp',
  'csharp',
  'html',
  'css',
  'scss',
  'less',
  'json',
  'markdown',
  'yaml',
  'xml',
  'sql',
  'shell',
  'php',
  'ruby',
  'swift',
  'dockerfile',
  'ini',
];
